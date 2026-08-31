import os
import sqlite3
import psycopg2
from psycopg2.extras import RealDictCursor
from flask import Flask, render_template, request, redirect, url_for, session, flash, make_response, send_from_directory
from flask_socketio import SocketIO, join_room, emit
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "change-this-secret-key-in-production")

UPLOAD_FOLDER = os.path.join(app.root_path, 'static', 'uploads')
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'pdf', 'txt', 'docx', 'zip'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

socketio = SocketIO(app, cors_allowed_origins="*")
DATABASE_URL = os.environ.get("DATABASE_URL")
DATABASE = "chat.db"

online_users = {}


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


class DBWrapper:
    """Unified wrapper to handle both SQLite (Local) and PostgreSQL (Render) smoothly."""
    def __init__(self, conn, is_postgres):
        self.conn = conn
        self.is_postgres = is_postgres

    def execute(self, query, params=()):
        cursor = self.conn.cursor()
        if self.is_postgres:
            query = query.replace('?', '%s')
            query = query.replace('INTEGER PRIMARY KEY AUTOINCREMENT', 'SERIAL PRIMARY KEY')
        cursor.execute(query, params)
        return cursor

    def commit(self):
        self.conn.commit()

    def close(self):
        self.conn.close()


def get_db_connection():
    if DATABASE_URL:
        # Render PostgreSQL
        db_url = DATABASE_URL
        if db_url.startswith("postgres://"):
            db_url = db_url.replace("postgres://", "postgresql://", 1)
        conn = psycopg2.connect(db_url, cursor_factory=RealDictCursor)
        return DBWrapper(conn, is_postgres=True)
    else:
        # Local SQLite fallback
        conn = sqlite3.connect(DATABASE)
        conn.row_factory = sqlite3.Row
        return DBWrapper(conn, is_postgres=False)


