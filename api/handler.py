"""Vercel serverless handler for BetweenUs API"""
import json
import os
import sqlite3
import time
import uuid
from pathlib import Path
from urllib.parse import parse_qs, urlparse

# Use /tmp for ephemeral database (Vercel limitation)
DB_PATH = "/tmp/betweenus.db"

def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    con = db()
    con.executescript("""
      CREATE TABLE IF NOT EXISTS sessions (token TEXT PRIMARY KEY, created_at INTEGER);
      CREATE TABLE IF NOT EXISTS posts (id TEXT PRIMARY KEY, body TEXT, need TEXT, category TEXT, created_at INTEGER, author_session TEXT DEFAULT '');
      CREATE TABLE IF NOT EXISTS relates (post_id TEXT, session TEXT, PRIMARY KEY(post_id, session));
      CREATE TABLE IF NOT EXISTS queue (ticket TEXT PRIMARY KEY, session TEXT, created_at INTEGER, status TEXT, room TEXT);
      CREATE TABLE IF NOT EXISTS rooms (id TEXT PRIMARY KEY, first_session TEXT, second_session TEXT, created_at INTEGER);
      CREATE TABLE IF NOT EXISTS messages (id TEXT PRIMARY KEY, room TEXT, sender TEXT, body TEXT, created_at INTEGER);
      CREATE TABLE IF NOT EXISTS reports (id TEXT PRIMARY KEY, session TEXT, room TEXT, reason TEXT, created_at INTEGER);
      CREATE TABLE IF NOT EXISTS blocks (session TEXT, blocked_session TEXT, created_at INTEGER, PRIMARY KEY(session, blocked_session));
      CREATE TABLE IF NOT EXISTS notifications (id TEXT PRIMARY KEY, recipient TEXT, actor TEXT, post_id TEXT, kind TEXT, message TEXT, created_at INTEGER, read_at INTEGER);
      CREATE TABLE IF NOT EXISTS invitations (id TEXT PRIMARY KEY, post_id TEXT, sender TEXT, recipient TEXT, status TEXT, room TEXT, created_at INTEGER);
    """)
    try: con.execute("ALTER TABLE posts ADD COLUMN author_session TEXT DEFAULT ''")
    except sqlite3.OperationalError: pass
    if not con.execute("SELECT 1 FROM posts LIMIT 1").fetchone():
        now = int(time.time())
        seeds = [
          ("seed-1", "I feel like everyone around me is moving forward while I'm just stuck.", "I want someone who relates", "feeling stuck", now-720, 27),
          ("seed-2", "I miss who I was before I started worrying about everything.", "I just want to vent", "college", now-1680, 14),
          ("seed-3", "I have people around me, but I don't feel known by any of them.", "I want to talk", "loneliness", now-3600, 41),
          ("seed-4", "I keep making myself smaller to make space for everyone else.", "I want someone to listen", "relationships", now-7200, 33),
        ]
        for pid, body, need, category, created, relates in seeds:
            con.execute("INSERT INTO posts (id,body,need,category,created_at,author_session) VALUES(?,?,?,?,?,?)", (pid, body, need, category, created, ""))
            for i in range(relates): con.execute("INSERT INTO relates VALUES(?,?)", (pid, f"seed-person-{pid}-{i}"))
    con.commit()
    con.close()

def clean(value, limit=500):
    return str(value or "").strip()[:limit]

def send_json(data, status=200):
    return {
        "statusCode": status,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(data)
    }

def get_session(headers, body_data):
    """Extract session token from query params or request body"""
    query = parse_qs(urlparse(headers.get("x-forwarded-url", "")).query)
    token = body_data.get("session") if body_data else None
    if not token:
        token = query.get("session", [""])[0] if query else ""
    if token:
        con = db()
        valid = con.execute("SELECT 1 FROM sessions WHERE token=?", (token,)).fetchone()
        con.close()
        return token if valid else None
    return None

# API Route Handlers
def posts(query):
    con = db()
    rows = con.execute("SELECT p.*, COUNT(r.post_id) relates FROM posts p LEFT JOIN relates r ON r.post_id=p.id GROUP BY p.id ORDER BY p.created_at DESC LIMIT 40").fetchall()
    con.close()
    return send_json({"posts": [dict(r) for r in rows], "now": int(time.time())})

def create_post(token, data):
    body = clean(data.get("body"))
    if len(body) < 3:
        return send_json({"error": "A few words is enough."}, 400)
    row = {"id": str(uuid.uuid4()), "body": body, "need": clean(data.get("need"), 80), "category": clean(data.get("category"), 40), "created_at": int(time.time()), "author_session": token}
    con = db()
    con.execute("INSERT INTO posts (id,body,need,category,created_at,author_session) VALUES(:id,:body,:need,:category,:created_at,:author_session)", row)
    con.commit()
    con.close()
    row["relates"] = 0
    return send_json({"post": row}, 201)

