from flask import Flask, render_template, request, redirect, url_for, session
import sqlite3
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)

app.secret_key = "change-this-secret-key"

DATABASE = "chat.db"


def get_db_connection():
    connection = sqlite3.connect(DATABASE)
    connection.row_factory = sqlite3.Row
    return connection


def init_db():
    connection = get_db_connection()

    # Users table
    connection.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL
        )
    """)

    # Messages table
    connection.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sender_id INTEGER NOT NULL,
            receiver_id INTEGER NOT NULL,
            message TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

            FOREIGN KEY (sender_id) REFERENCES users(id),
            FOREIGN KEY (receiver_id) REFERENCES users(id)
        )
    """)

    connection.commit()
    connection.close()

@app.route("/")
def home():

    if "user_id" not in session:
        return redirect(url_for("login"))

    connection = get_db_connection()

    users = connection.execute(
        "SELECT id, username FROM users WHERE id != ?",
        (session["user_id"],)
    ).fetchall()

    connection.close()

    return render_template(
        "index.html",
        users=users,
        current_username=session["username"]
    )

@app.route("/register", methods=["GET", "POST"])
def register():

    if request.method == "POST":

        username = request.form["username"].strip()
        password = request.form["password"]

        if not username or not password:
            return "Username and password are required."

        hashed_password = generate_password_hash(password)

        connection = get_db_connection()

        try:
            connection.execute(
                "INSERT INTO users (username, password) VALUES (?, ?)",
                (username, hashed_password)
            )

            connection.commit()

        except sqlite3.IntegrityError:
            connection.close()
            return "Username already exists."

        connection.close()

        return "Registration successful!"

    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():

    if request.method == "POST":

        username = request.form["username"].strip()
        password = request.form["password"]

        connection = get_db_connection()

        user = connection.execute(
            "SELECT * FROM users WHERE username = ?",
            (username,)
        ).fetchone()

        connection.close()

        if user and check_password_hash(user["password"], password):

            session["user_id"] = user["id"]
            session["username"] = user["username"]

            return redirect(url_for("home"))

        return "Invalid username or password."

    return render_template("login.html")


@app.route("/send_message", methods=["POST"])
def send_message():

    if "user_id" not in session:
        return {"success": False, "error": "Not logged in"}, 401

    data = request.get_json()

    receiver_id = data.get("receiver_id")
    message = data.get("message", "").strip()

    if not receiver_id or not message:
        return {"success": False, "error": "Missing data"}, 400

    connection = get_db_connection()

    connection.execute(
        """
        INSERT INTO messages (sender_id, receiver_id, message)
        VALUES (?, ?, ?)
        """,
        (session["user_id"], receiver_id, message)
    )

    connection.commit()
    connection.close()

    return {
        "success": True,
        "message": message
    }





@app.route("/messages/<int:user_id>")
def get_messages(user_id):

    if "user_id" not in session:
        return {"success": False, "error": "Not logged in"}, 401

    current_user_id = session["user_id"]

    connection = get_db_connection()

    messages = connection.execute(
        """
        SELECT sender_id, receiver_id, message, created_at
        FROM messages
        WHERE
            (sender_id = ? AND receiver_id = ?)
            OR
            (sender_id = ? AND receiver_id = ?)
        ORDER BY id ASC
        """,
        (
            current_user_id,
            user_id,
            user_id,
            current_user_id
        )
    ).fetchall()

    connection.close()

    return {
        "success": True,
        "messages": [
            {
                "sender_id": msg["sender_id"],
                "receiver_id": msg["receiver_id"],
                "message": msg["message"],
                "created_at": msg["created_at"]
            }
            for msg in messages
        ]
    }











@app.route("/logout")
def logout():

    session.clear()

    return redirect(url_for("login"))


if __name__ == "__main__":
    init_db()
    app.run(debug=True)