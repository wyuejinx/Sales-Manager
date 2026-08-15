import sqlite3
import os

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DB_PATH = os.path.join(BASE_DIR, "Database", "sales_manager.db")

print("Database:", DB_PATH)

conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()

users = cursor.execute("SELECT id, username, password FROM users").fetchall()

print("Users:")
for user in users:
    print(user)

conn.close()