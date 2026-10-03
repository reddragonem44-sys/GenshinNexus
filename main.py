from __future__ import annotations

import ipaddress
import json
import os
import re
import secrets
import sqlite3
import threading
import time
import unicodedata
from collections import deque
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlsplit

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field, field_validator
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
DB_PATH = BASE_DIR / "urls.db"
ALPHABET = "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"
SHORT_URL_PATTERN = re.compile(r"^https?://[^\s<>\"']+$", re.IGNORECASE)
CHARACTER_API_URL = "https://genshin.jmp.blue/characters"
API_BASE_URL = "https://genshin.jmp.blue"
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
    "enemies": "enemies",
}


def configured_feed(name: str) -> str | None:
    value = os.getenv(name, "").strip()
    if not value:
        return None
    parsed = urlsplit(value)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password or parsed.fragment:
        raise ValueError(f"{name} must be an absolute HTTPS URL without credentials or fragments.")
    return value


ABYSS_DATA_URL = configured_feed("ABYSS_DATA_URL")
THEATER_DATA_URL = configured_feed("THEATER_DATA_URL")
BANNER_DATA_URL = configured_feed("BANNER_DATA_URL")
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

ELEMENT_RESONANCE = {
    "Pyro": "2 Pyro: ATK +25%.",
    "Hydro": "2 Hydro: Max HP +25%.",
    "Anemo": "2 Anemo: Stamina consumption -15%, movement speed +10%, and skill cooldown -5%.",
}
VELOCITY_WINDOW_SECONDS = 1.0
VELOCITY_REQUEST_LIMIT = 3
CHALLENGE_WAIT_SECONDS = 30
VELOCITY_LOCK = threading.Lock()
CLIENT_REQUESTS: dict[str, deque[float]] = {}
BANNED_CLIENTS: dict[str, dict[str, Any]] = {}


def _flag_client_locked(client_ip: str) -> dict[str, Any]:
    ban = BANNED_CLIENTS.get(client_ip)
    if ban is None:
        ban = {
            "token": secrets.token_urlsafe(32),
            "challenge_started_at": None,
            "last_blocked_at": time.time(),
        }
        BANNED_CLIENTS[client_ip] = ban
    return ban


def flag_client(client_ip: str) -> dict[str, Any]:
    with VELOCITY_LOCK:
        return _flag_client_locked(client_ip).copy()


def get_client_ip(scope: dict[str, Any]) -> str:
    client = scope.get("client")
    return str(client[0]) if client else "unknown"


def challenge_url(ban: dict[str, Any]) -> str:
    return f"/security/challenge/{ban['token']}"


class VelocityBanMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")
        client_ip = get_client_ip(scope)
        is_challenge = path.startswith("/security/challenge/")
        is_counted = path.startswith(("/api/", "/characters/", "/shorten"))
        now = time.monotonic()
        triggered_now = False
        reservation = None

        if not is_challenge:
            with VELOCITY_LOCK:
                ban = BANNED_CLIENTS.get(client_ip)
                if ban is not None and ban["challenge_started_at"] is not None:
                    quiet_since = ban.get("last_blocked_at", ban["challenge_started_at"])
                    if time.time() - quiet_since >= CHALLENGE_WAIT_SECONDS:
                        BANNED_CLIENTS.pop(client_ip, None)
                        CLIENT_REQUESTS.pop(client_ip, None)
                        ban = None
                if ban is None and is_counted:
                    requests = CLIENT_REQUESTS.setdefault(client_ip, deque())
                    while requests and now - requests[0] > VELOCITY_WINDOW_SECONDS:
                        requests.popleft()
                    if len(requests) >= VELOCITY_REQUEST_LIMIT:
                        ban = _flag_client_locked(client_ip)
                        triggered_now = True
                    else:
                        requests.append(now)
                        reservation = now
                    if len(CLIENT_REQUESTS) > 4096:
                        stale_clients = [
                            key for key, stamps in CLIENT_REQUESTS.items()
                            if not stamps or now - stamps[-1] > 60
                        ]
                        for stale_ip in stale_clients:
                            CLIENT_REQUESTS.pop(stale_ip, None)
                if ban is not None:
                    ban["challenge_started_at"] = time.time()
                    ban["last_blocked_at"] = ban["challenge_started_at"]
                    status_code = 429 if triggered_now else 403
                    response_payload = {
                        "detail": "Automated request defenses are active.",
                        "challenge_url": challenge_url(ban),
                    }
                else:
                    response_payload = None
                    status_code = 0

            if response_payload is not None:
                response = JSONResponse(response_payload, status_code=status_code)
                await response(scope, receive, send)
                return

        async def release_failed_request(message):
            if (
                reservation is not None
                and message["type"] == "http.response.start"
                and message["status"] >= 400
            ):
                with VELOCITY_LOCK:
                    requests = CLIENT_REQUESTS.get(client_ip)
                    if requests is not None:
                        try:
                            requests.remove(reservation)
                        except ValueError:
                            pass
            await send(message)

        await self.app(scope, receive, release_failed_request)


