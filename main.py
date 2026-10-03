from __future__ import annotations

import asyncio
import ipaddress
import json
import os
import re
import sqlite3
import time
import unicodedata
from contextlib import asynccontextmanager, suppress
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlsplit

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field, field_validator
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
DB_PATH = BASE_DIR / "urls.db"
ALPHABET = "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"
SHORT_URL_PATTERN = re.compile(r"^https?://[^\s<>\"']+$", re.IGNORECASE)
CHARACTER_API_URL = "https://genshin.jmp.blue/characters"
API_BASE_URL = "https://genshin.jmp.blue"
CACHE_TTL_SECONDS = 24 * 60 * 60
SYNC_INTERVAL_SECONDS = 60
CUSTOM_CHARACTER_NAMES = {
    "Traveler (Anemo)", "Vodyanitsa", "Vesna", "Skirk", "Escoffier", "Chasca", "Mualani",
    "Ororon", "Xilonen", "Kachina", "Sandrone",
}
CHARACTER_ELEMENTS = {
    "Chasca": "Anemo", "Escoffier": "Cryo", "Kachina": "Geo", "Mualani": "Hydro",
    "Ororon": "Electro", "Skirk": "Cryo", "Xilonen": "Geo",
}
API_SLUG_ALIASES = {
    "arataki-itto": "itto",
    "kamisato-ayaka": "ayaka",
    "kamisato-ayato": "ayato",
    "kujou-sara": "sara",
    "raiden-shogun": "raiden",
    "shikanoin-heizou": "heizou",
    "malani": "mualani",
}
DISPLAY_NAME_OVERRIDES = {
    "ayaka": "Kamisato Ayaka",
    "ayato": "Kamisato Ayato",
    "heizou": "Shikanoin Heizou",
    "itto": "Arataki Itto",
    "mualani": "Mualani",
    "ororon": "Ororon",
    "raiden": "Raiden Shogun",
    "sara": "Kujou Sara",
    "vesna": "Vesna",
    "vodyanitsa": "Vodyanitsa",
    "skirk": "Skirk",
    "escoffier": "Escoffier",
    "chasca": "Chasca",
    "xilonen": "Xilonen",
    "kachina": "Kachina",
    "traveler-anemo": "Traveler (Anemo)",
}
CLOUD_CATALOG_PATHS = {
    "weapons": "weapons",
    "artifacts": "artifacts",
    "materials": "materials",
    "food": "foods",
}
GITHUB_TREE_PATH = "repos/genshindev/api/git/trees/mistress?recursive=1"
GOOGLE_CSE_API_KEY = os.getenv("GOOGLE_CSE_API_KEY")
GOOGLE_CSE_ID = os.getenv("GOOGLE_CSE_ID")
def parse_cors_allowed_origins(value: str) -> tuple[str, ...]:
    origins = []
    for raw_origin in value.split(","):
        origin = raw_origin.strip().rstrip("/")
        if not origin:
            continue
        if "*" in origin:
            raise ValueError("CORS_ALLOWED_ORIGINS must contain explicit origins; wildcards are disabled.")
        parsed = urlsplit(origin)
        if (
            parsed.scheme.lower() not in {"http", "https"}
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.path
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError(f"Invalid CORS origin: {raw_origin}")
        try:
            parsed.port
        except ValueError as exc:
            raise ValueError(f"Invalid CORS origin port: {raw_origin}") from exc
        origins.append(f"{parsed.scheme.lower()}://{parsed.netloc.lower()}")
    return tuple(origins)


CORS_ALLOWED_ORIGINS = parse_cors_allowed_origins(os.getenv("CORS_ALLOWED_ORIGINS", ""))


class ShortenPayload(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    url: str = Field(min_length=8, max_length=2048)

    @field_validator("url")
    @classmethod
    def validate_destination(cls, value: str) -> str:
        if not SHORT_URL_PATTERN.fullmatch(value) or value.lower().startswith("javascript:") or "\\" in value:
            raise ValueError("Provide a valid absolute http:// or https:// URL.")

        try:
            parsed = urlsplit(value)
        except ValueError as exc:
            raise ValueError("Malformed URL authority.") from exc
        hostname = parsed.hostname
        if parsed.scheme.lower() not in {"http", "https"} or not parsed.netloc or not hostname:
            raise ValueError("URL must include an http(s) scheme and hostname.")
        if parsed.username is not None or parsed.password is not None:
            raise ValueError("URLs containing embedded credentials are not allowed.")
        normalized_hostname = hostname.lower().rstrip(".")
        if "%" in normalized_hostname:
            raise ValueError("Percent-encoded hostnames are not allowed.")
        if normalized_hostname == "localhost" or normalized_hostname.endswith(".localhost"):
            raise ValueError("Loopback destinations are not allowed.")
        try:
            address = ipaddress.ip_address(normalized_hostname)
        except ValueError:
            if re.fullmatch(r"[0-9.]+", normalized_hostname) or re.fullmatch(r"0x[0-9a-f]+", normalized_hostname, re.IGNORECASE):
                raise ValueError("Non-canonical numeric IP destinations are not allowed.")
        else:
            mapped_address = getattr(address, "ipv4_mapped", None)
            mapped_loopback = mapped_address is not None and mapped_address.is_loopback
            if address.is_loopback or address.is_unspecified or mapped_loopback:
                raise ValueError("Loopback destinations are not allowed.")

        decoded_path = parsed.path
        for _ in range(3):
            decoded_path = unquote(decoded_path)
        if any(segment == ".." for segment in decoded_path.split("/")):
            raise ValueError("Path traversal segments are not allowed.")
        return value


class SecurityHeadersMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_secure(message):
            if message["type"] == "http.response.start":
                headers = [
                    (name, value)
                    for name, value in message.get("headers", [])
                    if name.lower() not in {b"server", b"x-powered-by"}
                ]
                present = {name.lower() for name, _ in headers}
                for name, value in (
                    (b"x-content-type-options", b"nosniff"),
                    (b"x-frame-options", b"DENY"),
                    (b"referrer-policy", b"no-referrer"),
                ):
                    if name not in present:
                        headers.append((name, value))
                message["headers"] = headers
            await send(message)

        await self.app(scope, receive, send_secure)

BANNER_PHASES = [
    {
        "id": "version-7-1-phase-1",
        "label": "Version 7.1 · Phase I",
        "status": "active",
        "starts_at": "2026-09-23T00:00:00Z",
        "ends_at": "2026-10-13T00:00:00Z",
        "characters": ["Vodyanitsa", "Vesna"],
        "featured_four_stars": ["Faruzan", "Chongyun", "Diona"],
        "weapons": ["Beyond the Chrysalis", "Hymn of the Maelstrom"],
    },
    {
        "id": "version-7-1-phase-2",
        "label": "Version 7.1 · Phase II",
        "status": "upcoming",
        "starts_at": "2026-10-13T00:00:00Z",
        "ends_at": "2026-11-03T00:00:00Z",
        "characters": ["Skirk", "Escoffier"],
        "featured_four_stars": [],
        "weapons": ["Azurelight", "Symphonist of Scents"],
    },
]

ABYSS_FLOOR_12 = {
    "cycle": "Version 7.1 · October 2026",
    "floor": 12,
    "blessing": {
        "name": "Ice-Surging Moon",
        "description": "Triggering Swirl or Stellar Swirl deals True DMG at the opponent's location once every 4 seconds.",
        "cooldown_seconds": 4,
    },
    "halves": [
        {
            "name": "First Half",
            "disorders": ["+200% Swirl DMG", "+75% Stellar Swirl DMG"],
            "recommended_elements": ["Anemo"],
        },
        {
            "name": "Second Half",
            "disorders": ["+200% Electro-Charged DMG", "+75% Lunar-Charged DMG"],
            "recommended_elements": ["Electro", "Hydro"],
        },
    ],
    "chambers": [
        {
            "number": 1,
            "first_half_enemies": ["Bandersnatch", "Wilderness Exiles"],
            "second_half_enemies": ["Raskolnikov"],
            "strategy": "Bring Anemo crowd control to group targets and capitalize on the Swirl buffs.",
            "recommended_elements": ["Anemo"],
            "recommended_teams": {
                "first_half": ["Venti", "Kazuha", "Furina", "Bennett"],
                "second_half": ["Raiden Shogun", "Yelan", "Xingqiu", "Sucrose"],
            },
        },
        {
            "number": 2,
            "first_half_enemies": ["Immortal Constructs"],
            "second_half_enemies": ["Whisperer"],
            "strategy": "Use strong Electro and Hydro application to maintain Electro-Charged control.",
            "recommended_elements": ["Electro", "Hydro"],
            "recommended_teams": {
                "first_half": ["Fischl", "Beidou", "Xingqiu", "Sucrose"],
                "second_half": ["Raiden Shogun", "Furina", "Yelan", "Kazuha"],
            },
        },
        {
            "number": 3,
            "first_half_enemies": ["Churin"],
            "second_half_enemies": ["Sigurd"],
            "strategy": "Apply high-impact elemental breaks to interrupt defensive stances.",
            "recommended_elements": ["Anemo", "Electro", "Hydro"],
            "recommended_teams": {
                "first_half": ["Kazuha", "Fischl", "Xingqiu", "Bennett"],
                "second_half": ["Raiden Shogun", "Furina", "Sucrose", "Yelan"],
            },
        },
    ],
}


def character_slug(display_name: str) -> str:
    normalized = unicodedata.normalize("NFKD", display_name).encode("ascii", "ignore").decode("ascii")
    normalized = re.sub(r"[()]", " ", normalized.lower())
    return re.sub(r"[^a-z0-9]+", "-", normalized).strip("-")


def api_character_slug(value: str) -> str:
    normalized = character_slug(value)
    return API_SLUG_ALIASES.get(normalized, normalized)


def display_name_for_slug(slug: str) -> str:
    return DISPLAY_NAME_OVERRIDES.get(slug, slug.replace("-", " ").title())


def mock_character(display_name: str) -> dict[str, Any]:
    is_traveler = display_name == "Traveler (Anemo)"
    return {
        "name": display_name,
        "element": "Anemo" if is_traveler else CHARACTER_ELEMENTS.get(display_name, "Unknown"),
        "weapon": "Sword" if is_traveler else "Unknown",
        "rarity": 5,
        "region": "Mondstadt" if is_traveler else "Unknown",
        "role": "Traveler" if is_traveler else "Unreleased",
        "specialty": "Local specialty (verify in-game)",
        "boss_drop": "Ascension material (verify in-game)",
        "talent_books": ["Talent material (verify in-game)"],
        "artifact_sets": [
            {
                "name": "Flexible 2-piece set",
                "main_stats": {"sands": "ATK%", "goblet": "Elemental DMG Bonus", "circlet": "CRIT Rate"},
                "substats": ["CRIT Rate", "CRIT DMG", "ATK%", "Energy Recharge"],
            }
        ],
    }

BASE_CHARACTERS = [
    {
        "name": "Furina",
        "element": "Hydro",
        "weapon": "Sword",
        "rarity": 5,
        "region": "Fontaine",
        "role": "Burst Support",
        "specialty": "Fontainian Water",
        "boss_drop": "Ring of Boreal Wolf",
        "talent_books": ["Freedom", "Justice", "Elegance"],
        "artifact_sets": [
            {
                "name": "Emblem of Severed Fate",
                "main_stats": {"sands": "ATK%", "goblet": "Hydro DMG Bonus", "circlet": "CRIT Rate"},
                "substats": ["ATK%", "CRIT Rate", "CRIT DMG", "Energy Recharge"]
            },
            {
                "name": "Golden Troupe",
                "main_stats": {"sands": "ATK%", "goblet": "Hydro DMG Bonus", "circlet": "CRIT DMG"},
                "substats": ["ATK%", "CRIT Rate", "CRIT DMG", "Elemental Mastery"]
            }
        ]
    },
    {
        "name": "Raiden Shogun",
        "element": "Electro",
        "weapon": "Polearm",
        "rarity": 5,
        "region": "Inazuma",
        "role": "Burst DPS",
        "specialty": "Storm Beads",
        "boss_drop": "Storm Beads",
        "talent_books": ["Light", "Transience", "Elegance"],
        "artifact_sets": [
            {
                "name": "Emblem of Severed Fate",
                "main_stats": {"sands": "Energy Recharge", "goblet": "Electro DMG Bonus", "circlet": "CRIT Rate"},
                "substats": ["Energy Recharge", "ATK%", "CRIT Rate", "CRIT DMG"]
            },
            {
                "name": "Gilded Dreams",
                "main_stats": {"sands": "ATK%", "goblet": "Electro DMG Bonus", "circlet": "CRIT DMG"},
                "substats": ["ATK%", "Energy Recharge", "CRIT Rate", "Elemental Mastery"]
            }
        ]
    },
    {
        "name": "Hu Tao",
        "element": "Pyro",
        "weapon": "Polearm",
        "rarity": 5,
        "region": "Liyue",
        "role": "Main DPS",
        "specialty": "Silk Flower",
        "boss_drop": "Juvenile Jade",
        "talent_books": ["Diligence", "Guide to Gold", "Freedom"],
        "artifact_sets": [
            {
                "name": "Crimson Witch of Flames",
                "main_stats": {"sands": "ATK%", "goblet": "Pyro DMG Bonus", "circlet": "CRIT DMG"},
                "substats": ["ATK%", "CRIT Rate", "CRIT DMG", "HP%"]
            },
            {
                "name": "Shimenawa's Reminiscence",
                "main_stats": {"sands": "ATK%", "goblet": "Pyro DMG Bonus", "circlet": "CRIT DMG"},
                "substats": ["ATK%", "CRIT Rate", "CRIT DMG", "Energy Recharge"]
            }
        ]
    },
    {
        "name": "Zhongli",
        "element": "Geo",
        "weapon": "Polearm",
        "rarity": 5,
        "region": "Liyue",
        "role": "Shield Support",
        "specialty": "Cor Lapis",
        "boss_drop": "Basalt Pillar",
        "talent_books": ["Gold", "Prosperity", "Diligence"],
        "artifact_sets": [
            {
                "name": "Tenacity of the Millelith",
                "main_stats": {"sands": "HP%", "goblet": "Geo DMG Bonus", "circlet": "CRIT Rate"},
                "substats": ["HP%", "Energy Recharge", "CRIT Rate", "DEF%"]
            },
            {
                "name": "Archaic Petra",
                "main_stats": {"sands": "HP%", "goblet": "Geo DMG Bonus", "circlet": "CRIT Rate"},
                "substats": ["HP%", "DEF%", "Elemental Mastery", "CRIT Rate"]
            }
        ]
    },
    {
        "name": "Kazuha",
        "element": "Anemo",
        "weapon": "Sword",
        "rarity": 5,
        "region": "Inazuma",
        "role": "Crowd Control",
        "specialty": "Sea Ganoderma",
        "boss_drop": "Marionette Core",
        "talent_books": ["Freedom", "Transience", "Elegance"],
        "artifact_sets": [
            {
                "name": "Viridescent Venerer",
                "main_stats": {"sands": "ATK%", "goblet": "Anemo DMG Bonus", "circlet": "Elemental Mastery"},
                "substats": ["ATK%", "EM", "CRIT Rate", "Energy Recharge"]
            },
            {
                "name": "The Noblesse Oblige",
                "main_stats": {"sands": "ATK%", "goblet": "Anemo DMG Bonus", "circlet": "ATK%"},
                "substats": ["ATK%", "Energy Recharge", "CRIT Rate", "Elemental Mastery"]
            }
        ]
    },
]

@asynccontextmanager
async def lifespan(application: FastAPI):
    init_db()
    sync_task = asyncio.create_task(cloud_sync_worker())
    try:
        yield
    finally:
        sync_task.cancel()
        with suppress(asyncio.CancelledError):
            await sync_task


limiter = Limiter(key_func=get_remote_address)
app = FastAPI(title="GenshinNexus", lifespan=lifespan)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(CORS_ALLOWED_ORIGINS),
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
    max_age=600,
)
app.add_middleware(SecurityHeadersMiddleware)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


def open_database() -> sqlite3.Connection:
    connection = sqlite3.connect(DB_PATH, timeout=10)
    connection.execute("PRAGMA mmap_size = 8388608")
    connection.execute("PRAGMA busy_timeout = 10000")
    return connection


def init_db() -> None:
    with open_database() as conn:
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS urls (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                long_url TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS characters (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                element TEXT NOT NULL,
                weapon TEXT NOT NULL,
                rarity INTEGER NOT NULL,
                region TEXT NOT NULL,
                role TEXT NOT NULL,
                specialty TEXT NOT NULL,
                boss_drop TEXT NOT NULL,
                talent_books TEXT NOT NULL,
                artifact_sets TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS api_cache (
                cache_key TEXT PRIMARY KEY,
                payload TEXT NOT NULL,
                cached_at REAL NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS cloud_cache (
                slug TEXT PRIMARY KEY,
                data_json TEXT NOT NULL,
                timestamp INTEGER NOT NULL
            )
            """
        )
        conn.execute(
            """
            INSERT OR IGNORE INTO cloud_cache (slug, data_json, timestamp)
            SELECT cache_key, payload, CAST(cached_at AS INTEGER) FROM api_cache
            """
        )
        conn.commit()

        archive_characters = [*BASE_CHARACTERS, *(mock_character(name) for name in CUSTOM_CHARACTER_NAMES)]
        for character in archive_characters:
            row = conn.execute("SELECT 1 FROM characters WHERE name = ?", (character["name"],)).fetchone()
            if row is None:
                conn.execute(
                    """
                    INSERT INTO characters (
                        name, element, weapon, rarity, region, role, specialty,
                        boss_drop, talent_books, artifact_sets
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        character["name"],
                        character["element"],
                        character["weapon"],
                        character["rarity"],
                        character["region"],
                        character["role"],
                        character["specialty"],
                        character["boss_drop"],
                        json.dumps(character["talent_books"]),
                        json.dumps(character["artifact_sets"]),
                    ),
                )
        conn.commit()


def read_api_cache(cache_key: str, allow_expired: bool = False) -> Any | None:
    with open_database() as conn:
        row = conn.execute(
            "SELECT data_json, timestamp FROM cloud_cache WHERE slug = ?",
            (cache_key,),
        ).fetchone()
    if row is None or (not allow_expired and time.time() - row[1] >= CACHE_TTL_SECONDS):
        return None
    return json.loads(row[0])


def write_api_cache(cache_key: str, payload: Any) -> None:
    with open_database() as conn:
        conn.execute(
            """
            INSERT INTO cloud_cache (slug, data_json, timestamp)
            VALUES (?, ?, ?)
            ON CONFLICT(slug) DO UPDATE SET
                data_json = excluded.data_json,
                timestamp = excluded.timestamp
            """,
            (cache_key, json.dumps(payload), int(time.time())),
        )
        conn.commit()


async def fetch_cloud_json(
    cache_key: str,
    path: str,
    *,
    force_refresh: bool = False,
    base_url: str = API_BASE_URL,
) -> Any:
    cached = None if force_refresh else read_api_cache(cache_key)
    if cached is not None:
        return cached

    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            response = await client.get(f"{base_url.rstrip('/')}/{path.lstrip('/')}")
        response.raise_for_status()
        payload = response.json()
        write_api_cache(cache_key, payload)
        return payload
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code != 404:
            stale = read_api_cache(cache_key, allow_expired=True)
            if stale is not None:
                return stale
        raise
    except (httpx.HTTPError, ValueError):
        stale = read_api_cache(cache_key, allow_expired=True)
        if stale is not None:
            return stale
        raise


async def cloud_sync_pass() -> dict[str, Any]:
    sync_targets = {
        "characters": ("catalog:characters", "characters", API_BASE_URL),
        "weapons": ("catalog:weapons", "weapons", API_BASE_URL),
        "artifacts": ("catalog:artifacts", "artifacts", API_BASE_URL),
        "materials": ("catalog:materials", "materials", API_BASE_URL),
        "food": ("catalog:food", "foods", API_BASE_URL),
        "github": ("sync:github-tree", GITHUB_TREE_PATH, "https://api.github.com"),
        "google": ("sync:google-search", "customsearch/v1", "https://www.googleapis.com"),
    }

    async def refresh_source(key: str, source: tuple[str, str, str]):
        cache_key, path, base_url = source
        if key == "google":
            if not GOOGLE_CSE_API_KEY or not GOOGLE_CSE_ID:
                return key, {"status": "disabled", "reason": "Google Custom Search credentials are not configured."}
            async with httpx.AsyncClient(timeout=8.0) as client:
                response = await client.get(
                    f"{base_url.rstrip('/')}/{path.lstrip('/')}",
                    params={
                        "key": GOOGLE_CSE_API_KEY,
                        "cx": GOOGLE_CSE_ID,
                        "q": "Genshin Impact event wish banner schedule character data",
                        "num": 10,
                    },
                )
            response.raise_for_status()
            search_data = response.json()
            return key, {
                "status": "ok",
                "results": [
                    {"title": item.get("title", ""), "link": item.get("link", "")}
                    for item in search_data.get("items", [])[:10]
                ],
            }
        if key == "github":
            async with httpx.AsyncClient(timeout=8.0) as client:
                response = await client.get(
                    f"{base_url.rstrip('/')}/{path.lstrip('/')}",
                    headers={"Accept": "application/vnd.github+json"},
                )
            response.raise_for_status()
            return key, response.json()
        return key, await fetch_cloud_json(cache_key, path, force_refresh=True, base_url=base_url)

    results = await asyncio.gather(
        *(refresh_source(key, source) for key, source in sync_targets.items()),
        return_exceptions=True,
    )
    sources: dict[str, dict[str, Any]] = {}
    for (source_key, _), result in zip(sync_targets.items(), results):
        if isinstance(result, BaseException):
            sources[source_key] = {"status": "error", "detail": str(result)[:180]}
            continue
        key, payload = result
        if key == "google":
            status = payload.get("status", "ok")
            summary = {"status": status, "items": len(payload.get("results", []))}
            if payload.get("results"):
                write_api_cache("sync:google-summary", payload["results"])
            sources[key] = summary
            continue
        if key == "github":
            tree = payload.get("tree", []) if isinstance(payload, dict) else []
            paths = [
                entry.get("path", "")
                for entry in tree
                if isinstance(entry, dict)
                and any(term in entry.get("path", "").lower() for term in ("character", "weapon", "artifact"))
            ]
            summary = {
                "sha": payload.get("sha"),
                "matching_paths": len(paths),
                "sample_paths": paths[:40],
            }
            write_api_cache("sync:github-summary", summary)
            sources[key] = {"status": "ok", **summary}
        else:
            sources[key] = {
                "status": "ok",
                "items": len(payload) if isinstance(payload, list) else 0,
            }

    previous = read_api_cache("sync:state", allow_expired=True) or {}
    state = {
        "status": "degraded" if any(source.get("status") == "error" for source in sources.values()) else "online" if sources else "degraded",
        "revision": int(time.time()),
        "last_synced_at": datetime.now(timezone.utc).isoformat(),
        "interval_seconds": SYNC_INTERVAL_SECONDS,
        "sources": sources,
        "previous_revision": previous.get("revision"),
    }
    write_api_cache("sync:state", state)
    return state


async def cloud_sync_worker() -> None:
    while True:
        await asyncio.sleep(SYNC_INTERVAL_SECONDS)
        try:
            await cloud_sync_pass()
        except Exception:
            previous = read_api_cache("sync:state", allow_expired=True) or {}
            previous.update({"status": "degraded", "last_error_at": datetime.now(timezone.utc).isoformat()})
            write_api_cache("sync:state", previous)


def get_sync_state() -> dict[str, Any]:
    return read_api_cache("sync:state", allow_expired=True) or {
        "status": "starting",
        "revision": 0,
        "last_synced_at": None,
        "interval_seconds": SYNC_INTERVAL_SECONDS,
        "sources": {},
    }


def get_live_banners(now: datetime | None = None) -> dict[str, Any]:
    current_time = now or datetime.now(timezone.utc)
    parsed = [
        {
            **phase,
            "start_epoch": int(datetime.fromisoformat(phase["starts_at"].replace("Z", "+00:00")).timestamp()),
            "end_epoch": int(datetime.fromisoformat(phase["ends_at"].replace("Z", "+00:00")).timestamp()),
        }
        for phase in BANNER_PHASES
    ]
    active = next((phase for phase in parsed if phase["start_epoch"] <= current_time.timestamp() < phase["end_epoch"]), None)
    upcoming = next((phase for phase in parsed if phase["start_epoch"] > current_time.timestamp()), None)
    transition = active["end_epoch"] if active else upcoming["start_epoch"] if upcoming else None
    for phase in parsed:
        phase["status"] = "active" if phase is active else "upcoming" if phase is upcoming else "ended"
    return {
        "active": active,
        "upcoming": upcoming,
        "now_epoch": int(current_time.timestamp()),
        "transition_epoch": transition,
        "seconds_to_transition": max(0, int(transition - current_time.timestamp())) if transition else 0,
    }


async def get_cloud_character_slugs() -> list[str]:
    payload = await fetch_cloud_json("catalog:characters", "characters")
    if not isinstance(payload, list):
        raise ValueError("The cloud character catalog has an unexpected format.")
    return [api_character_slug(str(value)) for value in payload if isinstance(value, str)]


def find_local_character_by_api_slug(slug: str) -> dict[str, Any] | None:
    normalized_slug = api_character_slug(slug)
    return next(
        (
            character
            for character in get_character_catalog()
            if api_character_slug(character["name"]) == normalized_slug
            or character_slug(character["name"]) == character_slug(slug)
        ),
        None,
    )


async def get_character_mappings() -> list[dict[str, Any]]:
    try:
        slugs = await get_cloud_character_slugs()
    except (httpx.HTTPError, ValueError):
        slugs = [api_character_slug(character["name"]) for character in get_character_catalog()]

    mappings = []
    seen_slugs = set()
    for slug in slugs:
        character = find_local_character_by_api_slug(slug)
        display_name = character["name"] if character else display_name_for_slug(slug)
        mappings.append(
            {
                "name": display_name,
                "slug": slug,
                "element": character["element"] if character else "Unknown",
                "weapon": character["weapon"] if character else "Unknown",
                "rarity": character["rarity"] if character else 0,
                "icon_url": f"{CHARACTER_API_URL}/{slug}/icon",
            }
        )
        seen_slugs.add(slug)

    for character in get_character_catalog():
        slug = api_character_slug(character["name"])
        if slug not in seen_slugs:
            mappings.append(
                {
                    "name": character["name"],
                    "slug": slug,
                    "element": character["element"],
                    "weapon": character["weapon"],
                    "rarity": character["rarity"],
                    "icon_url": f"{CHARACTER_API_URL}/{slug}/icon",
                }
            )
    return mappings


def encode_base62(number: int) -> str:
    if number < 0:
        raise ValueError("Number must be non-negative")
    if number == 0:
        return "0"

    chars: list[str] = []
    while number > 0:
        number, remainder = divmod(number, 62)
        chars.append(ALPHABET[remainder])
    return "".join(reversed(chars))


def decode_base62(value: str) -> int:
    if not value:
        return 0

    result = 0
    for char in value:
        index = ALPHABET.find(char)
        if index == -1:
            raise ValueError(f"Invalid base62 character: {char}")
        result = result * 62 + index
    return result


def get_character_catalog() -> list[dict[str, Any]]:
    with open_database() as conn:
        rows = conn.execute(
            """
            SELECT name, element, weapon, rarity, region, role, specialty, boss_drop,
                   talent_books, artifact_sets
            FROM characters ORDER BY name
            """
        ).fetchall()

    characters = []
    for row in rows:
        characters.append(
            {
                "name": row[0],
                "slug": api_character_slug(row[0]),
                "element": row[1],
                "weapon": row[2],
                "rarity": row[3],
                "region": row[4],
                "role": row[5],
                "specialty": row[6],
                "boss_drop": row[7],
                "talent_books": json.loads(row[8]),
                "artifact_sets": json.loads(row[9]),
            }
        )
    return characters


def find_character_by_slug(slug: str) -> dict[str, Any] | None:
    return find_local_character_by_api_slug(slug)


def save_mock_character(display_name: str) -> dict[str, Any]:
    character = mock_character(display_name)
    with open_database() as conn:
        conn.execute(
            """
            INSERT OR IGNORE INTO characters (
                name, element, weapon, rarity, region, role, specialty,
                boss_drop, talent_books, artifact_sets
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                character["name"],
                character["element"],
                character["weapon"],
                character["rarity"],
                character["region"],
                character["role"],
                character["specialty"],
                character["boss_drop"],
                json.dumps(character["talent_books"]),
                json.dumps(character["artifact_sets"]),
            ),
        )
        conn.commit()
    return find_character_by_slug(character_slug(display_name)) or character


def calculate_materials(character_name: str, current_level: int, target_level: int, talent_goals: dict[str, int]) -> dict[str, Any]:
    if current_level >= target_level:
        target_level = current_level + 1

    character = next(
        (item for item in get_character_catalog() if item["name"] == character_name),
        None,
    ) or find_character_by_slug(character_name)
    if character is None:
        raise ValueError(f"Unknown character: {character_name}")

    level_gap = max(0, target_level - current_level)
    specialty_count = max(0, (level_gap // 10) * 3)
    boss_count = max(0, (level_gap // 15) * 2)
    mora = level_gap * 12000 + sum(talent_goals.values()) * 42000

    talent_totals = {
        "normal": max(0, int(talent_goals.get("normal", 1)) - 1) * 3,
        "skill": max(0, int(talent_goals.get("skill", 1)) - 1) * 3,
        "burst": max(0, int(talent_goals.get("burst", 1)) - 1) * 3,
    }

    book_counts = {
        "book_1": talent_totals["normal"] + 2,
        "book_2": talent_totals["skill"] + 2,
        "book_3": talent_totals["burst"] + 2,
    }

    return {
        "character": character_name,
        "element": character["element"],
        "current_level": current_level,
        "target_level": target_level,
        "level_gap": level_gap,
        "regional_specialty": specialty_count,
        "boss_drop": boss_count,
        "talent_books": {
            "book_a": book_counts["book_1"],
            "book_b": book_counts["book_2"],
            "book_c": book_counts["book_3"],
        },
        "mora": mora,
        "summary": (
            f"{character_name} needs {specialty_count} {character['specialty']}s, {boss_count} {character['boss_drop']}s, "
            f"{book_counts['book_1'] + book_counts['book_2'] + book_counts['book_3']} talent books, and {mora:,} Mora."
        ),
    }


def calculate_cloud_materials(
    character: dict[str, Any],
    current_level: int,
    target_level: int,
    talent_goals: dict[str, int],
) -> dict[str, Any]:
    if not 1 <= current_level <= 90 or not 1 <= target_level <= 90:
        raise ValueError("Character levels must be between 1 and 90.")
    if target_level <= current_level:
        target_level = min(90, current_level + 1)

    totals: dict[str, int] = {}
    ascension = character.get("ascension_materials", {})
    for level_name, materials in ascension.items():
        match = re.search(r"(\d+)$", level_name)
        if not match or not current_level < int(match.group(1)) <= target_level:
            continue
        for material in materials:
            material_name = str(material.get("name", "Unknown"))
            totals[material_name] = totals.get(material_name, 0) + int(material.get("value", 0))

    talent_book_counts = {
        f"book_{index}": max(0, int(talent_goals.get(talent, 1)) - 1) * 3 + 2
        for index, talent in enumerate(("normal", "skill", "burst"), start=1)
    }
    local_character = find_local_character_by_api_slug(character.get("slug", "")) or {}
    mora = totals.get("Mora", max(0, target_level - current_level) * 12000)
    required_materials = [
        {"name": name, "amount": amount}
        for name, amount in sorted(totals.items())
        if name != "Mora"
    ]

    return {
        "character": character["name"],
        "element": character.get("element", "Unknown"),
        "current_level": current_level,
        "target_level": target_level,
        "level_gap": target_level - current_level,
        "regional_specialty": totals.get(local_character.get("specialty", ""), 0),
        "specialty_name": local_character.get("specialty", "Regional specialty"),
        "boss_drop": totals.get(local_character.get("boss_drop", ""), 0),
        "boss_name": local_character.get("boss_drop", "Boss material"),
        "talent_books": {
            f"book_{letter}": talent_book_counts[f"book_{index}"]
            for index, letter in enumerate(("a", "b", "c"), start=1)
        },
        "talent_materials": character.get("talent_materials", {}),
        "required_materials": required_materials,
        "mora": mora,
        "summary": (
            f"{character['name']} requires {len(required_materials)} ascension material types "
            f"and {mora:,} Mora from level {current_level} to {target_level}."
        ),
    }


@app.get("/")
def home() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/archive")
def archive() -> FileResponse:
    return FileResponse(STATIC_DIR / "archive.html")


@app.get("/api/characters")
@limiter.limit("10/minute")
async def get_characters(request: Request):
    return await get_character_mappings()


@app.get("/api/banners")
@app.get("/api/banners/live")
@limiter.limit("10/minute")
async def banners(request: Request):
    return get_live_banners()


@app.get("/api/abyss/floor12")
@limiter.limit("10/minute")
async def abyss_floor12(request: Request):
    return ABYSS_FLOOR_12


@app.get("/api/sync-archive")
@limiter.limit("10/minute")
async def sync_archive(request: Request):
    return get_sync_state()


@app.get("/characters/{character_name}")
@limiter.limit("10/minute")
async def get_character_details(request: Request, character_name: str):
    return await load_character_details(character_name)


async def load_character_details(character_name: str) -> dict[str, Any]:
    slug = api_character_slug(character_name)
    local_character = find_local_character_by_api_slug(slug)
    try:
        cloud_slugs = await get_cloud_character_slugs()
    except (httpx.HTTPError, ValueError):
        if local_character is not None:
            return local_character | {"source": "database"}
        raise HTTPException(status_code=502, detail="The cloud character catalog is unavailable.")

    if slug not in cloud_slugs:
        if local_character is not None:
            return local_character | {"source": "database"}
        raise HTTPException(status_code=404, detail="Character is not in the archive.")

    try:
        api_data = await fetch_cloud_json(f"character:{slug}", f"characters/{slug}")
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 404:
            display_name = local_character["name"] if local_character else display_name_for_slug(slug)
            return save_mock_character(display_name) | {"source": "database"}
        if local_character is not None:
            return local_character | {"source": "database"}
        raise HTTPException(status_code=502, detail="The cloud character service is unavailable.") from exc
    except (httpx.HTTPError, ValueError):
        if local_character is not None:
            return local_character | {"source": "database"}
        raise HTTPException(status_code=502, detail="The cloud character service is unavailable.")

    if not isinstance(api_data, dict):
        raise HTTPException(status_code=502, detail="The cloud character response is invalid.")

    character = local_character or mock_character(str(api_data.get("name") or display_name_for_slug(slug)))
    character.update(
        {
            "name": api_data.get("name", character["name"]),
            "slug": slug,
            "element": api_data.get("vision", character["element"]),
            "weapon": api_data.get("weapon", character["weapon"]),
            "rarity": api_data.get("rarity", character["rarity"]),
            "region": api_data.get("nation", character["region"]),
            "description": api_data.get("description", ""),
            "ascension_materials": api_data.get("ascension_materials", {}),
            "talent_materials": api_data.get("talent_materials", {}),
            "icon_url": f"{CHARACTER_API_URL}/{slug}/icon",
            "api_data": api_data,
            "source": "cloud",
        }
    )
    return character


@app.get("/api/catalog/{category}")
@limiter.limit("10/minute")
async def get_catalog_category(request: Request, category: str):
    if category == "characters":
        return {"items": await get_character_mappings(), "source": "cloud"}
    if category == "banners":
        return get_live_banners()
    if category == "spiral-abyss":
        return ABYSS_FLOOR_12

    cloud_path = CLOUD_CATALOG_PATHS.get(category)
    if cloud_path is not None:
        try:
            payload = await fetch_cloud_json(f"catalog:{category}", cloud_path)
        except (httpx.HTTPError, ValueError):
            payload = []
        items = [
            {
                "slug": str(item),
                "name": display_name_for_slug(str(item)),
                "icon_url": f"{API_BASE_URL}/{cloud_path}/{item}/icon",
            }
            for item in payload
            if isinstance(item, str)
        ] if isinstance(payload, list) else []
        return {"items": items, "source": "cloud"}

    if category not in {
        "builds", "teams", "tierlist", "tcg", "tcg-best-decks",
        "leaderboard", "imaginarium-theater", "onslaught",
    }:
        raise HTTPException(status_code=404, detail="Unknown portal category.")
    return {"items": [], "source": "portal", "category": category}


@app.post("/api/build-plan")
@limiter.limit("10/minute")
async def build_plan(request: Request, payload: dict):
    if not payload:
        raise HTTPException(status_code=400, detail="Build payload is required.")

    character_slug_value = str(payload.get("character") or "").strip()
    current_level = int(payload.get("current_level", 1))
    target_level = int(payload.get("target_level", 90))
    talent_goals = payload.get("talent_goals", {"normal": 1, "skill": 1, "burst": 1})

    if not character_slug_value:
        raise HTTPException(status_code=400, detail="A character is required.")

    try:
        character = await load_character_details(character_slug_value)
        result = calculate_cloud_materials(character, current_level, target_level, talent_goals)
        artifact_data = find_local_character_by_api_slug(character_slug_value) or {}
        result["artifact_recommendations"] = artifact_data.get("artifact_sets", [])
        result["character_info"] = {
            "element": character.get("element"),
            "weapon": character.get("weapon"),
            "rarity": character.get("rarity"),
            "role": artifact_data.get("role", "Unassigned"),
        }
        result["icon_url"] = character.get("icon_url")
        return result
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/shorten")
@limiter.limit("10/minute")
def shorten_url(request: Request, payload: ShortenPayload):
    long_url = payload.url

    with open_database() as conn:
        cursor = conn.execute("INSERT INTO urls (long_url) VALUES (?)", (long_url,))
        conn.commit()
        inserted_id = int(cursor.lastrowid)
        slug = encode_base62(inserted_id)

    short_url = str(request.base_url).rstrip("/") + f"/{slug}"
    return {"short_url": short_url, "slug": slug}


@app.get("/{slug}")
def redirect_to_long_url(slug: str):
    try:
        db_id = decode_base62(slug)
    except ValueError:
        return HTMLResponse(
            """
            <html>
              <head><title>Invalid Link</title></head>
              <body style="font-family: sans-serif; padding: 2rem; text-align: center;">
                <h1>Invalid short link</h1>
                <p>This shortened URL is malformed or does not exist.</p>
              </body>
            </html>
            """,
            status_code=404,
        )

    with open_database() as conn:
        row = conn.execute("SELECT long_url FROM urls WHERE id = ?", (db_id,)).fetchone()

    if row is None:
        return HTMLResponse(
            """
            <html>
              <head><title>Not Found</title></head>
              <body style="font-family: sans-serif; padding: 2rem; text-align: center;">
                <h1>Link not found</h1>
                <p>The short URL you requested does not exist.</p>
              </body>
            </html>
            """,
            status_code=404,
        )

    return RedirectResponse(url=row[0], status_code=307)


@app.exception_handler(RateLimitExceeded)
async def slowapi_rate_limit_handler(request: Request, exc: RateLimitExceeded):
    return JSONResponse(status_code=429, content={"detail": "Rate limit exceeded"})


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 8000)),
        server_header=False,
        reload=False,
    )
