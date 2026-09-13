-- Dallas Stars Pick'em - Supabase Schema
-- Run this in the Supabase SQL Editor (https://supabase.com/dashboard/project/_/sql/new)

-- Users table
CREATE TABLE IF NOT EXISTS users (
    username TEXT PRIMARY KEY,
    phone TEXT DEFAULT '',
    created_at TIMESTAMP DEFAULT NOW()
);

-- Picks table
CREATE TABLE IF NOT EXISTS picks (
    username TEXT NOT NULL REFERENCES users(username),
    game_idx INTEGER NOT NULL,
    pick TEXT NOT NULL,
    PRIMARY KEY (username, game_idx)
);

-- Game results table
CREATE TABLE IF NOT EXISTS game_results (
    game_idx INTEGER PRIMARY KEY,
    winner TEXT DEFAULT '',
    home_score TEXT DEFAULT '',
    away_score TEXT DEFAULT '',
    status TEXT DEFAULT '',
    last_updated TIMESTAMP DEFAULT NOW()
);

-- Enable Row Level Security (optional - we're using the service role key)
ALTER TABLE users ENABLE ROW LEVEL SECURITY;
ALTER TABLE picks ENABLE ROW LEVEL SECURITY;
ALTER TABLE game_results ENABLE ROW LEVEL SECURITY;

-- Allow public access for our API
CREATE POLICY "Public access" ON users FOR ALL USING (true);
CREATE POLICY "Public access" ON picks FOR ALL USING (true);
CREATE POLICY "Public access" ON game_results FOR ALL USING (true);
