from flask import Flask, render_template
import sqlite3

app = Flask(__name__)

DATABASE = "chat.db"


def init_db():
    connection = sqlite3.connect(DATABASE)

    cursor = connection.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL
        )
    """)

    connection.commit()
    connection.close()


@app.route("/")
def home():
    return render_template("index.html")


if __name__ == "__main__":
    init_db()
    app.run(debug=True)