def relate(token, pid):
    con = db()
    exists = con.execute("SELECT 1 FROM relates WHERE post_id=? AND session=?", (pid, token)).fetchone()
    if exists:
        con.execute("DELETE FROM relates WHERE post_id=? AND session=?", (pid, token))
        active = False
    else:
        con.execute("INSERT OR IGNORE INTO relates VALUES(?,?)", (pid, token))
        active = True
        post = con.execute("SELECT author_session FROM posts WHERE id=?", (pid,)).fetchone()
        if post and post['author_session'] and post['author_session'] != token:
            con.execute("INSERT INTO notifications VALUES(?,?,?,?,?,?,?,NULL)", (str(uuid.uuid4()), post['author_session'], token, pid, 'relate', 'Someone relates to something you shared.', int(time.time())))
    total = con.execute("SELECT COUNT(*) FROM relates WHERE post_id=?", (pid,)).fetchone()[0]
    con.commit()
    con.close()
    return send_json({"active": active, "relates": total})

def interest(token, pid):
    con = db()
    post = con.execute("SELECT author_session FROM posts WHERE id=?", (pid,)).fetchone()
    if not post:
        con.close()
        return send_json({"error": "Thought not found"}, 404)
    if post['author_session'] and post['author_session'] != token:
        old = con.execute("SELECT * FROM invitations WHERE post_id=? AND sender=? AND status='pending'", (pid, token)).fetchone()
        if old:
            con.close()
            return send_json({"ok": True, "invitation": dict(old)})
        invite = {"id": str(uuid.uuid4()), "post_id": pid, "sender": token, "recipient": post['author_session'], "status": "pending", "room": None, "created_at": int(time.time())}
        con.execute("INSERT INTO invitations VALUES(:id,:post_id,:sender,:recipient,:status,:room,:created_at)", invite)
        con.execute("INSERT INTO notifications VALUES(?,?,?,?,?,?,?,NULL)", (str(uuid.uuid4()), post['author_session'], token, pid, 'talk', 'Someone relates and wants to talk anonymously.', int(time.time())))
        con.commit()
        con.close()
        return send_json({"ok": True, "invitation": invite})
    con.close()
    return send_json({"ok": True, "invitation": None})

def notifications(token):
    if not token:
        return send_json({"error": "Anonymous session required"}, 401)
    con = db()
    rows = con.execute("SELECT id,kind,message,created_at FROM notifications WHERE recipient=? ORDER BY created_at DESC LIMIT 10", (token,)).fetchall()
    con.close()
    return send_json({"notifications": [dict(r) for r in rows]})

def invitations(token):
    if not token:
        return send_json({"error": "Anonymous session required"}, 401)
    con = db()
    rows = con.execute("SELECT * FROM invitations WHERE sender=? OR recipient=? ORDER BY created_at DESC LIMIT 20", (token, token)).fetchall()
    con.close()
    return send_json({"invitations": [dict(r) for r in rows]})

def invitation_status(token, invite_id):
    if not token:
        return send_json({"error": "Anonymous session required"}, 401)
    con = db()
    row = con.execute("SELECT * FROM invitations WHERE id=? AND (sender=? OR recipient=?)", (invite_id, token, token)).fetchone()
    con.close()
    if not row:
        return send_json({"error": "Invitation not found"}, 404)
    return send_json({"invitation": dict(row)})

def accept_invitation(token, invite_id):
    con = db()
    invite = con.execute("SELECT * FROM invitations WHERE id=? AND recipient=?", (invite_id, token)).fetchone()
    if not invite:
        con.close()
        return send_json({"error": "Invitation unavailable"}, 404)
    if invite['status'] == 'accepted':
        con.close()
        return send_json({"room": invite['room'], "status": "accepted"})
    if invite['status'] != 'pending':
        con.close()
        return send_json({"error": "Invitation is no longer active"}, 409)
    room = str(uuid.uuid4())
    con.execute("INSERT INTO rooms VALUES(?,?,?,?)", (room, invite['sender'], invite['recipient'], int(time.time())))
    con.execute("UPDATE invitations SET status='accepted',room=? WHERE id=?", (room, invite_id))
    con.commit()
    con.close()
    return send_json({"room": room, "status": "accepted"})

def decline_invitation(token, invite_id):
    con = db()
    con.execute("UPDATE invitations SET status='declined' WHERE id=? AND recipient=? AND status='pending'", (invite_id, token))
    con.commit()
    con.close()
    return send_json({"ok": True})

def match(token):
    con = db()
    now = int(time.time())
    con.execute("DELETE FROM queue WHERE created_at<? AND status='waiting'", (now - 600,))
    waiting = con.execute("SELECT * FROM queue WHERE status='waiting' AND session<>? ORDER BY created_at LIMIT 1", (token,)).fetchone()
    if waiting:
        room = str(uuid.uuid4())
        con.execute("INSERT INTO rooms VALUES(?,?,?,?)", (room, waiting['session'], token, now))
        con.execute("UPDATE queue SET status='matched', room=? WHERE ticket=?", (room, waiting['ticket']))
        ticket = str(uuid.uuid4())
        con.execute("INSERT INTO queue VALUES(?,?,?,?,?)", (ticket, token, now, 'matched', room))
        con.commit()
        con.close()
        return send_json({"status": "matched", "room": room, "ticket": ticket})
    ticket = str(uuid.uuid4())
    con.execute("INSERT INTO queue VALUES(?,?,?,?,?)", (ticket, token, now, 'waiting', None))
    con.commit()
    con.close()
    return send_json({"status": "waiting", "ticket": ticket})

