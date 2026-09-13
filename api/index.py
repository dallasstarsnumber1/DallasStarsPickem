"""
Dallas Stars Pick'em - Vercel Serverless API (Supabase version)
"""
import os, re, json
from datetime import datetime
from typing import Optional, Dict
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel
from supabase import create_client, Client

# --- Supabase Config ---
SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")
supabase: Client = None

def get_supabase():
    global supabase
    if supabase is None and SUPABASE_URL and SUPABASE_KEY:
        supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
    return supabase

# --- FastAPI App ---
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
def leaderboard():
    sb = get_supabase()
    if not sb:
        raise HTTPException(503, "Database not configured")
    
    # Get all users
    users_resp = sb.table("users").select("username, phone").execute()
    users = users_resp.data if users_resp.data else []
    
    # Get game results
    results_resp = sb.table("game_results").select("game_idx, winner").filter("status", "eq", "FINAL").execute()
    results = {r["game_idx"]: r["winner"] for r in (results_resp.data or [])}
    
    # Get all picks
    picks_resp = sb.table("picks").select("username, game_idx, pick").execute()
    picks_data = picks_resp.data if picks_resp.data else []
    
    # Group picks by user
    user_picks_map = {}
    for p in picks_data:
        user_picks_map.setdefault(p["username"], []).append((p["game_idx"], p["pick"]))
    
    leaderboard = []
    for u in users:
        user_picks = user_picks_map.get(u["username"], [])
        correct = 0
        wrong = 0
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
            'username': u["username"],
            'phone': u.get("phone", "") or "",
            'correct': correct,
            'wrong': wrong,
            'played': played,
            'pct': pct,
            'total_picks': len(user_picks)
        })
    
    leaderboard.sort(key=lambda x: (-x['correct'], -x['pct']))
    for i, entry in enumerate(leaderboard):
        entry['rank'] = i + 1
    return {'leaderboard': leaderboard}

@app.get("/api/user/{username_param}")
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
def get_users():
    sb = get_supabase()
    if not sb:
        raise HTTPException(503, "Database not configured")
    
    resp = sb.table("users").select("username, phone").order("username").execute()
    users = [{'username': u["username"], 'phone': u.get("phone", "") or ''} for u in (resp.data or [])]
    return {'users': users}

@app.get("/api/results")
def get_results():
    sb = get_supabase()
    if not sb:
        raise HTTPException(503, "Database not configured")
    
    resp = sb.table("game_results").select("game_idx, winner, home_score, away_score, status").execute()
    results = {}
    for r in (resp.data or []):
        results[str(r["game_idx"])] = {
            'winner': r["winner"],
            'homeScore': r["home_score"],
            'awayScore': r["away_score"],
            'status': r["status"]
        }
    return {'results': results}

@app.post("/api/register")
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

@app.post("/api/save-picks")
def save_picks(data: SavePicksData):
    sb = get_supabase()
    if not sb:
        raise HTTPException(503, "Database not configured")
    
    username = data.username.strip()
    if not username:
        raise HTTPException(400, 'Username required')
    
    for game_idx, pick in data.picks.items():
        sb.table("picks").upsert(
            {"username": username, "game_idx": int(game_idx), "pick": pick},
            on_conflict="username,game_idx"
        ).execute()
    
    return {'status': 'ok', 'saved': len(data.picks)}

@app.get("/health")
def health():
    sb = get_supabase()
    db_status = "connected" if sb else "not configured"
    return {"status": "ok", "database": db_status}

# For Vercel serverless - this is needed
from mangum import Mangum
handler = Mangum(app)
