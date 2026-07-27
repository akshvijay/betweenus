"""Vercel Python Runtime Handler for BetweenUs API"""
import json
import os
import sqlite3
import time
import uuid
import hashlib
import hmac
import base64
from urllib.parse import parse_qs, urlparse
from datetime import datetime, timedelta

# Database in Vercel tmp directory
DB_PATH = "/tmp/betweenus.db"
JWT_SECRET = os.environ.get("JWT_SECRET", "betweenus-secret-key-change-in-production")

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    conn.executescript("""
      CREATE TABLE IF NOT EXISTS users (id TEXT PRIMARY KEY, email TEXT UNIQUE, password_hash TEXT, created_at INTEGER);
      CREATE TABLE IF NOT EXISTS sessions (token TEXT PRIMARY KEY, user_id TEXT, created_at INTEGER, FOREIGN KEY(user_id) REFERENCES users(id));
      CREATE TABLE IF NOT EXISTS posts (id TEXT PRIMARY KEY, body TEXT, need TEXT, category TEXT, created_at INTEGER, author_session TEXT DEFAULT '', author_user_id TEXT);
      CREATE TABLE IF NOT EXISTS relates (post_id TEXT, session TEXT, user_id TEXT, PRIMARY KEY(post_id, session, user_id));
      CREATE TABLE IF NOT EXISTS queue (ticket TEXT PRIMARY KEY, session TEXT, user_id TEXT, created_at INTEGER, status TEXT, room TEXT);
      CREATE TABLE IF NOT EXISTS rooms (id TEXT PRIMARY KEY, first_session TEXT, first_user_id TEXT, second_session TEXT, second_user_id TEXT, created_at INTEGER);
      CREATE TABLE IF NOT EXISTS messages (id TEXT PRIMARY KEY, room TEXT, sender TEXT, sender_user_id TEXT, body TEXT, created_at INTEGER);
      CREATE TABLE IF NOT EXISTS reports (id TEXT PRIMARY KEY, session TEXT, room TEXT, reason TEXT, created_at INTEGER);
      CREATE TABLE IF NOT EXISTS blocks (session TEXT, blocked_session TEXT, created_at INTEGER, PRIMARY KEY(session, blocked_session));
      CREATE TABLE IF NOT EXISTS notifications (id TEXT PRIMARY KEY, recipient TEXT, actor TEXT, post_id TEXT, kind TEXT, message TEXT, created_at INTEGER, read_at INTEGER);
      CREATE TABLE IF NOT EXISTS invitations (id TEXT PRIMARY KEY, post_id TEXT, sender TEXT, recipient TEXT, status TEXT, room TEXT, created_at INTEGER);
    """)
    try:
        conn.execute("ALTER TABLE posts ADD COLUMN author_user_id TEXT")
    except sqlite3.OperationalError:
        pass
    try:
        conn.execute("ALTER TABLE relates ADD COLUMN user_id TEXT")
    except sqlite3.OperationalError:
        pass
    try:
        conn.execute("ALTER TABLE queue ADD COLUMN user_id TEXT")
    except sqlite3.OperationalError:
        pass
    try:
        conn.execute("ALTER TABLE rooms ADD COLUMN first_user_id TEXT")
    except sqlite3.OperationalError:
        pass
    try:
        conn.execute("ALTER TABLE rooms ADD COLUMN second_user_id TEXT")
    except sqlite3.OperationalError:
        pass
    try:
        conn.execute("ALTER TABLE messages ADD COLUMN sender_user_id TEXT")
    except sqlite3.OperationalError:
        pass
    try:
        conn.execute("CREATE TABLE IF NOT EXISTS users (id TEXT PRIMARY KEY, email TEXT UNIQUE, password_hash TEXT, created_at INTEGER)")
    except sqlite3.OperationalError:
        pass
    try:
        conn.execute("CREATE TABLE IF NOT EXISTS sessions (token TEXT PRIMARY KEY, user_id TEXT, created_at INTEGER, FOREIGN KEY(user_id) REFERENCES users(id))")
    except sqlite3.OperationalError:
        pass
    
    if not conn.execute("SELECT 1 FROM posts LIMIT 1").fetchone():
        now = int(time.time())
        seeds = [
          ("seed-1", "I feel like everyone around me is moving forward while I'm just stuck.", "I want someone who relates", "feeling stuck", now-720, 27),
          ("seed-2", "I miss who I was before I started worrying about everything.", "I just want to vent", "college", now-1680, 14),
          ("seed-3", "I have people around me, but I don't feel known by any of them.", "I want to talk", "loneliness", now-3600, 41),
          ("seed-4", "I keep making myself smaller to make space for everyone else.", "I want someone to listen", "relationships", now-7200, 33),
        ]
        for pid, body, need, category, created, relates in seeds:
            conn.execute("INSERT INTO posts (id,body,need,category,created_at,author_session,author_user_id) VALUES(?,?,?,?,?,?,NULL)", (pid, body, need, category, created, ""))
            for i in range(relates):
                conn.execute("INSERT INTO relates VALUES(?,?,NULL)", (pid, f"seed-person-{pid}-{i}"))
    conn.commit()
    conn.close()

