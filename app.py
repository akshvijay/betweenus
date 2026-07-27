import os
import time
import uuid
from pathlib import Path

import psycopg2
from psycopg2.extras import RealDictCursor
from flask import Flask, jsonify, request, send_from_directory


ROOT = Path(__file__).parent

app = Flask(__name__, static_folder=None)


# =========================================================
# DATABASE
# =========================================================

def get_db():
    database_url = os.environ.get("DATABASE_URL")

    if not database_url:
        raise RuntimeError("DATABASE_URL is not configured")

    return psycopg2.connect(
        database_url,
        cursor_factory=RealDictCursor
    )


def clean(value, limit=500):
    return str(value or "").strip()[:limit]


# =========================================================
# SESSION
# =========================================================

def get_session(data=None):
    data = data or {}

    token = data.get("session") or request.args.get("session")

    if not token:
        return None

    conn = get_db()

    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT 1 FROM sessions WHERE token=%s",
                (token,)
            )

            exists = cur.fetchone()

        return token if exists else None

    finally:
        conn.close()


@app.post("/api/session")
def create_session():

    token = str(uuid.uuid4())

    conn = get_db()

    try:
        with conn.cursor() as cur:

            cur.execute(
                """
                INSERT INTO sessions
                (token, created_at)
                VALUES (%s, %s)
                """,
                (
                    token,
                    int(time.time())
                )
            )

        conn.commit()

    finally:
        conn.close()

    return jsonify({
        "session": token
    })


# =========================================================
# POSTS
# =========================================================

@app.get("/api/posts")
def get_posts():

    conn = get_db()

    try:

        with conn.cursor() as cur:

            cur.execute(
                """
                SELECT
                    p.*,
                    COUNT(r.post_id)::int AS relates

                FROM posts p

                LEFT JOIN relates r
                ON r.post_id = p.id

                GROUP BY p.id

                ORDER BY p.created_at DESC

                LIMIT 40
                """
            )

            posts = cur.fetchall()

    finally:
        conn.close()

    return jsonify({
        "posts": posts,
        "now": int(time.time())
    })


@app.post("/api/posts")
def create_post():

    data = request.get_json(silent=True) or {}

    token = get_session(data)

    if not token:
        return jsonify({
            "error": "Session required"
        }), 401

    body = clean(data.get("body"))

    if len(body) < 3:
        return jsonify({
            "error": "A few words is enough."
        }), 400

    post_id = str(uuid.uuid4())

    created_at = int(time.time())

    need = clean(
        data.get("need"),
        80
    )

    category = clean(
        data.get("category"),
        40
    )

    conn = get_db()

    try:

        with conn.cursor() as cur:

            cur.execute(
                """
                INSERT INTO posts
                (
                    id,
                    body,
                    need,
                    category,
                    created_at,
                    author_session
                )

                VALUES
                (%s,%s,%s,%s,%s,%s)
                """,
                (
                    post_id,
                    body,
                    need,
                    category,
                    created_at,
                    token
                )
            )

        conn.commit()

    finally:
        conn.close()

    return jsonify({
        "post": {
            "id": post_id,
            "body": body,
            "need": need,
            "category": category,
            "created_at": created_at,
            "author_session": token,
            "relates": 0
        }
    }), 201


# =========================================================
# RELATE
# =========================================================

@app.post("/api/posts/<post_id>/relate")
def relate(post_id):

    data = request.get_json(silent=True) or {}

    token = get_session(data)

    if not token:
        return jsonify({
            "error": "Session required"
        }), 401

    conn = get_db()

    try:

        with conn.cursor() as cur:

            cur.execute(
                """
                SELECT 1
                FROM relates
                WHERE post_id=%s
                AND session=%s
                """,
                (
                    post_id,
                    token
                )
            )

            exists = cur.fetchone()

            if exists:

                cur.execute(
                    """
                    DELETE FROM relates
                    WHERE post_id=%s
                    AND session=%s
                    """,
                    (
                        post_id,
                        token
                    )
                )

                active = False

            else:

                cur.execute(
                    """
                    INSERT INTO relates
                    (post_id, session)

                    VALUES (%s,%s)

                    ON CONFLICT DO NOTHING
                    """,
                    (
                        post_id,
                        token
                    )
                )

                active = True

            cur.execute(
                """
                SELECT COUNT(*)::int AS total
                FROM relates
                WHERE post_id=%s
                """,
                (post_id,)
            )

            total = cur.fetchone()["total"]

        conn.commit()

    finally:
        conn.close()

    return jsonify({
        "active": active,
        "relates": total
    })


