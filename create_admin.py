import sqlite3
import os
from flask_bcrypt import Bcrypt

bcrypt = Bcrypt()

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DB_PATH = os.path.join(BASE_DIR, "Database", "sales_manager.db")

print("Using database:", DB_PATH)

username = "admin"
password = "admin123"

hashed_password = bcrypt.generate_password_hash(password).decode("utf-8")

conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()

# Prevent duplicate admin users
existing = cursor.execute(
    "SELECT * FROM users WHERE username=?",
    (username,)
).fetchone()

if existing:
    print("Admin user already exists.")
else:
    cursor.execute(
        "INSERT INTO users (username, password) VALUES (?, ?)",
        (username, hashed_password)
    )
    conn.commit()
    print("Admin user created successfully!")

conn.close()