def match_status(token, ticket):
    if not token:
        return send_json({"error": "Anonymous session required"}, 401)
    con = db()
    row = con.execute("SELECT * FROM queue WHERE ticket=? AND session=?", (ticket, token)).fetchone()
    con.close()
    if not row:
        return send_json({"error": "Match not found"}, 404)
    return send_json({"status": row['status'], "ticket": ticket, "room": row['room']})

def allowed_room(token, room):
    con = db()
    row = con.execute("SELECT * FROM rooms WHERE id=? AND (first_session=? OR second_session=?)", (room, token, token)).fetchone()
    con.close()
    return row

def chat(token, room):
    if not token or not allowed_room(token, room):
        return send_json({"error": "Conversation unavailable"}, 403)
    con = db()
    rows = con.execute("SELECT id,sender,body,created_at FROM messages WHERE room=? ORDER BY created_at,id", (room,)).fetchall()
    con.close()
    return send_json({"messages": [dict(r) for r in rows]})

def send_chat(token, room, data):
    if not allowed_room(token, room):
        return send_json({"error": "Conversation unavailable"}, 403)
    body = clean(data.get("body"), 700)
    if not body:
        return send_json({"error": "Message is empty"}, 400)
    msg = {"id": str(uuid.uuid4()), "room": room, "sender": token, "body": body, "created_at": int(time.time())}
    con = db()
    con.execute("INSERT INTO messages VALUES(:id,:room,:sender,:body,:created_at)", msg)
    con.commit()
    con.close()
    return send_json({"message": msg}, 201)

def report(token, data):
    con = db()
    con.execute("INSERT INTO reports VALUES(?,?,?,?,?)", (str(uuid.uuid4()), token, clean(data.get("room"), 80), clean(data.get("reason"), 300), int(time.time())))
    con.commit()
    con.close()
    return send_json({"ok": True})

def block(token, data):
    room = clean(data.get("room"), 80)
    row = allowed_room(token, room)
    if not row:
        return send_json({"error": "Conversation unavailable"}, 403)
    other = row['second_session'] if row['first_session'] == token else row['first_session']
    con = db()
    con.execute("INSERT OR IGNORE INTO blocks VALUES(?,?,?)", (token, other, int(time.time())))
    con.commit()
    con.close()
    return send_json({"ok": True})

def handler(request):
    """Main Vercel handler function"""
    init_db()
    
    method = request.method
    path = request.path
    
    # Parse query and body
    query = parse_qs(urlparse(path).query) if request.url else {}
    try:
        body_data = json.loads(request.get_data(as_text=True) or "{}")
    except:
        body_data = {}
    
    # Extract session token
    token = get_session(request.headers, body_data) if method == "POST" else None
    
    # Route handling
    if method == "POST":
        if path == "/api/session":
            token = str(uuid.uuid4())
            con = db()
            con.execute("INSERT INTO sessions VALUES(?,?)", (token, int(time.time())))
            con.commit()
            con.close()
            return send_json({"session": token})
        
        if not token:
            return send_json({"error": "Anonymous session required"}, 401)
        
        if path == "/api/posts":
            return create_post(token, body_data)
        if path.startswith("/api/posts/") and path.endswith("/relate"):
            pid = path.split("/")[3]
            return relate(token, pid)
        if path.startswith("/api/posts/") and path.endswith("/interest"):
            pid = path.split("/")[3]
            return interest(token, pid)
        if path.startswith("/api/invitations/") and path.endswith("/accept"):
            invite_id = path.split("/")[3]
            return accept_invitation(token, invite_id)
        if path.startswith("/api/invitations/") and path.endswith("/decline"):
            invite_id = path.split("/")[3]
            return decline_invitation(token, invite_id)
        if path == "/api/match":
            return match(token)
        if path.startswith("/api/chat/"):
            room = path.rsplit("/", 1)[-1]
            return send_chat(token, room, body_data)
        if path == "/api/report":
            return report(token, body_data)
        if path == "/api/block":
            return block(token, body_data)
    
    elif method == "GET":
        if path == "/api/posts":
            return posts(query)
        if path == "/api/notifications":
            token = get_session(request.headers, {})
            return notifications(token)
        if path == "/api/invitations":
            token = get_session(request.headers, {})
            return invitations(token)
        if path.startswith("/api/invitations/"):
            invite_id = path.rsplit("/", 1)[-1]
            token = get_session(request.headers, {})
            return invitation_status(token, invite_id)
        if path.startswith("/api/match/"):
            ticket = path.rsplit("/", 1)[-1]
            token = get_session(request.headers, {})
            return match_status(token, ticket)
        if path.startswith("/api/chat/"):
            room = path.rsplit("/", 1)[-1]
            token = get_session(request.headers, {})
            return chat(token, room)
    
    return send_json({"error": "Not found"}, 404)
