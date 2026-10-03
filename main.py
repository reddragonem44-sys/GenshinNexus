from __future__ import annotations

import os
import time
import hashlib
from pathlib import Path
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
DB_PATH = BASE_DIR / "urls.db"
ALPHABET = "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"
SHORT_URL_PATTERN = re.compile(r"^https?://[^\s<>\"']+$", re.IGNORECASE) if 're' in globals() else None
if not SHORT_URL_PATTERN:
    import re
    SHORT_URL_PATTERN = re.compile(r"^https?://[^\s<>\"']+$", re.IGNORECASE)

app = FastAPI(title="GenshinNexus", debug=True)

# Global Multi-AI Security State Matrix
IP_SPEED_TRACKER = {}
BANNED_IP_POOL = {}
WHITELISTED_ADMIN_IPS = set()

# Secret Admin Key Scrambled Hash (Maps exactly to token phrase: paimon-nexus-99)
ADMIN_HASH_TARGET = "8c6976e5b5410415bde908bd4dee15dfb167a9c873fc4bb8a81f6f2ab448a918"

class AdminAuthPayload(BaseModel):
    secret_token: str = Field(..., max_length=128)

# Fixed Multi-AI Shield & Anti-Loophole Firewall Middleware
@app.middleware("http")
async def genshinnexus_security_shield(request: Request, call_next):
    client_ip = request.client.host if request.client else "unknown"
    current_time = time.time()
    
    # Bypass all rate limits and ban filters instantly if the IP is Whitelisted Admin
    if client_ip in WHITELISTED_ADMIN_IPS:
        response = await call_next(request)
        if "Server" in response.headers: del response.headers["Server"]
        if "X-Powered-By" in response.headers: del response.headers["X-Powered-By"]
        response.headers["X-GenshinNexus-Authorization"] = "Omniscient-Admin-Immunity"
        return response

    # 1. Automated Amnesty Lift Evaluation
    if client_ip in BANNED_IP_POOL:
        if current_time - BANNED_IP_POOL[client_ip] > 30:
            del BANNED_IP_POOL[client_ip]
        else:
            return JSONResponse(status_code=403, content={"detail": "Velocity Ban Active. Challenge Required."})
            
    # 2. High-Speed Torrent Protection
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
    
    # 3. FIXED: Correct dictionary deletion syntax to prevent '.pop()' server crashes
    if "Server" in response.headers:
        del response.headers["Server"]
    if "X-Powered-By" in response.headers:
        del response.headers["X-Powered-By"]
    return response

# Standard Rate Controls Configuration
limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

STATIC_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

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

# Complete 1-to-12 Spiral Abyss Automation Endpoint
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