def character_slug(display_name: str) -> str:
    normalized = unicodedata.normalize("NFKD", display_name).encode("ascii", "ignore").decode("ascii")
    normalized = re.sub(r"[()]", " ", normalized.lower())
    return re.sub(r"[^a-z0-9]+", "-", normalized).strip("-")


def api_character_slug(value: str) -> str:
    normalized = character_slug(value)
    return API_SLUG_ALIASES.get(normalized, normalized)


def display_name_for_slug(slug: str) -> str:
    return DISPLAY_NAME_OVERRIDES.get(slug, slug.replace("-", " ").title())


@asynccontextmanager
async def lifespan(application: FastAPI):
    init_db()
    yield


limiter = Limiter(key_func=get_remote_address)
app = FastAPI(title="GenshinNexus", lifespan=lifespan)
app.state.limiter = limiter


async def rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded):
    client_ip = request.client.host if request.client else "unknown"
    ban = flag_client(client_ip)
    return JSONResponse(
        {
            "detail": "The request limit was reached. Automated request defenses are active.",
            "challenge_url": challenge_url(ban),
        },
        status_code=429,
    )


app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(CORS_ALLOWED_ORIGINS),
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
    max_age=600,
)
app.add_middleware(VelocityBanMiddleware)
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
        conn.commit()


async def fetch_cloud_json(
    cache_key: str,
    path: str,
    *,
    force_refresh: bool = False,
    base_url: str = API_BASE_URL,
) -> Any:
    async with httpx.AsyncClient(timeout=8.0) as client:
        response = await client.get(f"{base_url.rstrip('/')}/{path.lstrip('/')}")
    response.raise_for_status()
    return response.json()


def stream_json(payload: Any) -> StreamingResponse:
    encoder = json.JSONEncoder(separators=(",", ":"), ensure_ascii=False)

    def chunks():
        for fragment in encoder.iterencode(payload):
            yield fragment.encode("utf-8")

    return StreamingResponse(chunks(), media_type="application/json")


async def fetch_provider_json(url: str | None, source_name: str) -> Any:
    if not url:
        raise HTTPException(status_code=503, detail=f"{source_name} feed is not configured.")
    try:
        async with httpx.AsyncClient(timeout=12.0, follow_redirects=False) as client:
            response = await client.get(url, headers={"Accept": "application/json"})
        response.raise_for_status()
        if len(response.content) > 8 * 1024 * 1024:
            raise HTTPException(status_code=502, detail=f"{source_name} feed exceeds the 8 MB response limit.")
        return response.json()
    except HTTPException:
        raise
    except (httpx.HTTPError, ValueError) as exc:
        raise HTTPException(status_code=502, detail=f"{source_name} feed is unavailable or invalid.") from exc


def suggest_abyss_teams(payload: dict[str, Any]) -> list[dict[str, Any]]:
    roster = payload.get("character_pool", [])
    floors = payload.get("floors", [])
    if not isinstance(roster, list) or not roster:
        return []

    suggestions = []
    for floor in floors:
        required = {
            element
            for half in floor.get("halves", [])
            for element in half.get("recommended_elements", [])
        }
        members = []
        for candidate in roster:
            if not isinstance(candidate, dict) or not candidate.get("name"):
                continue
            if candidate.get("element") in required and candidate not in members:
                members.append(candidate)
            if len(members) == 4:
                break
        for candidate in roster:
            if len(members) == 4:
                break
            if isinstance(candidate, dict) and candidate.get("name") and candidate not in members:
                members.append(candidate)
        counts: dict[str, int] = {}
        for member in members:
            element = member.get("element")
            counts[element] = counts.get(element, 0) + 1
        resonances = [
            {"element": element, "effect": ELEMENT_RESONANCE[element]}
            for element, count in counts.items()
            if count >= 2 and element in ELEMENT_RESONANCE
        ]
        if members:
            suggestions.append({
                "floor": floor.get("floor"),
                "members": members,
                "resonances": resonances,
                "matched_elements": sorted(required.intersection(counts)),
                "algorithm": "element-match-v1",
            })
    return suggestions


