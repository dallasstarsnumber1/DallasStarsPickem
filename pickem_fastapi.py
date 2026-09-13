#!/usr/bin/env python3
"""Dallas Stars Pick'em - FastAPI Backend Server"""
import json, sqlite3, os, re
from datetime import datetime
from pathlib import Path
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, Dict

# --- Config ---
DB_PATH = os.environ.get('PICKEM_DB', os.path.expanduser('~/.hermes/pickem.db'))
STATIC_DIR = os.environ.get('PICKEM_STATIC', os.path.expanduser('~'))
HOST = os.environ.get('HOST', '0.0.0.0')
PORT = int(os.environ.get('PORT', 8080))

app = FastAPI(title="Dallas Stars Pick'em")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# --- Database ---
def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users (
        username TEXT PRIMARY KEY, phone TEXT, created_at TEXT
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS picks (
        username TEXT, game_idx INTEGER, pick TEXT,
        PRIMARY KEY (username, game_idx)
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS game_results (
        game_idx INTEGER PRIMARY KEY, winner TEXT, home_score TEXT,
        away_score TEXT, status TEXT, last_updated TEXT
    )''')
    conn.commit()
    conn.close()

init_db()

# --- Models ---
class RegisterData(BaseModel):
    username: str
    phone: Optional[str] = ""

class SavePicksData(BaseModel):
    username: str
    picks: Dict[str, str]

# --- Helpers ---
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

# --- API Routes ---
@app.get("/api/leaderboard")
def leaderboard():
    conn = get_db()
    c = conn.cursor()
    c.execute('''SELECT u.username, u.phone, COUNT(p.game_idx) as total_picks
        FROM users u LEFT JOIN picks p ON u.username = p.username
        GROUP BY u.username''')
    users = c.fetchall()
    c.execute('SELECT game_idx, winner FROM game_results WHERE status = "FINAL"')
    results = {row["game_idx"]: row["winner"] for row in c.fetchall()}
    
    leaderboard = []
    for u in users:
        c.execute('SELECT game_idx, pick FROM picks WHERE username = ?', (u["username"],))
        user_picks = c.fetchall()
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
            'username': u["username"], 'phone': u["phone"] or '',
            'correct': correct, 'wrong': wrong, 'played': played,
            'pct': pct, 'total_picks': u["total_picks"]
        })
    conn.close()
    leaderboard.sort(key=lambda x: (-x['correct'], -x['pct']))
    for i, entry in enumerate(leaderboard):
        entry['rank'] = i + 1
    return {'leaderboard': leaderboard}

@app.get("/api/user/{username}")
def get_user(username: str):
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT game_idx, pick FROM picks WHERE username = ?', (username,))
    picks_dict = {str(row["game_idx"]): row["pick"] for row in c.fetchall()}
    c.execute('SELECT phone FROM users WHERE username = ?', (username,))
    user_row = c.fetchone()
    conn.close()
    return {'username': username, 'phone': user_row["phone"] if user_row else '', 'picks': picks_dict}

@app.get("/api/users")
def get_users():
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT username, phone FROM users ORDER BY username')
    users = [{'username': row["username"], 'phone': row["phone"] or ''} for row in c.fetchall()]
    conn.close()
    return {'users': users}

@app.get("/api/results")
def get_results():
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT game_idx, winner, home_score, away_score, status FROM game_results')
    results = {str(row["game_idx"]): {
        'winner': row["winner"], 'homeScore': row["home_score"],
        'awayScore': row["away_score"], 'status': row["status"]
    } for row in c.fetchall()}
    conn.close()
    return {'results': results}

@app.post("/api/register")
def register(data: RegisterData):
    username = data.username.strip()
    phone = data.phone.strip() if data.phone else ""
    if not username:
        raise HTTPException(400, 'Username required')
    if not re.match(r'^[a-zA-Z0-9_-]{1,20}$', username):
        raise HTTPException(400, 'Invalid username')
    conn = get_db()
    now = datetime.now().isoformat()
    conn.execute('INSERT OR REPLACE INTO users (username, phone, created_at) VALUES (?, ?, ?)',
                 (username, phone, now))
    conn.commit()
    conn.close()
    return {'status': 'ok', 'username': username}

@app.post("/api/save-picks")
def save_picks(data: SavePicksData):
    username = data.username.strip()
    if not username:
        raise HTTPException(400, 'Username required')
    conn = get_db()
    for game_idx, pick in data.picks.items():
        conn.execute('INSERT OR REPLACE INTO picks (username, game_idx, pick) VALUES (?, ?, ?)',
                     (username, int(game_idx), pick))
    conn.commit()
    conn.close()
    return {'status': 'ok', 'saved': len(data.picks)}

@app.get("/health")
def health():
    return {"status": "ok"}

# --- Serve Static Files (the HTML page + images) ---
HTML_FILE = os.path.join(STATIC_DIR, 'dallas-stars-schedule.html')
BG_FILE = os.path.join(STATIC_DIR, 'stars_bg.jpg')

@app.get("/", response_class=HTMLResponse)
@app.get("/dallas-stars-schedule.html", response_class=HTMLResponse)
def serve_html():
    path = HTML_FILE if os.path.exists(HTML_FILE) else os.path.join(STATIC_DIR, 'dallas-stars-schedule.html')
    if not os.path.exists(path):
        raise HTTPException(404, "Page not found")
    with open(path) as f:
        return f.read()

@app.get("/stars_bg.jpg")
def serve_bg():
    path = BG_FILE if os.path.exists(BG_FILE) else os.path.join(STATIC_DIR, 'stars_bg.jpg')
    if not os.path.exists(path):
        raise HTTPException(404, "Background not found")
    return FileResponse(path, media_type='image/jpeg')

# --- Main ---
if __name__ == '__main__':
    import uvicorn
    print(f"FastAPI Pick'em server running on http://localhost:{PORT}")
    uvicorn.run(app, host=HOST, port=PORT, log_level="warning")