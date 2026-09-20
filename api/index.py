"""
Dallas Stars Pick'em - Vercel Serverless API (Supabase version)
"""
import os, re, json
from datetime import datetime
from typing import Optional, Dict
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from supabase import create_client, Client

# --- Supabase Config ---
SUPABASE_URL = os.environ.get("SUPABASE_URL", "https://fnosqjpdvqzwiqfckowf.supabase.co")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImZub3NxanBkdnF6d2lxZmNrb3dmIiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODkyNzYwMjUsImV4cCI6MjEwNDg1MjAyNX0.iDD-ymzz3d4fM20LeBg5R_Z7sEqiVs1eCzUfkoCHNY4")
supabase: Client = None
seasonLocked = False
seasonLockMsg = ""

def get_supabase():
    global supabase
    if supabase is None and SUPABASE_URL and SUPABASE_KEY:
        supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
    return supabase

def check_season_locked(sb=None):
    """Check if any Dallas Stars game has started or finished"""
    global seasonLocked, seasonLockMsg
    if seasonLocked:
        return {"locked": True, "message": seasonLockMsg}
    if sb is None:
        sb = get_supabase()
    if sb:
        try:
            resp = sb.table("game_results").select("game_idx, status").neq("status", "").execute()
            if resp.data and any(r["status"] in ("FINAL", "LIVE", "CRIT") for r in resp.data):
                seasonLocked = True
                seasonLockMsg = "🔒 Season locked! Picks can no longer be changed."
                return {"locked": True, "message": seasonLockMsg}
        except:
            pass
    # Also check via NHL API if no results in DB yet
    try:
        import urllib.request, json
        for week in ['2026-09-19','2026-09-26','2026-10-03','2026-10-10']:
            req = urllib.request.Request(f"https://api-web.nhle.com/v1/schedule/{week}")
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read())
            for g in data.get("games", []):
                if g.get("homeTeam", {}).get("abbrev") == "DAL" or g.get("awayTeam", {}).get("abbrev") == "DAL":
                    if g.get("gameState") in ("LIVE", "FINAL", "CRIT"):
                        seasonLocked = True
                        seasonLockMsg = "🔒 Season locked! Picks can no longer be changed."
                        return {"locked": True, "message": seasonLockMsg}
    except:
        pass
    return {"locked": False, "message": ""}

# --- FastAPI App (routes without /api prefix - Vercel handles that) ---
app = FastAPI(title="Dallas Stars Pick'em")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# --- Models ---
class RegisterData(BaseModel):
    username: str
    phone: Optional[str] = ""

class SavePicksData(BaseModel):
    username: str
    picks: Dict[str, str]

# --- API Routes ---
@app.get("/api/leaderboard")
@app.get("/leaderboard")
def leaderboard():
    sb = get_supabase()
    if not sb:
        raise HTTPException(503, "Database not configured")
    
    users_resp = sb.table("users").select("username, phone").execute()
    users = users_resp.data if users_resp.data else []
    
    results_resp = sb.table("game_results").select("game_idx, winner").filter("status", "eq", "FINAL").execute()
    results = {r["game_idx"]: r["winner"] for r in (results_resp.data or [])}
    
    picks_resp = sb.table("picks").select("username, game_idx, pick").execute()
    picks_data = picks_resp.data if picks_resp.data else []
    
    user_picks_map = {}
    for p in picks_data:
        user_picks_map.setdefault(p["username"], []).append((p["game_idx"], p["pick"]))
    
    leaderboard = []
    for u in users:
        user_picks = user_picks_map.get(u["username"], [])
        correct = 0; wrong = 0
        for gidx, pick in user_picks:
            if gidx in results:
                winner = results[gidx]
                dal_win = winner == 'DAL'
                opp_win = winner not in ('DAL', 'TIE', '')
                if (pick == 'dal' and dal_win) or (pick == 'opp' and opp_win):
                    correct += 1
                elif dal_win or opp_win:
                    wrong += 1
        played = correct + wrong
        pct = round((correct / played * 100), 1) if played > 0 else 0
        leaderboard.append({
            'username': u["username"], 'phone': u.get("phone", "") or '',
            'correct': correct, 'wrong': wrong, 'played': played,
            'pct': pct, 'total_picks': len(user_picks)
        })
    
    leaderboard.sort(key=lambda x: (-x['correct'], -x['pct']))
    for i, entry in enumerate(leaderboard):
        entry['rank'] = i + 1
    return {'leaderboard': leaderboard}