async def get_live_banners(now: datetime | None = None) -> dict[str, Any]:
    feed = await fetch_provider_json(BANNER_DATA_URL, "Banner schedule")
    phases = feed.get("phases", []) if isinstance(feed, dict) else []
    if not isinstance(phases, list):
        raise HTTPException(status_code=502, detail="Banner schedule feed has an invalid phase list.")
    current_time = now or datetime.now(timezone.utc)
    parsed = []
    try:
        for phase in phases:
            item = dict(phase)
            item["start_epoch"] = int(datetime.fromisoformat(item["starts_at"].replace("Z", "+00:00")).timestamp())
            item["end_epoch"] = int(datetime.fromisoformat(item["ends_at"].replace("Z", "+00:00")).timestamp())
            parsed.append(item)
    except (KeyError, TypeError, ValueError) as exc:
        raise HTTPException(status_code=502, detail="Banner schedule feed has invalid phase dates.") from exc
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
    try:
        payload = await fetch_cloud_json(
            "catalog:characters",
            "characters",
            force_refresh=True,
        )
    except (httpx.HTTPError, ValueError) as exc:
        raise HTTPException(status_code=502, detail="The live character catalog is unavailable.") from exc
    if not isinstance(payload, list):
        raise ValueError("The cloud character catalog has an unexpected format.")
    return [api_character_slug(str(value)) for value in payload if isinstance(value, str)]


def find_local_character_by_api_slug(slug: str) -> dict[str, Any] | None:
    return None