def clean(value, limit=500):
    return str(value or "").strip()[:limit]

def hash_password(password):
    """Hash password using SHA256"""
    return hashlib.sha256(password.encode()).hexdigest()

def create_jwt(user_id, expires_in=2592000):
    """Create a simple JWT token (30 days)"""
    now = int(time.time())
    exp = now + expires_in
    header = base64.urlsafe_b64encode(json.dumps({"alg": "HS256", "typ": "JWT"}).encode()).decode().rstrip("=")
    payload = base64.urlsafe_b64encode(json.dumps({"sub": user_id, "iat": now, "exp": exp}).encode()).decode().rstrip("=")
    signature = base64.urlsafe_b64encode(hmac.new(JWT_SECRET.encode(), f"{header}.{payload}".encode(), hashlib.sha256).digest()).decode().rstrip("=")
    return f"{header}.{payload}.{signature}"

def verify_jwt(token):
    """Verify JWT token and extract user_id"""
    try:
        parts = token.split(".")
        if len(parts) != 3:
            return None
        header, payload, signature = parts
        # Verify signature
        expected_sig = base64.urlsafe_b64encode(hmac.new(JWT_SECRET.encode(), f"{header}.{payload}".encode(), hashlib.sha256).digest()).decode().rstrip("=")
        if signature != expected_sig:
            return None
        # Decode payload
        payload_decoded = json.loads(base64.urlsafe_b64decode(payload + "=="))
        if payload_decoded["exp"] < int(time.time()):
            return None
        return payload_decoded["sub"]
    except:
        return None

def get_session_token(req, body):
    """Extract session token from query params or request body"""
    token = None
    # Try URL query params
    query_str = urlparse(req.url or "").query if hasattr(req, 'url') else ""
    query = parse_qs(query_str)
    if 'session' in query:
        token = query['session'][0]
    # Try request body
    if not token and body and isinstance(body, dict):
        token = body.get('session')
    
    if token:
        try:
            conn = get_db()
            valid = conn.execute("SELECT 1 FROM sessions WHERE token=?", (token,)).fetchone()
            conn.close()
            return token if valid else None
        except Exception as e:
            return None
    return None

def json_response(data, status=200):
    return {
        "statusCode": status,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type, Authorization"
        },
        "body": json.dumps(data)
    }

def signup(data):
    """Create new user account"""
    email = clean(data.get("email", ""), 255)
    password = data.get("password", "")
    
    if not email or "@" not in email:
        return json_response({"error": "Valid email required"}, 400)
    if len(password) < 6:
        return json_response({"error": "Password must be at least 6 characters"}, 400)
    
    user_id = str(uuid.uuid4())
    password_hash = hash_password(password)
    
    conn = get_db()
    try:
        conn.execute("INSERT INTO users VALUES(?,?,?,?)", (user_id, email, password_hash, int(time.time())))
        conn.commit()
        conn.close()
        token = create_jwt(user_id)
        return json_response({"user_id": user_id, "email": email, "token": token}, 201)
    except sqlite3.IntegrityError:
        conn.close()
        return json_response({"error": "Email already registered"}, 400)

def login(data):
    """Login user and return JWT token"""
    email = clean(data.get("email", ""), 255)
    password = data.get("password", "")
    
    if not email or not password:
        return json_response({"error": "Email and password required"}, 400)
    
    password_hash = hash_password(password)
    conn = get_db()
    user = conn.execute("SELECT id, email FROM users WHERE email=? AND password_hash=?", (email, password_hash)).fetchone()
    conn.close()
    
    if not user:
        return json_response({"error": "Invalid email or password"}, 401)
    
    token = create_jwt(user["id"])
    return json_response({"user_id": user["id"], "email": user["email"], "token": token}, 200)