def init_db():
    conn = get_db_connection()
    
    # 1. Users Table
    conn.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            username VARCHAR(80) UNIQUE NOT NULL,
            password VARCHAR(200) NOT NULL,
            bio VARCHAR(255) DEFAULT 'Hey there! I am using Chat App.',
            profile_pic VARCHAR(255) DEFAULT 'default.png'
        );
    ''')

    # 2. Messages Table
    conn.execute('''
        CREATE TABLE IF NOT EXISTS messages (
            id SERIAL PRIMARY KEY,
            sender_id INT NOT NULL,
            receiver_id INT NOT NULL,
            message TEXT NOT NULL,
            file_url TEXT DEFAULT NULL,
            file_type TEXT DEFAULT NULL,
            is_read INT DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    ''')
    
    # 3. Safe Dynamic Migrations for Existing Tables
    migrations = [
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS bio VARCHAR(255) DEFAULT 'Hey there! I am using Chat App.'",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS profile_pic VARCHAR(255) DEFAULT 'default.png'",
        "ALTER TABLE messages ADD COLUMN IF NOT EXISTS file_url TEXT DEFAULT NULL",
        "ALTER TABLE messages ADD COLUMN IF NOT EXISTS file_type TEXT DEFAULT NULL",
        "ALTER TABLE messages ADD COLUMN IF NOT EXISTS is_read INT DEFAULT 0",
        "ALTER TABLE messages ADD COLUMN IF NOT EXISTS created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP"
    ]

    for mig in migrations:
        try:
            conn.execute(mig)
        except Exception:
            pass  # Ignore if column already exists in SQLite/DB

    conn.commit()
    conn.close()


# Initialize DB on App startup
with app.app_context():
    try:
        init_db()
        print("Database schema successfully initialized!")
    except Exception as e:
        print(f"Database initialization error: {e}")


@app.route("/")
def home():
    if "user_id" not in session:
        return redirect(url_for("login"))

    current_id = session["user_id"]
    connection = get_db_connection()

    cur = connection.execute(
        """
        SELECT u.id, u.username, u.bio, u.profile_pic,
               COUNT(m.id) AS unread_count
        FROM users u
        LEFT JOIN messages m ON m.sender_id = u.id 
                             AND m.receiver_id = ? 
                             AND (m.is_read = 0 OR m.is_read IS NULL)
        WHERE u.id != ?
        GROUP BY u.id, u.username, u.bio, u.profile_pic
        """,
        (current_id, current_id)
    )
    users = cur.fetchall()
    connection.close()

    response = make_response(render_template(
        "index.html",
        users=users,
        current_username=session.get("username", "User"),
        online_user_ids=list(online_users.keys())
    ))
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    return response


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        if not username or not password:
            flash("Username and password are required.", "error")
            return render_template("register.html")

        hashed_password = generate_password_hash(password)
        connection = get_db_connection()

        try:
            connection.execute(
                "INSERT INTO users (username, password) VALUES (?, ?)",
                (username, hashed_password)
            )
            connection.commit()
            connection.close()
            flash("Registration successful! Please log in.", "success")
            return redirect(url_for("login"))
        except Exception:
            connection.close()
            flash("Username already exists.", "error")
            return render_template("register.html")

    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        connection = get_db_connection()
        cur = connection.execute(
            "SELECT * FROM users WHERE username = ?",
            (username,)
        )
        user = cur.fetchone()
        connection.close()

        if user and check_password_hash(user["password"], password):
            session["user_id"] = user["id"]
            session["username"] = user["username"]
            session["bio"] = user.get("bio", "Hey there! I am using Chat App.")
            session["profile_pic"] = user.get("profile_pic", "default.png")
            return redirect(url_for("home"))

        flash("Invalid username or password.", "error")
        return render_template("login.html")

    return render_template("login.html")


@app.route("/update-profile", methods=["POST"])
def update_profile():
    if "user_id" not in session:
        return redirect(url_for("login"))

    bio = request.form.get("bio", "").strip()
    user_id = session["user_id"]
    connection = get_db_connection()

    if 'profile_pic' in request.files:
        file = request.files['profile_pic']
        if file and file.filename != '' and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            unique_filename = f"p_{user_id}_{filename}"
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)
            file.save(filepath)
            
            connection.execute(
                "UPDATE users SET bio = ?, profile_pic = ? WHERE id = ?",
                (bio, unique_filename, user_id)
            )
            session["profile_pic"] = unique_filename
        else:
            connection.execute("UPDATE users SET bio = ? WHERE id = ?", (bio, user_id))
    else:
        connection.execute("UPDATE users SET bio = ? WHERE id = ?", (bio, user_id))

    connection.commit()
    connection.close()

    session["bio"] = bio
    flash("Profile updated successfully!", "success")
    return redirect(url_for("home"))


@app.route("/messages/<int:user_id>")
def get_messages(user_id):
    if "user_id" not in session:
        return {"success": False, "error": "Not logged in"}, 401

    current_user_id = session["user_id"]
    connection = get_db_connection()

    connection.execute(
        "UPDATE messages SET is_read = 1 WHERE sender_id = ? AND receiver_id = ? AND is_read = 0",
        (user_id, current_user_id)
    )
    connection.commit()

    socketio.emit("messages_read_receipt", {"read_by": current_user_id, "sender_id": user_id}, room=f"user_{user_id}")

    cur = connection.execute(
        """
        SELECT id, sender_id, receiver_id, message, file_url, file_type, is_read, created_at
        FROM messages
        WHERE (sender_id = ? AND receiver_id = ?)
           OR (sender_id = ? AND receiver_id = ?)
        ORDER BY id ASC
        """,
        (current_user_id, user_id, user_id, current_user_id)
    )
    messages = cur.fetchall()
    connection.close()

    return {
        "success": True,
        "messages": [
            {
                "id": msg["id"],
                "sender_id": msg["sender_id"],
                "receiver_id": msg["receiver_id"],
                "message": msg["message"],
                "file_url": msg["file_url"],
                "file_type": msg["file_type"],
                "is_read": bool(msg["is_read"]),
                "created_at": str(msg["created_at"])
            }
            for msg in messages
        ]
    }


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@socketio.on("connect")
def handle_connect():
    if "user_id" not in session:
        return False

    user_id = session["user_id"]
    join_room(f"user_{user_id}")

    if user_id not in online_users:
        online_users[user_id] = set()
        socketio.emit("user_status", {"user_id": user_id, "status": "online"})

    online_users[user_id].add(request.sid)


@socketio.on("disconnect")
def handle_disconnect():
    if "user_id" not in session:
        return

    user_id = session["user_id"]
    if user_id in online_users:
        online_users[user_id].discard(request.sid)
        if not online_users[user_id]:
            del online_users[user_id]
            socketio.emit("user_status", {"user_id": user_id, "status": "offline"})


@socketio.on("send_message")
def handle_send_message(data):
    if "user_id" not in session:
        return

    sender_id = session["user_id"]
    receiver_id = data.get("receiver_id")
    message_text = data.get("message", "").strip()

    if not receiver_id or not message_text:
        return

    try:
        receiver_id = int(receiver_id)
    except ValueError:
        return

    connection = get_db_connection()
    if connection.is_postgres:
        cur = connection.execute(
            "INSERT INTO messages (sender_id, receiver_id, message) VALUES (?, ?, ?) RETURNING id, created_at",
            (sender_id, receiver_id, message_text)
        )
        row = cur.fetchone()
        msg_id = row["id"]
        created_at = str(row["created_at"])
    else:
        cur = connection.execute(
            "INSERT INTO messages (sender_id, receiver_id, message) VALUES (?, ?, ?)",
            (sender_id, receiver_id, message_text)
        )
        msg_id = cur.lastrowid
        created_at = str(connection.execute("SELECT created_at FROM messages WHERE id = ?", (msg_id,)).fetchone()["created_at"])

    connection.commit()
    connection.close()

    payload = {
        "id": msg_id,
        "sender_id": sender_id,
        "receiver_id": receiver_id,
        "message": message_text,
        "file_url": None,
        "file_type": None,
        "is_read": 0,
        "created_at": created_at
    }

    socketio.emit("receive_message", payload, room=f"user_{receiver_id}")
    socketio.emit("receive_message", payload, room=f"user_{sender_id}")


@socketio.on("typing")
def handle_typing(data):
    if "user_id" not in session:
        return
    receiver_id = data.get("receiver_id")
    is_typing = data.get("is_typing", False)

    emit("user_typing", {
        "sender_id": session["user_id"],
        "is_typing": is_typing
    }, room=f"user_{receiver_id}")


@socketio.on('mark_as_read')
def handle_mark_as_read(data):
    sender_id = data.get('sender_id') 
    receiver_id = session.get('user_id') 
    
    if not sender_id or not receiver_id:
        return

    connection = get_db_connection()
    connection.execute(
        "UPDATE messages SET is_read = 1 WHERE sender_id = ? AND receiver_id = ? AND is_read = 0",
        (sender_id, receiver_id)
    )
    connection.commit()
    connection.close()
    
    emit('messages_read_receipt', {'read_by': receiver_id, 'sender_id': sender_id}, room=f"user_{sender_id}")


if __name__ == "__main__":
    socketio.run(app, debug=True)