async def get_character_mappings() -> list[dict[str, Any]]:
    slugs = await get_cloud_character_slugs()
    mappings = []
    for slug in slugs:
        mappings.append(
            {
                "name": display_name_for_slug(slug),
                "slug": slug,
                "element": "Unknown",
                "weapon": "Unknown",
                "rarity": 0,
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
    return []


def find_character_by_slug(slug: str) -> dict[str, Any] | None:
    return find_local_character_by_api_slug(slug)


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
    specialty_name = str(character.get("specialty", "Regional specialty"))
    boss_name = str(character.get("boss_material", "Boss material"))
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
        "regional_specialty": totals.get(specialty_name, 0),
        "specialty_name": specialty_name,
        "boss_drop": totals.get(boss_name, 0),
        "boss_name": boss_name,
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


def render_security_challenge(token: str, remaining_seconds: int, status_code: int = 200) -> HTMLResponse:
    page = f"""<!doctype html>
<html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Verify request · GenshinNexus</title>
<body style="margin:0;background:#111827;color:#f3f4f6;font:16px system-ui;min-height:100vh;display:grid;place-items:center">
<main style="width:min(440px,calc(100% - 40px));padding:24px;border:1px solid #374151;border-radius:12px;background:#1f2937">
<p style="color:#7ce0d4;font-size:12px;font-weight:700;letter-spacing:.12em">GENSHINNEXUS SECURITY</p>
<h1>Confirm this is a person</h1><p id="wait-copy">Please wait {remaining_seconds} seconds before confirming.</p>
<form method="post" action="/security/challenge/{token}/verify"><button id="verify-button" type="submit" {'disabled' if remaining_seconds else ''} style="padding:11px 14px;border:0;border-radius:7px;background:#f1c56f;color:#111827;font-weight:700;cursor:pointer">Verify and return</button></form>
</main><script>
let remaining={remaining_seconds};const button=document.getElementById('verify-button');const copy=document.getElementById('wait-copy');
const countdown=window.setInterval(()=>{{remaining=Math.max(0,remaining-1);copy.textContent=remaining?`Please wait ${{remaining}} seconds before confirming.`:'You can now confirm and return.';if(!remaining){{button.disabled=false;window.clearInterval(countdown);}}}},1000);
</script></body></html>"""
    return HTMLResponse(page, status_code=status_code)


@app.get("/security/challenge/{token}", response_class=HTMLResponse)
def start_security_challenge(request: Request, token: str):
    client_ip = request.client.host if request.client else "unknown"
    if not re.fullmatch(r"[A-Za-z0-9_-]{30,}", token):
        raise HTTPException(status_code=404, detail="Verification challenge not found.")
    with VELOCITY_LOCK:
        ban = BANNED_CLIENTS.get(client_ip)
        if ban is None or not secrets.compare_digest(token, ban["token"]):
            raise HTTPException(status_code=404, detail="Verification challenge not found.")
        if ban["challenge_started_at"] is None:
            ban["challenge_started_at"] = time.time()
            ban["last_blocked_at"] = ban["challenge_started_at"]
        remaining = max(0, CHALLENGE_WAIT_SECONDS - int(time.time() - ban["challenge_started_at"]))
    return render_security_challenge(token, remaining)


@app.post("/security/challenge/{token}/verify")
def verify_security_challenge(request: Request, token: str):
    client_ip = request.client.host if request.client else "unknown"
    with VELOCITY_LOCK:
        ban = BANNED_CLIENTS.get(client_ip)
        if ban is None or not secrets.compare_digest(token, ban["token"]):
            raise HTTPException(status_code=404, detail="Verification challenge not found.")
        started_at = ban["challenge_started_at"]
        if started_at is None:
            raise HTTPException(status_code=400, detail="Open the verification challenge first.")
        remaining = max(0, CHALLENGE_WAIT_SECONDS - int(time.time() - started_at))
        if remaining:
            return render_security_challenge(token, remaining, status_code=429)
        BANNED_CLIENTS.pop(client_ip, None)
        CLIENT_REQUESTS.pop(client_ip, None)
    return RedirectResponse(url="/", status_code=303)


@app.get("/")
def home() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/archive")
def archive() -> FileResponse:
    return FileResponse(STATIC_DIR / "archive.html")


@app.get("/api/characters")
@limiter.limit("10/minute")
async def get_characters(request: Request):
    return stream_json(await get_character_mappings())


@app.get("/api/banners")
@app.get("/api/banners/live")
@limiter.limit("10/minute")
async def banners(request: Request):
    return stream_json(await get_live_banners())


async def load_abyss_feed() -> dict[str, Any]:
    payload = await fetch_provider_json(ABYSS_DATA_URL, "Abyss rotation")
    if not isinstance(payload, dict) or not isinstance(payload.get("floors"), list) or len(payload["floors"]) != 12:
        raise HTTPException(status_code=502, detail="Abyss feed must provide exactly 12 floor records.")
    try:
        payload["floors"] = sorted(payload["floors"], key=lambda floor: int(floor["floor"]))
    except (KeyError, TypeError, ValueError) as exc:
        raise HTTPException(status_code=502, detail="Abyss feed floor numbers are invalid.") from exc
    if [floor["floor"] for floor in payload["floors"]] != list(range(1, 13)):
        raise HTTPException(status_code=502, detail="Abyss feed must contain floors 1 through 12 exactly once.")
    try:
        enemies = await fetch_cloud_json(
            "catalog:enemies",
            "enemies",
            force_refresh=True,
        )
    except (httpx.HTTPError, ValueError) as exc:
        raise HTTPException(status_code=502, detail="The live enemy asset catalog is unavailable.") from exc
    enemy_slugs = set(enemies) if isinstance(enemies, list) else set()
    for floor in payload["floors"]:
        if not isinstance(floor, dict):
            raise HTTPException(status_code=502, detail="Abyss feed contains an invalid floor record.")
        if not isinstance(floor.get("halves"), list) or not isinstance(floor.get("chambers"), list):
            raise HTTPException(status_code=502, detail="Each Abyss floor must provide halves and chambers.")
        if not isinstance(floor.get("blessing"), dict):
            raise HTTPException(status_code=502, detail="Each Abyss floor must provide a blessing or disorder record.")
        floor.setdefault("cycle", payload.get("cycle", "Abyss rotation"))
        floor.setdefault("data_status", "Live provider feed")
        for half in floor["halves"]:
            if not isinstance(half, dict):
                raise HTTPException(status_code=502, detail="Abyss feed contains an invalid half record.")
            half.setdefault("disorders", [])
            half.setdefault("recommended_elements", [])
        assets = []
        for chamber in floor.get("chambers", []):
            if not isinstance(chamber, dict):
                raise HTTPException(status_code=502, detail="Abyss feed contains an invalid chamber record.")
            chamber.setdefault("recommended_elements", [])
            chamber.setdefault("strategy", "Use the listed enemy lineup to plan elemental coverage.")
            for half_key in ("first_half_enemies", "second_half_enemies"):
                names = []
                for enemy in chamber.get(half_key, []):
                    enemy_name = enemy.get("name", "Unknown") if isinstance(enemy, dict) else str(enemy)
                    names.append(enemy_name)
                    slug = character_slug(enemy_name)
                    asset_slug = slug if slug in enemy_slugs else "hilichurl"
                    assets.append({
                        "name": enemy_name,
                        "image_url": f"{API_BASE_URL}/enemies/{asset_slug}/icon",
                    })
                chamber[half_key] = names
        floor["enemy_assets"] = assets
        floor["layout_image_url"] = assets[0]["image_url"] if assets else f"{API_BASE_URL}/enemies/hilichurl/icon"
    payload["teams"] = payload.get("teams") or suggest_abyss_teams(payload)
    return payload


@app.get("/api/abyss")
@app.get("/api/abyss/all-floors")
@limiter.limit("10/minute")
async def abyss_matrix(request: Request):
    return stream_json(await load_abyss_feed())


@app.get("/api/abyss/floor12")
@limiter.limit("10/minute")
async def abyss_floor12(request: Request):
    payload = await load_abyss_feed()
    return stream_json(payload["floors"][11])


@app.get("/api/abyss/{floor_number}")
@limiter.limit("10/minute")
async def abyss_floor(request: Request, floor_number: int):
    if not 1 <= floor_number <= 12:
        raise HTTPException(status_code=404, detail="Abyss floor must be between 1 and 12.")
    payload = await load_abyss_feed()
    return stream_json(payload["floors"][floor_number - 1])


@app.get("/api/theater/current")
@limiter.limit("10/minute")
async def current_theater(request: Request):
    return stream_json(await load_theater_feed())


async def load_theater_feed() -> dict[str, Any]:
    payload = await fetch_provider_json(THEATER_DATA_URL, "Imaginarium Theater")
    if not isinstance(payload, dict):
        raise HTTPException(status_code=502, detail="Theater feed must return a JSON object.")
    return payload


@app.get("/characters/{character_name}")
@limiter.limit("10/minute")
async def get_character_details(request: Request, character_name: str):
    return stream_json(await load_character_details(character_name))


async def load_character_details(character_name: str) -> dict[str, Any]:
    slug = api_character_slug(character_name)
    try:
        cloud_slugs = await get_cloud_character_slugs()
    except HTTPException:
        raise

    if slug not in cloud_slugs:
        raise HTTPException(status_code=404, detail="Character is not in the archive.")

    try:
        api_data = await fetch_cloud_json(
            f"character:{slug}",
            f"characters/{slug}",
            force_refresh=True,
        )
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 404:
            raise HTTPException(status_code=404, detail="Character details are not available from the provider.") from exc
        raise HTTPException(status_code=502, detail="The cloud character service is unavailable.") from exc
    except (httpx.HTTPError, ValueError) as exc:
        raise HTTPException(status_code=502, detail="The cloud character service is unavailable.") from exc

    if not isinstance(api_data, dict):
        raise HTTPException(status_code=502, detail="The cloud character response is invalid.")

    return api_data | {
        "name": api_data.get("name") or display_name_for_slug(slug),
        "slug": slug,
        "element": api_data.get("vision", "Unknown"),
        "region": api_data.get("nation", "Unknown"),
        "icon_url": f"{CHARACTER_API_URL}/{slug}/icon",
        "source": "cloud",
    }


@app.get("/api/catalog/{category}")
@limiter.limit("10/minute")
async def get_catalog_category(request: Request, category: str):
    if category == "characters":
        return stream_json({"items": await get_character_mappings(), "source": "cloud"})
    if category == "banners":
        return stream_json(await get_live_banners())
    if category == "spiral-abyss":
        return stream_json(await load_abyss_feed())
    if category == "imaginarium-theater":
        return stream_json(await load_theater_feed())

    cloud_path = CLOUD_CATALOG_PATHS.get(category)
    if cloud_path is not None:
        try:
            payload = await fetch_cloud_json(
                f"catalog:{category}",
                cloud_path,
                force_refresh=True,
            )
        except (httpx.HTTPError, ValueError):
            raise HTTPException(status_code=502, detail=f"The live {category} catalog is unavailable.")
        items = [
            {
                "slug": str(item),
                "name": display_name_for_slug(str(item)),
                "icon_url": (
                    f"{API_BASE_URL}/artifacts/{item}/flower-of-life"
                    if category == "artifacts"
                    else f"{API_BASE_URL}/{cloud_path}/{item}/icon"
                ),
            }
            for item in payload
            if isinstance(item, str)
        ] if isinstance(payload, list) else []
        return stream_json({"items": items, "source": "cloud"})

    if category not in {
        "builds", "teams", "tierlist", "tcg", "tcg-best-decks",
        "leaderboard", "imaginarium-theater", "onslaught",
    }:
        raise HTTPException(status_code=404, detail="Unknown portal category.")
    return stream_json({"items": [], "source": "portal", "category": category})


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
        result["artifact_recommendations"] = character.get("artifact_sets", [])
        result["character_info"] = {
            "element": character.get("element"),
            "weapon": character.get("weapon"),
            "rarity": character.get("rarity"),
            "role": character.get("role", "Provider data unavailable"),
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


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 8000)),
        server_header=False,
        reload=False,
    )