def get_history(user_id):
    """Get user's chat history"""
    if not user_id:
        return json_response({"error": "Not authenticated"}, 401)
    
    conn = get_db()
    # Get all rooms where user participated
    rooms = conn.execute("""
        SELECT id, first_session, second_session, created_at 
        FROM rooms 
        WHERE first_user_id=? OR second_user_id=?
        ORDER BY created_at DESC
    """, (user_id, user_id)).fetchall()
    
    history = []
    for room in rooms:
        messages = conn.execute("""
            SELECT id, sender, body, created_at 
            FROM messages 
            WHERE room=? 
            ORDER BY created_at
        """, (room["id"],)).fetchall()
        
        history.append({
            "room_id": room["id"],
            "created_at": room["created_at"],
            "message_count": len(messages),
            "messages": [dict(m) for m in messages]
        })
    
    conn.close()
    return json_response({"history": history})

def posts_get():
    conn = get_db()
    rows = conn.execute("SELECT p.*, COUNT(r.post_id) relates FROM posts p LEFT JOIN relates r ON r.post_id=p.id GROUP BY p.id ORDER BY p.created_at DESC LIMIT 40").fetchall()
    conn.close()
    return json_response({"posts": [dict(r) for r in rows], "now": int(time.time())})

def session_create():
    token = str(uuid.uuid4())
    conn = get_db()
    try:
        conn.execute("INSERT INTO sessions VALUES(?,?,?)", (token, None, int(time.time())))
        conn.commit()
    except Exception as e:
        conn.close()
        return json_response({"error": f"Failed to create session: {str(e)}"}, 500)
    conn.close()
    return json_response({"session": token})

def posts_create(token, data):
    body = clean(data.get("body", ""))
    if len(body) < 3:
        return json_response({"error": "A few words is enough."}, 400)
    row = {
        "id": str(uuid.uuid4()),
        "body": body,
        "need": clean(data.get("need", ""), 80),
        "category": clean(data.get("category", ""), 40),
        "created_at": int(time.time()),
        "author_session": token
    }
    conn = get_db()
    try:
        conn.execute("INSERT INTO posts (id,body,need,category,created_at,author_session) VALUES(:id,:body,:need,:category,:created_at,:author_session)", row)
        conn.commit()
    except Exception as e:
        conn.close()
        return json_response({"error": f"Failed to create post: {str(e)}"}, 500)
    conn.close()
    row["relates"] = 0
    return json_response({"post": row}, 201)

def relate(token, pid):
    conn = get_db()
    exists = conn.execute("SELECT 1 FROM relates WHERE post_id=? AND session=?", (pid, token)).fetchone()
    if exists:
        conn.execute("DELETE FROM relates WHERE post_id=? AND session=?", (pid, token))
        active = False
    else:
        conn.execute("INSERT OR IGNORE INTO relates VALUES(?,?,?)", (pid, token, None))
        active = True
        post = conn.execute("SELECT author_session FROM posts WHERE id=?", (pid,)).fetchone()
        if post and post['author_session'] and post['author_session'] != token:
            conn.execute("INSERT INTO notifications VALUES(?,?,?,?,?,?,?,NULL)", (str(uuid.uuid4()), post['author_session'], token, pid, 'relate', 'Someone relates to something you shared.', int(time.time())))
    total = conn.execute("SELECT COUNT(*) FROM relates WHERE post_id=?", (pid,)).fetchone()[0]
    conn.commit()
    conn.close()
    return json_response({"active": active, "relates": total})

def interest(token, pid):
    conn = get_db()
    post = conn.execute("SELECT author_session FROM posts WHERE id=?", (pid,)).fetchone()
    if not post:
        conn.close()
        return json_response({"error": "Thought not found"}, 404)
    if post['author_session'] and post['author_session'] != token:
        old = conn.execute("SELECT * FROM invitations WHERE post_id=? AND sender=? AND status='pending'", (pid, token)).fetchone()
        if old:
            conn.close()
            return json_response({"ok": True, "invitation": dict(old)})
        invite = {"id": str(uuid.uuid4()), "post_id": pid, "sender": token, "recipient": post['author_session'], "status": "pending", "room": None, "created_at": int(time.time())}
        conn.execute("INSERT INTO invitations VALUES(:id,:post_id,:sender,:recipient,:status,:room,:created_at)", invite)
        conn.execute("INSERT INTO notifications VALUES(?,?,?,?,?,?,?,NULL)", (str(uuid.uuid4()), post['author_session'], token, pid, 'talk', 'Someone relates and wants to talk anonymously.', int(time.time())))
        conn.commit()
        conn.close()
        return json_response({"ok": True, "invitation": invite})
    conn.close()
    return json_response({"ok": True, "invitation": None})

