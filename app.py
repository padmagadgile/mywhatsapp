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
    connection = get_db_connection()

    connection.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL
        )
    """)

    connection.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id SERIAL PRIMARY KEY,
            sender_id INTEGER NOT NULL,
            receiver_id INTEGER NOT NULL,
            message TEXT,
            file_url TEXT,
            file_type TEXT,
            is_read INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (sender_id) REFERENCES users(id),
            FOREIGN KEY (receiver_id) REFERENCES users(id)
        )
    """)

    for col_def in ["is_read INTEGER DEFAULT 0", "file_url TEXT", "file_type TEXT"]:
        try:
            connection.execute(f"ALTER TABLE messages ADD COLUMN {col_def}")
            connection.commit()
        except Exception:
            pass

    connection.commit()
    connection.close()


with app.app_context():
    init_db()


@app.route("/")
def home():
    if "user_id" not in session:
        return redirect(url_for("login"))

    current_id = session["user_id"]
    connection = get_db_connection()

    cur = connection.execute(
        """
        SELECT u.id, u.username,
               COUNT(m.id) AS unread_count
        FROM users u
        LEFT JOIN messages m ON m.sender_id = u.id 
                             AND m.receiver_id = ? 
                             AND m.is_read = 0
        WHERE u.id != ?
        GROUP BY u.id, u.username
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
            return redirect(url_for("home"))

        flash("Invalid username or password.", "error")
        return render_template("login.html")

    return render_template("login.html")


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

    socketio.emit("messages_read", {"read_by": current_user_id}, room=f"user_{user_id}")

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
                "is_read": msg["is_read"],
                "created_at": str(msg["created_at"])
            }
            for msg in messages
        ]
    }


@app.route("/upload", methods=["POST"])
def upload_file():
    if "user_id" not in session:
        return {"success": False, "error": "Not logged in"}, 401

    if 'file' not in request.files:
        return {"success": False, "error": "No file attached"}, 400

    file = request.files['file']
    receiver_id = request.form.get('receiver_id')

    if file.filename == '' or not receiver_id:
        return {"success": False, "error": "Invalid request"}, 400

    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        unique_filename = f"{session['user_id']}_{int(os.urandom(4).hex(), 16)}_{filename}"
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)
        file.save(filepath)

        file_url = url_for('static', filename=f'uploads/{unique_filename}')
        ext = filename.rsplit('.', 1)[1].lower()
        file_type = 'image' if ext in ['png', 'jpg', 'jpeg', 'gif'] else 'file'

        sender_id = session["user_id"]
        connection = get_db_connection()
        
        if connection.is_postgres:
            cur = connection.execute(
                "INSERT INTO messages (sender_id, receiver_id, message, file_url, file_type) VALUES (?, ?, ?, ?, ?) RETURNING id, created_at",
                (sender_id, receiver_id, filename, file_url, file_type)
            )
            row = cur.fetchone()
            msg_id = row["id"]
            created_at = str(row["created_at"])
        else:
            cur = connection.execute(
                "INSERT INTO messages (sender_id, receiver_id, message, file_url, file_type) VALUES (?, ?, ?, ?, ?)",
                (sender_id, receiver_id, filename, file_url, file_type)
            )
            msg_id = cur.lastrowid
            created_at = str(connection.execute("SELECT created_at FROM messages WHERE id = ?", (msg_id,)).fetchone()["created_at"])

        connection.commit()
        connection.close()

        payload = {
            "id": msg_id,
            "sender_id": sender_id,
            "receiver_id": int(receiver_id),
            "message": filename,
            "file_url": file_url,
            "file_type": file_type,
            "is_read": 0,
            "created_at": created_at
        }

        socketio.emit("receive_message", payload, room=f"user_{receiver_id}")
        socketio.emit("receive_message", payload, room=f"user_{sender_id}")

        return {"success": True, "data": payload}

    return {"success": False, "error": "File type not allowed"}, 400


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


if __name__ == "__main__":
    socketio.run(app, debug=True)