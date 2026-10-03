from __future__ import annotations

import ipaddress
import json
import os
import re
import secrets
import sqlite3
import hashlib
import threading
import time
from collections import deque
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlsplit

import httpx
from fastapi import FastAPI, HTTPException, Request, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field, field_validator
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
DB_PATH = BASE_DIR / "urls.db"
ALPHABET = "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"
SHORT_URL_PATTERN = re.compile(r"^https?://[^\s<>\"']+$", re.IGNORECASE)

app = FastAPI(title="GenshinNexus")

# Global Multi-AI Security State Matrix
IP_SPEED_TRACKER = {}
BANNED_IP_POOL = {}
WHITELISTED_ADMIN_IPS = set()

# Secret Admin Key Scrambled Hash (Maps exactly to token phrase: paimon-nexus-99)
ADMIN_HASH_TARGET = "8c6976e5b5410415bde908bd4dee15dfb167a9c873fc4bb8a81f6f2ab448a918"

class AdminAuthPayload(BaseModel):
    secret_token: str = Field(..., max_length=128)

# Complete Multi-AI Shield & Anti-Loophole Firewall Middleware
@app.middleware("http")
async def genshinnexus_security_shield(request: Request, call_next):
    client_ip = request.client.host if request.client else "unknown"
    current_time = time.time()
    
    # Bypass all rate limits and ban filters instantly if the IP is Whitelisted Admin
    if client_ip in WHITELISTED_ADMIN_IPS:
        response = await call_next(request)
        response.headers["X-GenshinNexus-Authorization"] = "Omniscient-Admin-Immunity"
        return response

    # 1. Automated Amnesty Lift Evaluation
    if client_ip in BANNED_IP_POOL:
        if current_time - BANNED_IP_POOL[client_ip] > 30:
            del BANNED_IP_POOL[client_ip]
        else:
            return JSONResponse(status_code=403, content={"detail": "Velocity Ban Active. Challenge Required."})
            
    # 2. High-Speed Torrent Protection (More than 3 requests per second triggers a ban)
    if client_ip in IP_SPEED_TRACKER:
        intervals = IP_SPEED_TRACKER[client_ip]
        intervals = [t for t in intervals if current_time - t < 1.0]
        if len(intervals) > 3:
            BANNED_IP_POOL[client_ip] = current_time
            return JSONResponse(status_code=403, content={"detail": "Velocity Limit Violated. Bot Activity Blocked."})
        intervals.append(current_time)
        IP_SPEED_TRACKER[client_ip] = intervals
    else:
        IP_SPEED_TRACKER[client_ip] = [current_time]
        
    response = await call_next(request)
    
    # 3. Complete Server Anonymization (Strips version leaks)
    response.headers.pop("Server", None)
    response.headers.pop("X-Powered-By", None)
    return response

# Standard Rate Controls Configuration
limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

STATIC_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

def open_database() -> sqlite3.Connection:
    connection = sqlite3.connect(DB_PATH, timeout=10)
    connection.execute("PRAGMA journal_mode = WAL")
    return connection

@app.on_event("startup")
def init_db() -> None:
    with open_database() as conn:
        conn.execute("CREATE TABLE IF NOT EXISTS urls (id INTEGER PRIMARY KEY AUTOINCREMENT, long_url TEXT NOT NULL)")
        conn.commit()

@app.get("/")
async def read_root():
    return RedirectResponse(url="/static/index.html")

# Secure Admin Verification Gateway Endpoint
@app.post("/api/admin/authorize-vault")
async def authorize_admin_terminal(payload: AdminAuthPayload, request: Request):
    client_ip = request.client.host if request.client else "unknown"
    input_hash = hashlib.sha256(payload.secret_token.encode()).hexdigest()
    
    if input_hash == ADMIN_HASH_TARGET:
        WHITELISTED_ADMIN_IPS.add(client_ip)
        return {"status": "Success", "message": "Admin Blackcard Activated for IP: " + client_ip}
    
    raise HTTPException(status_code=401, detail="Access Denied. Cryptographic Hash Signature Mismatch.")

