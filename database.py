import sqlite3
import os

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DB_PATH = os.path.join(BASE_DIR, "Database", "sales_manager.db")
os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()

cursor.execute('''
CREATE TABLE IF NOT EXISTS users(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE,
    password TEXT,
    first_name TEXT,
    last_name TEXT,
    security_pin TEXT DEFAULT '1234',
    email TEXT UNIQUE,
    is_verified INTEGER DEFAULT 0
)
''')

for migration_sql in [
    "ALTER TABLE users ADD COLUMN security_pin TEXT DEFAULT '1234'",
    "ALTER TABLE users ADD COLUMN email TEXT",
    "ALTER TABLE users ADD COLUMN is_verified INTEGER DEFAULT 0"
]:
    try:
        cursor.execute(migration_sql)
        conn.commit()
    except sqlite3.OperationalError:
        pass

cursor.execute('''
CREATE TABLE IF NOT EXISTS email_otp(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT NOT NULL,
    otp_code TEXT NOT NULL,
    purpose TEXT NOT NULL,
    payload TEXT,
    attempt_count INTEGER DEFAULT 0,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    expires_at DATETIME NOT NULL
)
''')

for migration_sql in [
    "ALTER TABLE email_otp ADD COLUMN attempt_count INTEGER DEFAULT 0"
]:
    try:
        cursor.execute(migration_sql)
        conn.commit()
    except sqlite3.OperationalError:
        pass

cursor.execute('''
CREATE TABLE IF NOT EXISTS clients(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    client_name TEXT NOT NULL,
    facebook_page TEXT,
    contact_number TEXT,
    email TEXT,
    notes TEXT,
    user_id INTEGER
)
''')

cursor.execute('''
CREATE TABLE IF NOT EXISTS services(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    service_name TEXT NOT NULL,
    description TEXT,
    price REAL NOT NULL,
    user_id INTEGER
)
''')

cursor.execute('''
CREATE TABLE IF NOT EXISTS transactions(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    client_id INTEGER,
    service_id INTEGER,
    amount REAL,
    payment_method TEXT,
    payment_status TEXT,
    transaction_date DATE,
    notes TEXT,
    user_id INTEGER,

    FOREIGN KEY(client_id)
    REFERENCES clients(id),

    FOREIGN KEY(service_id)
    REFERENCES services(id)
)
''')

cursor.execute('''
CREATE TABLE IF NOT EXISTS monthly_records(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    month_name TEXT,
    total_sales REAL,
    paid_sales REAL,
    pending_sales REAL,
    transaction_count INTEGER,
    saved_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    user_id INTEGER,
    UNIQUE(month_name, user_id)
)
''')

cursor.execute('''
CREATE TABLE IF NOT EXISTS daily_capital(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    amount REAL NOT NULL,
    description TEXT NOT NULL,
    record_date TEXT NOT NULL,
    user_id INTEGER
)
''')

conn.commit()
conn.close()

print("Database created successfully.")