@app.get("/api/user/{username_param}")
@app.get("/user/{username_param}")
def get_user(username_param: str):
    sb = get_supabase()
    if not sb:
        raise HTTPException(503, "Database not configured")
    
    picks_resp = sb.table("picks").select("game_idx, pick").filter("username", "eq", username_param).execute()
    picks_dict = {str(p["game_idx"]): p["pick"] for p in (picks_resp.data or [])}
    
    user_resp = sb.table("users").select("phone").filter("username", "eq", username_param).execute()
    phone = user_resp.data[0]["phone"] if user_resp.data else ""
    
    return {'username': username_param, 'phone': phone or '', 'picks': picks_dict}

@app.get("/api/users")
@app.get("/users")
def get_users():
    sb = get_supabase()
    if not sb:
        raise HTTPException(503, "Database not configured")
    
    resp = sb.table("users").select("username, phone").order("username").execute()
    users = [{'username': u["username"], 'phone': u.get("phone", "") or ''} for u in (resp.data or [])]
    return {'users': users}

@app.get("/api/results")
@app.get("/results")
def get_results():
    sb = get_supabase()
    if not sb:
        raise HTTPException(503, "Database not configured")
    
    resp = sb.table("game_results").select("game_idx, winner, home_score, away_score, status").execute()
    results = {}
    for r in (resp.data or []):
        results[str(r["game_idx"])] = {
            'winner': r["winner"], 'homeScore': r["home_score"],
            'awayScore': r["away_score"], 'status': r["status"]
        }
    return {'results': results}

@app.post("/api/register")
@app.post("/register")
def register(data: RegisterData):
    sb = get_supabase()
    if not sb:
        raise HTTPException(503, "Database not configured")
    
    username = data.username.strip()
    phone = data.phone.strip() if data.phone else ""
    if not username:
        raise HTTPException(400, 'Username required')
    if not re.match(r'^[a-zA-Z0-9_-]{1,20}$', username):
        raise HTTPException(400, 'Invalid username')
    
    now = datetime.now().isoformat()
    sb.table("users").upsert(
        {"username": username, "phone": phone, "created_at": now},
        on_conflict="username"
    ).execute()
    
    return {'status': 'ok', 'username': username}

@app.get("/api/season-status")
def season_status():
    """Check if the season is locked (any game has started/finished)"""
    return {"locked": seasonLocked, "message": seasonLockMsg}

@app.post("/api/save-picks")
@app.post("/save-picks")
def save_picks(data: SavePicksData):
    sb = get_supabase()
    if not sb:
        raise HTTPException(503, "Database not configured")
    
    username = data.username.strip()
    if not username:
        raise HTTPException(400, 'Username required')
    
    # Check if season is locked
    locked_info = check_season_locked(sb)
    if locked_info["locked"]:
        raise HTTPException(403, locked_info["message"])
    
    for game_idx, pick in data.picks.items():
        sb.table("picks").upsert(
            {"username": username, "game_idx": int(game_idx), "pick": pick},
            on_conflict="username,game_idx"
        ).execute()
    
    return {'status': 'ok', 'saved': len(data.picks)}

@app.get("/health")
def health():
    return {"status": "ok"}

@app.post("/api/save-results")
@app.post("/save-results")
def save_results(data: dict):
    sb = get_supabase()
    if not sb:
        raise HTTPException(503, "Database not configured")
    results = data.get("results", {})
    saved = 0
    for game_idx_str, result in results.items():
        try:
            game_idx = int(game_idx_str)
            sb.table("game_results").upsert({
                "game_idx": game_idx,
                "winner": result.get("winner", ""),
                "home_score": str(result.get("homeScore", "")),
                "away_score": str(result.get("awayScore", "")),
                "status": result.get("status", ""),
                "last_updated": datetime.now().isoformat()
            }, on_conflict="game_idx").execute()
            saved += 1
        except:
            pass
    return {"status": "ok", "saved": saved}

# Serve the HTML page
@app.get("/")
@app.get("/dallas-stars-schedule.html")
def serve_html():
    html_path = os.path.join(os.path.dirname(__file__), '..', 'dallas-stars-schedule.html')
    if not os.path.exists(html_path):
        html_path = os.path.join(os.path.dirname(__file__), 'dallas-stars-schedule.html')
    if not os.path.exists(html_path):
        raise HTTPException(404, "Page not found")
    with open(html_path) as f:
        return HTMLResponse(f.read())

# For Vercel - wrap with Mangum
from mangum import Mangum
handler = Mangum(app)