def notifications_get(token):
    if not token:
        return json_response({"error": "Session required"}, 401)
    conn = get_db()
    rows = conn.execute("SELECT id,kind,message,created_at FROM notifications WHERE recipient=? ORDER BY created_at DESC LIMIT 10", (token,)).fetchall()
    conn.close()
    return json_response({"notifications": [dict(r) for r in rows]})

def invitations_get(token):
    if not token:
        return json_response({"error": "Session required"}, 401)
    conn = get_db()
    rows = conn.execute("SELECT * FROM invitations WHERE sender=? OR recipient=? ORDER BY created_at DESC LIMIT 20", (token, token)).fetchall()
    conn.close()
    return json_response({"invitations": [dict(r) for r in rows]})

def invitation_status(token, invite_id):
    if not token:
        return json_response({"error": "Session required"}, 401)
    conn = get_db()
    row = conn.execute("SELECT * FROM invitations WHERE id=? AND (sender=? OR recipient=?)", (invite_id, token, token)).fetchone()
    conn.close()
    if not row:
        return json_response({"error": "Invitation not found"}, 404)
    return json_response({"invitation": dict(row)})

def accept_invitation(token, invite_id):
    conn = get_db()
    invite = conn.execute("SELECT * FROM invitations WHERE id=? AND recipient=?", (invite_id, token)).fetchone()
    if not invite:
        conn.close()
        return json_response({"error": "Invitation unavailable"}, 404)
    if invite['status'] == 'accepted':
        conn.close()
        return json_response({"room": invite['room'], "status": "accepted"})
    if invite['status'] != 'pending':
        conn.close()
        return json_response({"error": "Invitation is no longer active"}, 409)
    room = str(uuid.uuid4())
    conn.execute("INSERT INTO rooms VALUES(?,?,?,?,?,?)", (room, invite['sender'], None, invite['recipient'], None, int(time.time())))
    conn.execute("UPDATE invitations SET status='accepted',room=? WHERE id=?", (room, invite_id))
    conn.commit()
    conn.close()
    return json_response({"room": room, "status": "accepted"})

def decline_invitation(token, invite_id):
    conn = get_db()
    conn.execute("UPDATE invitations SET status='declined' WHERE id=? AND recipient=? AND status='pending'", (invite_id, token))
    conn.commit()
    conn.close()
    return json_response({"ok": True})

def match(token):
    conn = get_db()
    now = int(time.time())
    conn.execute("DELETE FROM queue WHERE created_at<? AND status='waiting'", (now - 600,))
    waiting = conn.execute("SELECT * FROM queue WHERE status='waiting' AND session<>? ORDER BY created_at LIMIT 1", (token,)).fetchone()
    if waiting:
        room = str(uuid.uuid4())
        conn.execute("INSERT INTO rooms VALUES(?,?,?,?,?,?)", (room, waiting['session'], None, token, None, now))
        conn.execute("UPDATE queue SET status='matched', room=? WHERE ticket=?", (room, waiting['ticket']))
        ticket = str(uuid.uuid4())
        conn.execute("INSERT INTO queue VALUES(?,?,?,?,?,?)", (ticket, token, None, now, 'matched', room))
        conn.commit()
        conn.close()
        return json_response({"status": "matched", "room": room, "ticket": ticket})
    ticket = str(uuid.uuid4())
    conn.execute("INSERT INTO queue VALUES(?,?,?,?,?,?)", (ticket, token, None, now, 'waiting', None))
    conn.commit()
    conn.close()
    return json_response({"status": "waiting", "ticket": ticket})