# =========================================================
# INTEREST / TALK
# =========================================================

@app.post("/api/posts/<post_id>/interest")
def interest(post_id):

    data = request.get_json(silent=True) or {}

    token = get_session(data)

    if not token:
        return jsonify({
            "error": "Session required"
        }), 401

    conn = get_db()

    try:

        with conn.cursor() as cur:

            cur.execute(
                """
                SELECT author_session
                FROM posts
                WHERE id=%s
                """,
                (post_id,)
            )

            post = cur.fetchone()

            if not post:
                return jsonify({
                    "error": "Thought not found"
                }), 404

            recipient = post["author_session"]

            if not recipient or recipient == token:

                return jsonify({
                    "ok": True,
                    "invitation": None
                })

            cur.execute(
                """
                SELECT *
                FROM invitations

                WHERE post_id=%s
                AND sender=%s
                AND status='pending'
                """,
                (
                    post_id,
                    token
                )
            )

            existing = cur.fetchone()

            if existing:

                return jsonify({
                    "ok": True,
                    "invitation": existing
                })

            invitation_id = str(uuid.uuid4())

            created_at = int(time.time())

            cur.execute(
                """
                INSERT INTO invitations
                (
                    id,
                    post_id,
                    sender,
                    recipient,
                    status,
                    room,
                    created_at
                )

                VALUES
                (%s,%s,%s,%s,%s,%s,%s)
                """,
                (
                    invitation_id,
                    post_id,
                    token,
                    recipient,
                    "pending",
                    None,
                    created_at
                )
            )

            cur.execute(
                """
                INSERT INTO notifications
                (
                    id,
                    recipient,
                    actor,
                    post_id,
                    kind,
                    message,
                    created_at
                )

                VALUES
                (%s,%s,%s,%s,%s,%s,%s)
                """,
                (
                    str(uuid.uuid4()),
                    recipient,
                    token,
                    post_id,
                    "talk",
                    "Someone relates and wants to talk anonymously.",
                    created_at
                )
            )

        conn.commit()

    finally:
        conn.close()

    return jsonify({
        "ok": True,
        "invitation": {
            "id": invitation_id,
            "post_id": post_id,
            "sender": token,
            "recipient": recipient,
            "status": "pending",
            "room": None,
            "created_at": created_at
        }
    })


# =========================================================
# NOTIFICATIONS
# =========================================================

@app.get("/api/notifications")
def notifications():

    token = get_session()

    if not token:
        return jsonify({
            "error": "Session required"
        }), 401

    conn = get_db()

    try:

        with conn.cursor() as cur:

            cur.execute(
                """
                SELECT
                    id,
                    kind,
                    message,
                    created_at

                FROM notifications

                WHERE recipient=%s

                ORDER BY created_at DESC

                LIMIT 10
                """,
                (token,)
            )

            rows = cur.fetchall()

    finally:
        conn.close()

    return jsonify({
        "notifications": rows
    })


# =========================================================
# INVITATIONS
# =========================================================

@app.get("/api/invitations")
def invitations():

    token = get_session()

    if not token:
        return jsonify({
            "error": "Session required"
        }), 401

    conn = get_db()

    try:

        with conn.cursor() as cur:

            cur.execute(
                """
                SELECT *
                FROM invitations

                WHERE sender=%s
                OR recipient=%s

                ORDER BY created_at DESC

                LIMIT 20
                """,
                (
                    token,
                    token
                )
            )

            rows = cur.fetchall()

    finally:
        conn.close()

    return jsonify({
        "invitations": rows
    })


@app.get("/api/invitations/<invitation_id>")
def invitation_status(invitation_id):

    token = get_session()

    if not token:
        return jsonify({
            "error": "Session required"
        }), 401

    conn = get_db()

    try:

        with conn.cursor() as cur:

            cur.execute(
                """
                SELECT *
                FROM invitations

                WHERE id=%s

                AND
                (
                    sender=%s
                    OR recipient=%s
                )
                """,
                (
                    invitation_id,
                    token,
                    token
                )
            )

            invitation = cur.fetchone()

    finally:
        conn.close()

    if not invitation:

        return jsonify({
            "error": "Invitation not found"
        }), 404

    return jsonify({
        "invitation": invitation
    })