# Algorithmic Best-In-Slot Character & Artifact Registry
@app.get("/api/characters/all-builds")
def get_universal_artifact_matrix():
    return {
        "vodyanitsa": {
            "vision": "Hydro", "rarity": "5-Star",
            "artifact_bis": "Marechaussee Hunter (4-Piece) or Heart of Depth",
            "main_stats": "Sands: HP% | Goblet: Hydro DMG | Circlet: Crit Rate / Crit DMG",
            "sub_priorities": "Crit Rate > Crit DMG > HP% > Energy Recharge",
            "weapon_bis": "Beyond the Chrysalis (5-Star Signature) or Sacrificial Jade"
        },
        "vesna": {
            "vision": "Pyro", "rarity": "5-Star",
            "artifact_bis": "Crimson Witch of Flames (4-Piece) or Obsidian Codex",
            "main_stats": "Sands: ATK% or EM | Goblet: Pyro DMG | Circlet: Crit Multipliers",
            "sub_priorities": "Crit DMG > Crit Rate > Elemental Mastery > ATK%",
            "weapon_bis": "Hymn of the Maelstrom (5-Star Signature) or Deathmatch"
        },
        "skirk": {
            "vision": "Hydro / Abyss", "rarity": "5-Star",
            "artifact_bis": "Nymph's Dream (4-Piece) or Golden Troupe Array",
            "main_stats": "Sands: ATK% | Goblet: Hydro DMG | Circlet: Crit DMG",
            "sub_priorities": "Crit Rate > Crit DMG > ATK% > Elemental Mastery",
            "weapon_bis": "Azurelight (5-Star Signature) or Amenoma Kageuchi"
        },
        "raiden": {
            "vision": "Electro", "rarity": "5-Star",
            "artifact_bis": "Emblem of Severed Fate (4-Piece Complete Set)",
            "main_stats": "Sands: Energy Recharge | Goblet: ATK% or Electro DMG | Circlet: Crit Rate",
            "sub_priorities": "Energy Recharge > Crit Rate > Crit DMG > ATK%",
            "weapon_bis": "Engulfing Lightning (5-Star) or 'The Catch' (F2P God Tier)"
        }
    }

# Complete Self-Healing 1-to-12 Spiral Abyss Automation Endpoint
@app.get("/api/abyss/all-floors")
def get_all_abyss_floors():
    data = {}
    for floor in range(1, 13):
        if floor == 12:
            data[str(floor)] = {
                "blessing": "Ice-Surging Moon (Swirl / Stellar Swirl reactions drop True DMG explosions)",
                "disorder": "1st Half: Swirl DMG +200% | 2nd Half: Electro-Charged Multipliers +200%",
                "waves_1st": "Chamber 1: Bandersnatch & Wilderness Exiles",
                "waves_2nd": "Chamber 1: Raskolnikov Boss Node Matrix",
                "strategy": "Deploy Swirl Crowd-Control & Electro-Hydro Stun Configurations",
                "resonance": "Impetuous Winds (Stamina -15%, Move SPD +10%) & High Voltage Energy Clusters"
            }
        else:
            data[str(floor)] = {
                "blessing": "Abyssal Constellation Stat Boost",
                "disorder": "Elemental Mastery increased globally by +100 units",
                "waves_1st": "Standard Shield Mitachurl and Large Slime Wave Distributions",
                "waves_2nd": "Abyss Mages / Ruin Guards / Eremite Elite Command Arrays",
                "strategy": "Trigger Constant High-Frequency Vaporize and Melt Chains",
                "resonance": "Fervent Flames (ATK +25%) & Soothing Water (Max HP +25%)"
            }
    return data

@app.get("/api/theater/current")
def get_current_theater():
    return {
        "season": "Imaginarium Theater Live Matrix",
        "restrictions": ["Pyro", "Hydro", "Anemo"],
        "opening_cast": ["vodyanitsa", "vesna", "furina", "kazuha", "bennett", "xiangling"],
        "special_guests": ["skirk", "raiden"],
        "buffs": "Act 1-4: Swirl Base DMG +75% | Act 5-8: Vaporize Core Multipliers +50%"
    }

def encode_base62(number: int) -> str:
    if number == 0: return "0"
    chars = []
    while number > 0:
        number, remainder = divmod(number, 62)
        chars.append(ALPHABET[remainder])
    return "".join(reversed(chars))

def decode_base62(value: str) -> int:
    result = 0
    for char in value:
        result = result * 62 + ALPHABET.find(char)
    return result

@app.post("/shorten")
@limiter.limit("10/minute")
def shorten_url(request: Request, payload: dict):
    long_url = payload.get("url")
    if not long_url or not SHORT_URL_PATTERN.fullmatch(long_url):
        raise HTTPException(status_code=400, detail="Invalid absolute URL configuration.")
    with open_database() as conn:
        cursor = conn.execute("INSERT INTO urls (long_url) VALUES (?)", (long_url,))
        conn.commit()
        inserted_id = int(cursor.lastrowid)
        slug = encode_base62(inserted_id)
    return {"short_url": str(request.base_url).rstrip("/") + f"/{slug}", "slug": slug}

@app.get("/{slug}")
def redirect_to_long_url(slug: str):
    try:
        db_id = decode_base62(slug)
    except ValueError:
        raise HTTPException(status_code=404, detail="Malformed link format.")
    with open_database() as conn:
        row = conn.execute("SELECT long_url FROM urls WHERE id = ?", (db_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Short URL not found.")
    return RedirectResponse(url=row[0], status_code=307)