def match_status(token, ticket):
    if not token:
        return json_response({"error": "Session required"}, 401)
    conn = get_db()
    row = conn.execute("SELECT * FROM queue WHERE ticket=? AND session=?", (ticket, token)).fetchone()
    conn.close()
    if not row:
        return json_response({"error": "Match not found"}, 404)
    return json_response({"status": row['status'], "ticket": ticket, "room": row['room']})

def allowed_room(token, room):
    conn = get_db()
    row = conn.execute("SELECT * FROM rooms WHERE id=? AND (first_session=? OR second_session=?)", (room, token, token)).fetchone()
    conn.close()
    return row

def chat_get(token, room):
    if not token or not allowed_room(token, room):
        return json_response({"error": "Conversation unavailable"}, 403)
    conn = get_db()
    rows = conn.execute("SELECT id,sender,body,created_at FROM messages WHERE room=? ORDER BY created_at,id", (room,)).fetchall()
    conn.close()
    return json_response({"messages": [dict(r) for r in rows]})

def chat_post(token, room, data):
    if not allowed_room(token, room):
        return json_response({"error": "Conversation unavailable"}, 403)
    body = clean(data.get("body", ""), 700)
    if not body:
        return json_response({"error": "Message is empty"}, 400)
    msg = {"id": str(uuid.uuid4()), "room": room, "sender": token, "sender_user_id": None, "body": body, "created_at": int(time.time())}
    conn = get_db()
    conn.execute("INSERT INTO messages VALUES(:id,:room,:sender,:sender_user_id,:body,:created_at)", msg)
    conn.commit()
    conn.close()
    return json_response({"message": msg}, 201)

def report(token, data):
    conn = get_db()
    conn.execute("INSERT INTO reports VALUES(?,?,?,?,?)", (str(uuid.uuid4()), token, clean(data.get("room", ""), 80), clean(data.get("reason", ""), 300), int(time.time())))
    conn.commit()
    conn.close()
    return json_response({"ok": True})

def block(token, data):
    room = clean(data.get("room", ""), 80)
    row = allowed_room(token, room)
    if not row:
        return json_response({"error": "Conversation unavailable"}, 403)
    other = row['second_session'] if row['first_session'] == token else row['first_session']
    conn = get_db()
    conn.execute("INSERT OR IGNORE INTO blocks VALUES(?,?,?)", (token, other, int(time.time())))
    conn.commit()
    conn.close()
    return json_response({"ok": True})

def handler(request):
    """Vercel Python handler"""
    init_db()
    
    method = request.method
    path = request.path
    
    # Handle CORS preflight
    if method == "OPTIONS":
        return json_response({}, 200)
    
    # Parse request body
    try:
        body = json.loads(request.get_data(as_text=True) or "{}")
    except:
        body = {}
    
    # Auth routes (no token required)
    if method == "POST" and path == "/api/auth/signup":
        return signup(body)
    if method == "POST" and path == "/api/auth/login":
        return login(body)
    
    # GET routes
    if method == "GET":
        if path == "/api/posts":
            return posts_get()
        if path == "/api/notifications":
            token = get_session_token(request, {})
            return notifications_get(token)
        if path == "/api/invitations":
            token = get_session_token(request, {})
            return invitations_get(token)
        if path == "/api/history":
            # Check for JWT token in Authorization header
            auth_header = request.headers.get("Authorization", "")
            jwt_token = auth_header.replace("Bearer ", "") if auth_header.startswith("Bearer ") else None
            user_id = verify_jwt(jwt_token) if jwt_token else None
            return get_history(user_id)
        if path.startswith("/api/invitations/"):
            token = get_session_token(request, {})
            invite_id = path.split("/")[-1]
            return invitation_status(token, invite_id)
        if path.startswith("/api/match/"):
            token = get_session_token(request, {})
            ticket = path.split("/")[-1]
            return match_status(token, ticket)
        if path.startswith("/api/chat/"):
            token = get_session_token(request, {})
            room = path.split("/")[-1]
            return chat_get(token, room)
    
    # POST routes
    elif method == "POST":
        if path == "/api/session":
            return session_create()
        
        token = get_session_token(request, body)
        if not token:
            return json_response({"error": "Session required"}, 401)
        
        if path == "/api/posts":
            return posts_create(token, body)
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
            room = path.split("/")[-1]
            return chat_post(token, room, body)
        if path == "/api/report":
            return report(token, body)
        if path == "/api/block":
            return block(token, body)
    
    return json_response({"error": "Not found"}, 404)