# =========================================================
# ACCEPT INVITATION
# =========================================================

@app.post("/api/invitations/<invitation_id>/accept")
def accept_invitation(invitation_id):

    data = request.get_json(silent=True) or {}

    token = get_session(data)

    if not token:

        return jsonify({
            "error": "Session required"
        }), 401

    conn = get_db()

    try:

        with conn.cursor() as cur:

            cur.execute(
                """
                SELECT *
                FROM invitations

                WHERE id=%s
                AND recipient=%s
                """,
                (
                    invitation_id,
                    token
                )
            )

            invitation = cur.fetchone()

            if not invitation:

                return jsonify({
                    "error": "Invitation unavailable"
                }), 404

            if invitation["status"] == "accepted":

                return jsonify({
                    "room": invitation["room"],
                    "status": "accepted"
                })

            room = str(uuid.uuid4())

            cur.execute(
                """
                INSERT INTO rooms
                (
                    id,
                    first_session,
                    second_session,
                    created_at
                )

                VALUES (%s,%s,%s,%s)
                """,
                (
                    room,
                    invitation["sender"],
                    invitation["recipient"],
                    int(time.time())
                )
            )

            cur.execute(
                """
                UPDATE invitations

                SET
                    status='accepted',
                    room=%s

                WHERE id=%s
                """,
                (
                    room,
                    invitation_id
                )
            )

        conn.commit()

    finally:
        conn.close()

    return jsonify({
        "room": room,
        "status": "accepted"
    })


# =========================================================
# CHAT
# =========================================================

def allowed_room(token, room):

    conn = get_db()

    try:

        with conn.cursor() as cur:

            cur.execute(
                """
                SELECT *
                FROM rooms

                WHERE id=%s

                AND
                (
                    first_session=%s
                    OR second_session=%s
                )
                """,
                (
                    room,
                    token,
                    token
                )
            )

            return cur.fetchone()

    finally:
        conn.close()


@app.get("/api/chat/<room>")
def get_chat(room):

    token = get_session()

    if not token or not allowed_room(token, room):

        return jsonify({
            "error": "Conversation unavailable"
        }), 403

    conn = get_db()

    try:

        with conn.cursor() as cur:

            cur.execute(
                """
                SELECT
                    id,
                    sender,
                    body,
                    created_at

                FROM messages

                WHERE room=%s

                ORDER BY created_at,id
                """,
                (room,)
            )

            rows = cur.fetchall()

    finally:
        conn.close()

    return jsonify({
        "messages": rows
    })


@app.post("/api/chat/<room>")
def send_message(room):

    data = request.get_json(silent=True) or {}

    token = get_session(data)

    if not token or not allowed_room(token, room):

        return jsonify({
            "error": "Conversation unavailable"
        }), 403

    body = clean(
        data.get("body"),
        700
    )

    if not body:

        return jsonify({
            "error": "Message is empty"
        }), 400

    message_id = str(uuid.uuid4())

    created_at = int(time.time())

    conn = get_db()

    try:

        with conn.cursor() as cur:

            cur.execute(
                """
                INSERT INTO messages
                (
                    id,
                    room,
                    sender,
                    body,
                    created_at
                )

                VALUES (%s,%s,%s,%s,%s)
                """,
                (
                    message_id,
                    room,
                    token,
                    body,
                    created_at
                )
            )

        conn.commit()

    finally:
        conn.close()

    return jsonify({
        "message": {
            "id": message_id,
            "room": room,
            "sender": token,
            "body": body,
            "created_at": created_at
        }
    }), 201


# =========================================================
# STATIC WEBSITE
# =========================================================

@app.get("/")
def homepage():

    return send_from_directory(
        ROOT,
        "index.html"
    )


@app.get("/<path:path>")
def static_files(path):

    if path.startswith("api/"):

        return jsonify({
            "error": "Not found"
        }), 404

    file_path = ROOT / path

    if file_path.is_file():

        return send_from_directory(
            ROOT,
            path
        )

    return send_from_directory(
        ROOT,
        "index.html"
    )