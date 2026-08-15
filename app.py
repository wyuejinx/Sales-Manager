from flask import Flask, render_template, request, redirect, url_for, session, jsonify
from flask_bcrypt import Bcrypt
import calendar
import os
import sqlite3
import random
import json
from datetime import date, datetime, timedelta
from email_service import send_otp_email


app = Flask(__name__)

import config
import database

app.secret_key = config.SECRET_KEY
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'

bcrypt = Bcrypt(app)

@app.after_request
def apply_security_headers(response):
    response.headers['X-Frame-Options'] = 'SAMEORIGIN'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-XSS-Protection'] = '1; mode=block'
    response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
    return response

BASE_DIR = os.path.abspath(os.path.dirname(__file__))

if os.environ.get('VERCEL'):
    DB_PATH = '/tmp/sales_manager.db'
else:
    DB_PATH = os.path.join(BASE_DIR, "Database", "sales_manager.db")

# DATABASE CONNECTION

def get_db():
    global DB_PATH
    try:
        os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
        conn = sqlite3.connect(DB_PATH)
    except Exception:
        DB_PATH = '/tmp/sales_manager.db'
        os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
        conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def seed_realistic_data(user_id):
    if user_id != 1:
        return

    seed_flag = os.path.join(BASE_DIR, "Database", ".seeded")
    if os.path.exists(seed_flag):
        return

    try:
        os.makedirs(os.path.dirname(seed_flag), exist_ok=True)
        with open(seed_flag, 'w') as f:
            f.write('seeded')
    except Exception as e:
        print("Error writing seed flag:", e)

    conn = get_db()
    count = conn.execute("SELECT COUNT(*) FROM transactions WHERE user_id = 1").fetchone()[0]
    if count < 5:
        # Check if we have clients
        clients = conn.execute("SELECT id FROM clients WHERE user_id = 1").fetchall()
        if not clients:
            conn.execute("INSERT INTO clients (client_name, user_id) VALUES ('Cedrick Tacan', 1)")
            conn.execute("INSERT INTO clients (client_name, user_id) VALUES ('Brendon Lee Navarro', 1)")
            conn.execute("INSERT INTO clients (client_name, user_id) VALUES ('John Doe', 1)")
            conn.commit()
            clients = conn.execute("SELECT id FROM clients WHERE user_id = 1").fetchall()
            
        # Check if we have services
        services = conn.execute("SELECT id, price FROM services WHERE user_id = 1").fetchall()
        if not services:
            conn.execute("INSERT INTO services (service_name, description, price, user_id) VALUES ('Serato DJ Pro', 'Full access to all Serato Features', 500.0, 1)")
            conn.execute("INSERT INTO services (service_name, description, price, user_id) VALUES ('VirtualDJ', 'Full access to all VDJ Features', 500.0, 1)")
            conn.execute("INSERT INTO services (service_name, description, price, user_id) VALUES ('Sample Decks', '', 300.0, 1)")
            conn.commit()
            services = conn.execute("SELECT id, price FROM services WHERE user_id = 1").fetchall()
            
        # Seed realistic transactions for this month
        import random
        from datetime import datetime
        today = datetime.today()
        
        methods = ['Cash', 'PayPal', 'Bank Transfer', 'GCash']
        statuses = ['Paid', 'Paid', 'Paid', 'Pending']
        
        # Seed some transactions spread over days 1 to today
        for day_num in range(1, today.day + 1):
            if random.random() < 0.6:
                num_txs = random.choice([1, 2])
                for _ in range(num_txs):
                    client_id = random.choice(clients)[0]
                    service_row = random.choice(services)
                    service_id = service_row[0]
                    amount = service_row[1]
                    method = random.choice(methods)
                    status = random.choice(statuses)
                    t_date = today.replace(day=day_num).strftime('%Y-%m-%d')
                    
                    conn.execute("""
                        INSERT INTO transactions (client_id, service_id, amount, payment_method, payment_status, transaction_date, notes, user_id)
                        VALUES (?, ?, ?, ?, ?, ?, '', 1)
                    """, (client_id, service_id, amount, method, status, t_date))
        conn.commit()
    conn.close()


# LOGIN PAGE
@app.route('/', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()

        conn = get_db()
        user = conn.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()

        if user and bcrypt.check_password_hash(user['password'], password):
            user_email = user['email']
            if user_email:
                otp_code = str(random.randint(100000, 999999))
                expires_at = (datetime.now() + timedelta(minutes=10)).strftime('%Y-%m-%d %H:%M:%S')

                payload = json.dumps({
                    'id': user['id'],
                    'username': user['username'],
                    'first_name': user['first_name'],
                    'last_name': user['last_name']
                })

                conn.execute("DELETE FROM email_otp WHERE email=? AND purpose='login'", (user_email,))
                conn.execute(
                    "INSERT INTO email_otp (email, otp_code, purpose, payload, expires_at) VALUES (?, ?, 'login', ?, ?)",
                    (user_email, otp_code, payload, expires_at)
                )
                conn.commit()
                conn.close()

                dispatch_result = send_otp_email(user_email, otp_code, purpose="Login Security")
                session['pending_login_email'] = user_email
                if dispatch_result.get('dev_mode'):
                    session['login_dev_mode_hint'] = otp_code
                else:
                    session.pop('login_dev_mode_hint', None)

                return redirect(url_for('verify_login'))
            else:
                conn.close()
                session['user_id'] = user['id']
                session['username'] = user['username']
                session['first_name'] = user['first_name']
                session['last_name'] = user['last_name']
                return redirect(url_for('dashboard'))

        conn.close()
        return render_template('auth/login.html', error='Incorrect username or password. Please try again.')

    success_msg = session.pop('login_success_msg', None)
    return render_template('auth/login.html', success=success_msg)


def validate_and_consume_otp(conn, email, otp_input, purpose):
    """
    Validates an OTP input against DB.
    Tracks attempt_count: if attempt_count >= config.MAX_OTP_ATTEMPTS (3), the OTP is deleted/invalidated.
    Returns (success_bool, user_payload_or_error_msg).
    """
    now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    otp_record = conn.execute(
        "SELECT * FROM email_otp WHERE email=? AND purpose=? AND expires_at > ?",
        (email, purpose, now_str)
    ).fetchone()

    if not otp_record:
        return False, "Invalid or expired verification code. Please request a new code."

    current_attempts = (otp_record['attempt_count'] or 0) + 1

    if current_attempts > config.MAX_OTP_ATTEMPTS:
        conn.execute("DELETE FROM email_otp WHERE id=?", (otp_record['id'],))
        conn.commit()
        return False, f"Maximum verification attempts exceeded ({config.MAX_OTP_ATTEMPTS}/{config.MAX_OTP_ATTEMPTS}). This code has been invalidated for security. Please request a new code."

    if otp_record['otp_code'] != otp_input:
        if current_attempts >= config.MAX_OTP_ATTEMPTS:
            conn.execute("DELETE FROM email_otp WHERE id=?", (otp_record['id'],))
            conn.commit()
            return False, f"Maximum verification attempts exceeded ({config.MAX_OTP_ATTEMPTS}/{config.MAX_OTP_ATTEMPTS}). This code has been invalidated for security. Please request a new code."
        else:
            conn.execute("UPDATE email_otp SET attempt_count=? WHERE id=?", (current_attempts, otp_record['id']))
            conn.commit()
            return False, f"Incorrect verification code. Attempt {current_attempts} of {config.MAX_OTP_ATTEMPTS}."

    # Code matched! Clean OTP record
    payload = otp_record['payload']
    conn.execute("DELETE FROM email_otp WHERE id=?", (otp_record['id'],))
    conn.commit()
    return True, payload


@app.route('/verify_login', methods=['GET', 'POST'])
def verify_login():
    email = session.get('pending_login_email') or request.args.get('email', '')
    dev_mode_hint = session.get('login_dev_mode_hint')

    if request.method == 'POST':
        otp_input = request.form.get('otp_code', '').strip()
        email_input = request.form.get('email', '').strip() or email

        if not otp_input:
            return render_template('auth/verify_login.html', email=email_input, error="Please enter the 6-digit verification code.", dev_mode_hint=dev_mode_hint)

        conn = get_db()
        success, result = validate_and_consume_otp(conn, email_input, otp_input, purpose='login')
        conn.close()

        if not success:
            return render_template('auth/verify_login.html', email=email_input, error=result, dev_mode_hint=dev_mode_hint)

        user_data = json.loads(result)
        session.clear()
        session['user_id'] = user_data['id']
        session['username'] = user_data['username']
        session['first_name'] = user_data['first_name']
        session['last_name'] = user_data['last_name']

        return redirect(url_for('dashboard'))

    return render_template('auth/verify_login.html', email=email, dev_mode_hint=dev_mode_hint)


# REGISTER PAGE
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '').strip()
        first_name = request.form.get('first_name', '').strip()
        last_name = request.form.get('last_name', '').strip()
        security_pin = request.form.get('security_pin', '').strip()

        if not username or not email or not password or not security_pin:
            return render_template('auth/register.html', error="All fields (including Gmail and Security PIN) are required.")

        hashed_password = bcrypt.generate_password_hash(password).decode('utf-8')

        conn = get_db()
        existing_user = conn.execute(
            "SELECT id FROM users WHERE username=? OR email=?",
            (username, email)
        ).fetchone()

        if existing_user:
            conn.close()
            return render_template('auth/register.html', error="Username or Gmail address is already registered.")

        # Generate 6-digit OTP
        otp_code = str(random.randint(100000, 999999))
        payload = json.dumps({
            'username': username,
            'email': email,
            'password': hashed_password,
            'first_name': first_name,
            'last_name': last_name,
            'security_pin': security_pin
        })
        expires_at = (datetime.now() + timedelta(minutes=config.OTP_EXPIRY_MINUTES)).strftime('%Y-%m-%d %H:%M:%S')

        # Clean old OTPs for this email
        conn.execute("DELETE FROM email_otp WHERE email=? AND purpose='register'", (email,))
        conn.execute(
            "INSERT INTO email_otp (email, otp_code, purpose, payload, expires_at) VALUES (?, ?, 'register', ?, ?)",
            (email, otp_code, payload, expires_at)
        )
        conn.commit()
        conn.close()

        dispatch_result = send_otp_email(email, otp_code, purpose="Registration")
        session['pending_verify_email'] = email
        if dispatch_result.get('dev_mode'):
            session['dev_mode_hint'] = otp_code
        else:
            session.pop('dev_mode_hint', None)

        return redirect(url_for('verify_email'))

    return render_template('auth/register.html')


@app.route('/verify_email', methods=['GET', 'POST'])
def verify_email():
    email = session.get('pending_verify_email') or request.args.get('email', '')
    dev_mode_hint = session.get('dev_mode_hint')

    if request.method == 'POST':
        otp_input = request.form.get('otp_code', '').strip()
        email_input = request.form.get('email', '').strip() or email

        if not otp_input:
            return render_template('auth/verify_email.html', email=email_input, error="Please enter the 6-digit verification code.", dev_mode_hint=dev_mode_hint)

        conn = get_db()
        success, result = validate_and_consume_otp(conn, email_input, otp_input, purpose='register')

        if not success:
            conn.close()
            return render_template('auth/verify_email.html', email=email_input, error=result, dev_mode_hint=dev_mode_hint)

        user_data = json.loads(result)
        try:
            conn.execute(
                "INSERT INTO users (username, password, first_name, last_name, security_pin, email, is_verified) VALUES (?, ?, ?, ?, ?, ?, 1)",
                (user_data['username'], user_data['password'], user_data['first_name'], user_data['last_name'], user_data['security_pin'], user_data['email'])
            )
            conn.commit()
            conn.close()
            session.pop('pending_verify_email', None)
            session.pop('dev_mode_hint', None)
            session['login_success_msg'] = "Account verified and created successfully! Please log in."
            return redirect(url_for('login'))
        except sqlite3.IntegrityError:
            conn.close()
            return render_template('auth/verify_email.html', email=email_input, error="User or Gmail already registered.", dev_mode_hint=dev_mode_hint)

    return render_template('auth/verify_email.html', email=email, dev_mode_hint=dev_mode_hint)


@app.route('/forgot_password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        email = request.form.get('email', '').strip()
        if not email:
            return render_template('auth/forgot_password.html', error="Please enter your registered Gmail address.")

        conn = get_db()
        user = conn.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()

        if not user:
            conn.close()
            return render_template('auth/forgot_password.html', error="No account found registered with that Gmail address.")

        otp_code = str(random.randint(100000, 999999))
        expires_at = (datetime.now() + timedelta(minutes=config.OTP_EXPIRY_MINUTES)).strftime('%Y-%m-%d %H:%M:%S')

        conn.execute("DELETE FROM email_otp WHERE email=? AND purpose='forgot_password'", (email,))
        conn.execute(
            "INSERT INTO email_otp (email, otp_code, purpose, expires_at) VALUES (?, ?, 'forgot_password', ?)",
            (email, otp_code, expires_at)
        )
        conn.commit()
        conn.close()

        dispatch_result = send_otp_email(email, otp_code, purpose="Password Reset")
        session['reset_password_email'] = email
        if dispatch_result.get('dev_mode'):
            session['reset_dev_mode_hint'] = otp_code
        else:
            session.pop('reset_dev_mode_hint', None)

        return redirect(url_for('reset_password'))

    return render_template('auth/forgot_password.html')


@app.route('/reset_password', methods=['GET', 'POST'])
def reset_password():
    email = session.get('reset_password_email') or request.args.get('email', '')
    dev_mode_hint = session.get('reset_dev_mode_hint')

    if request.method == 'POST':
        email_input = request.form.get('email', '').strip() or email
        otp_input = request.form.get('otp_code', '').strip()
        new_password = request.form.get('new_password', '').strip()
        confirm_password = request.form.get('confirm_password', '').strip()

        if not otp_input or not new_password or not confirm_password:
            return render_template('auth/reset_password.html', email=email_input, error="All fields are required.", dev_mode_hint=dev_mode_hint)

        if new_password != confirm_password:
            return render_template('auth/reset_password.html', email=email_input, error="Passwords do not match.", dev_mode_hint=dev_mode_hint)

        conn = get_db()
        success, result = validate_and_consume_otp(conn, email_input, otp_input, purpose='forgot_password')

        if not success:
            conn.close()
            return render_template('auth/reset_password.html', email=email_input, error=result, dev_mode_hint=dev_mode_hint)

        hashed_password = bcrypt.generate_password_hash(new_password).decode('utf-8')
        conn.execute("UPDATE users SET password=? WHERE email=?", (hashed_password, email_input))
        conn.commit()
        conn.close()

        session.pop('reset_password_email', None)
        session.pop('reset_dev_mode_hint', None)
        session['login_success_msg'] = "Password updated successfully! Please log in with your new password."
        return redirect(url_for('login'))

    return render_template('auth/reset_password.html', email=email, dev_mode_hint=dev_mode_hint)


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))


# =========================
# DASHBOARD
# =========================
@app.route('/dashboard')
def dashboard():

    if 'user_id' not in session:
        return redirect(url_for('login'))

    user_id = session['user_id']

    # Auto-archive past months
    auto_archive_past_months(user_id)

    seed_realistic_data(user_id)

    conn = get_db()

    total_clients = conn.execute("SELECT COUNT(*) FROM clients WHERE user_id = ?", (user_id,)).fetchone()[0]
    total_services = conn.execute("SELECT COUNT(*) FROM services WHERE user_id = ?", (user_id,)).fetchone()[0]
    total_transactions = conn.execute("SELECT COUNT(*) FROM transactions WHERE user_id = ?", (user_id,)).fetchone()[0]

    overall_capital = conn.execute("""
        SELECT IFNULL(SUM(amount), 0) FROM daily_capital WHERE user_id = ?
    """, (user_id,)).fetchone()[0]

    gross_total_sales = conn.execute("""
        SELECT IFNULL(SUM(amount), 0)
        FROM transactions
        WHERE payment_status='Paid' AND user_id = ?
    """, (user_id,)).fetchone()[0]

    total_sales = gross_total_sales - overall_capital

    pending_sales = conn.execute("""
        SELECT IFNULL(SUM(amount), 0)
        FROM transactions
        WHERE payment_status='Pending' AND user_id = ?
    """, (user_id,)).fetchone()[0]

    today = date.today()
    month_start = today.replace(day=1).strftime('%Y-%m-%d')
    month_end = today.strftime('%Y-%m-%d')

    month_capital = conn.execute("""
        SELECT IFNULL(SUM(amount), 0) FROM daily_capital
        WHERE record_date >= ? AND record_date <= ? AND user_id = ?
    """, (month_start, month_end, user_id)).fetchone()[0]

    gross_monthly_sales = conn.execute("""
        SELECT IFNULL(SUM(amount), 0)
        FROM transactions
        WHERE payment_status='Paid'
          AND transaction_date >= ?
          AND transaction_date <= ?
          AND user_id = ?
    """, (month_start, month_end, user_id)).fetchone()[0]

    monthly_sales = gross_monthly_sales - month_capital

    daily_sales_rows = conn.execute("""
        SELECT strftime('%d', transaction_date) AS day_num, SUM(amount) AS revenue
        FROM transactions
        WHERE payment_status='Paid'
          AND transaction_date >= ?
          AND transaction_date <= ?
          AND user_id = ?
        GROUP BY strftime('%d', transaction_date)
        ORDER BY day_num
    """, (month_start, month_end, user_id)).fetchall()

    daily_capital_rows = conn.execute("""
        SELECT strftime('%d', record_date) AS day_num, SUM(amount) AS capital
        FROM daily_capital
        WHERE record_date >= ? AND record_date <= ? AND user_id = ?
        GROUP BY strftime('%d', record_date)
        ORDER BY day_num
    """, (month_start, month_end, user_id)).fetchall()

    daily_sales = {int(row['day_num']): float(row['revenue']) for row in daily_sales_rows}
    daily_capital_map = {int(row['day_num']): float(row['capital']) for row in daily_capital_rows}

    chart_labels = [str(day) for day in range(1, today.day + 1)]
    chart_values = [daily_sales.get(day, 0) - daily_capital_map.get(day, 0) for day in range(1, today.day + 1)]

    recent_transactions = conn.execute("""
        SELECT t.id, c.client_name, s.service_name, t.amount, t.payment_status, t.transaction_date
        FROM transactions t
        JOIN clients c ON t.client_id = c.id
        JOIN services s ON t.service_id = s.id
        WHERE t.user_id = ?
        ORDER BY t.id DESC
        LIMIT 5
    """, (user_id,)).fetchall()

    # Calculate today's sales and capital
    today_str = today.strftime('%Y-%m-%d')
    today_sales = conn.execute("""
        SELECT IFNULL(SUM(amount), 0) FROM transactions 
        WHERE payment_status = 'Paid' AND transaction_date = ? AND user_id = ?
    """, (today_str, user_id)).fetchone()[0]

    today_capital = conn.execute("""
        SELECT IFNULL(SUM(amount), 0) FROM daily_capital 
        WHERE record_date = ? AND user_id = ?
    """, (today_str, user_id)).fetchone()[0]

    user = conn.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
    conn.close()

    return render_template(
        'dashboard/dashboard.html',
        total_clients=total_clients,
        total_services=total_services,
        total_transactions=total_transactions,
        user=user,
        total_sales=total_sales,
        monthly_sales=monthly_sales,
        pending_sales=pending_sales,
        recent_transactions=recent_transactions,
        chart_labels=chart_labels,
        chart_values=chart_values,
        month_name=today.strftime('%B'),
        today_sales=today_sales,
        today_capital=today_capital
    )


@app.route('/settings', methods=['GET', 'POST'])
def settings():

    if 'user_id' not in session:
        return redirect(url_for('login'))

    conn = get_db()
    user = conn.execute("SELECT * FROM users WHERE id=?", (session['user_id'],)).fetchone()

    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()
        security_pin = request.form.get('security_pin', '').strip()

        if username:
            conn.execute("UPDATE users SET username=? WHERE id=?", (username, session['user_id']))

        if password:
            hashed_password = bcrypt.generate_password_hash(password).decode('utf-8')
            conn.execute("UPDATE users SET password=? WHERE id=?", (hashed_password, session['user_id']))

        conn.execute("UPDATE users SET security_pin=? WHERE id=?", (security_pin, session['user_id']))

        conn.commit()
        conn.close()
        return redirect(url_for('settings'))

    conn.close()
    return render_template('settings.html', user=user)


@app.route('/verify_pin', methods=['POST'])
def verify_pin():
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'User not authenticated.'}), 401

    data = request.get_json() or {}
    entered_pin = data.get('pin', '').strip()

    conn = get_db()
    user = conn.execute("SELECT security_pin FROM users WHERE id=?", (session['user_id'],)).fetchone()
    conn.close()

    if user:
        db_pin = user['security_pin']
        if db_pin is None or db_pin == '':
            return jsonify({'success': False, 'message': 'Security PIN is not set. Please set your Security PIN in Settings first.'})

        if entered_pin == db_pin:
            return jsonify({'success': True})

    return jsonify({'success': False, 'message': 'Incorrect Security PIN. Access Denied.'})


@app.route('/records')
@app.route('/reports')
def records():

    if 'user_id' not in session:
        return redirect(url_for('login'))

    user_id = session['user_id']
    conn = get_db()

    search = request.args.get('search', '').strip()

    total_clients = conn.execute("SELECT COUNT(*) FROM clients WHERE user_id = ?", (user_id,)).fetchone()[0]
    total_services = conn.execute("SELECT COUNT(*) FROM services WHERE user_id = ?", (user_id,)).fetchone()[0]
    total_transactions = conn.execute("SELECT COUNT(*) FROM transactions WHERE user_id = ?", (user_id,)).fetchone()[0]
    overall_capital = conn.execute("""
        SELECT IFNULL(SUM(amount), 0) FROM daily_capital WHERE user_id = ?
    """, (user_id,)).fetchone()[0]

    gross_total_sales = conn.execute("""
        SELECT IFNULL(SUM(amount), 0)
        FROM transactions
        WHERE payment_status='Paid' AND user_id = ?
    """, (user_id,)).fetchone()[0]

    total_sales = gross_total_sales - overall_capital

    pending_sales = conn.execute("""
        SELECT IFNULL(SUM(amount), 0)
        FROM transactions
        WHERE payment_status='Pending' AND user_id = ?
    """, (user_id,)).fetchone()[0]

    month_capital = conn.execute("""
        SELECT IFNULL(SUM(amount), 0) FROM daily_capital
        WHERE strftime('%Y-%m', record_date) = strftime('%Y-%m', 'now')
          AND user_id = ?
    """, (user_id,)).fetchone()[0]

    gross_monthly_sales = conn.execute("""
        SELECT IFNULL(SUM(amount), 0)
        FROM transactions
        WHERE payment_status='Paid'
          AND strftime('%Y-%m', transaction_date) = strftime('%Y-%m', 'now')
          AND user_id = ?
    """, (user_id,)).fetchone()[0]

    monthly_sales = gross_monthly_sales - month_capital

    if search:
        transactions = conn.execute("""
            SELECT t.id, t.amount, t.payment_status, t.payment_method, t.transaction_date,
                   c.client_name, s.service_name
            FROM transactions t
            JOIN clients c ON t.client_id = c.id
            JOIN services s ON t.service_id = s.id
            WHERE (c.client_name LIKE ?
               OR s.service_name LIKE ?
               OR t.payment_status LIKE ?
               OR t.payment_method LIKE ?
               OR t.amount LIKE ?
               OR t.id LIKE ?
               OR t.transaction_date LIKE ?)
               AND t.user_id = ?
            ORDER BY t.id DESC
        """, (f"%{search}%", f"%{search}%", f"%{search}%", f"%{search}%", f"%{search}%", f"%{search}%", f"%{search}%", user_id)).fetchall()
    else:
        transactions = conn.execute("""
            SELECT t.id, t.amount, t.payment_status, t.payment_method, t.transaction_date,
                   c.client_name, s.service_name
            FROM transactions t
            JOIN clients c ON t.client_id = c.id
            JOIN services s ON t.service_id = s.id
            WHERE t.user_id = ?
            ORDER BY t.id DESC
        """, (user_id,)).fetchall()

    recent_clients = conn.execute("""
        SELECT id, client_name, contact_number, email
        FROM clients
        WHERE user_id = ?
        ORDER BY id DESC
        LIMIT 5
    """, (user_id,)).fetchall()

    recent_services = conn.execute("""
        SELECT id, service_name, price
        FROM services
        WHERE user_id = ?
        ORDER BY id DESC
        LIMIT 5
    """, (user_id,)).fetchall()

    conn.close()

    return render_template(
        'reports.html',
        transactions=transactions,
        recent_clients=recent_clients,
        recent_services=recent_services,
        total_clients=total_clients,
        total_services=total_services,
        total_transactions=total_transactions,
        total_sales=total_sales,
        pending_sales=pending_sales,
        monthly_sales=monthly_sales,
        search_query=search
    )


# =========================
# SERVICES
# =========================
@app.route('/services', methods=['GET', 'POST'])
def services():

    if 'user_id' not in session:
        return redirect(url_for('login'))

    user_id = session['user_id']
    conn = get_db()

    if request.method == 'POST':
        service_name = request.form.get('service_name', '').strip()
        price = request.form.get('price', '').strip()

        conn.execute("""
            INSERT INTO services (service_name, price, user_id)
            VALUES (?, ?, ?)
        """, (
            service_name,
            price,
            user_id
        ))
        conn.commit()
        return redirect(url_for('services'))

    search = request.args.get('search')

    if search:
        services = conn.execute("""
            SELECT * FROM services
            WHERE (service_name LIKE ?
            OR description LIKE ?
            OR price LIKE ?
            OR id LIKE ?)
            AND user_id = ?
            ORDER BY id ASC
        """, (f"%{search}%", f"%{search}%", f"%{search}%", f"%{search}%", user_id)).fetchall()
    else:
        services = conn.execute("SELECT * FROM services WHERE user_id = ? ORDER BY id ASC", (user_id,)).fetchall()

    conn.close()

    return render_template(
        'services/services.html',
        services=services,
        search_query=search
    )


@app.route('/edit_service/<int:id>', methods=['GET', 'POST'])
def edit_service(id):

    if 'user_id' not in session:
        return redirect(url_for('login'))

    user_id = session['user_id']
    conn = get_db()

    if request.method == 'POST':
        service_name = request.form.get('service_name', '').strip()
        price = request.form.get('price', '').strip()

        conn.execute("""
            UPDATE services
            SET service_name=?, price=?
            WHERE id=? AND user_id=?
        """, (
            service_name,
            price,
            id,
            user_id
        ))
        conn.commit()
        conn.close()
        return redirect(url_for('services'))

    service = conn.execute("SELECT * FROM services WHERE id=? AND user_id=?", (id, user_id)).fetchone()
    conn.close()

    return render_template('services/edit_service.html', service=service)


@app.route('/delete_service/<int:id>')
def delete_service(id):

    if 'user_id' not in session:
        return redirect(url_for('login'))

    user_id = session['user_id']
    conn = get_db()
    conn.execute("DELETE FROM transactions WHERE service_id=? AND user_id=?", (id, user_id))
    conn.execute("DELETE FROM services WHERE id=? AND user_id=?", (id, user_id))
    conn.commit()
    conn.close()

    return redirect(url_for('services'))


# =========================
# CLIENTS
# =========================
@app.route('/clients', methods=['GET', 'POST'])
def clients():

    if 'user_id' not in session:
        return redirect(url_for('login'))

    user_id = session['user_id']
    conn = get_db()

    if request.method == 'POST':
        conn.execute("""
            INSERT INTO clients (client_name, facebook_page, contact_number, email, notes, user_id)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            request.form.get('client_name', '').strip(),
            request.form.get('facebook_page', '').strip(),
            request.form.get('contact_number', '').strip(),
            request.form.get('email', '').strip(),
            request.form.get('notes', '').strip(),
            user_id
        ))
        conn.commit()
        conn.close()
        return redirect(url_for('clients'))

    search = request.args.get('search')

    if search:
        clients = conn.execute("""
            SELECT * FROM clients
            WHERE (client_name LIKE ?
            OR contact_number LIKE ?
            OR email LIKE ?
            OR id LIKE ?)
            AND user_id = ?
            ORDER BY id ASC
        """, (f"%{search}%", f"%{search}%", f"%{search}%", f"%{search}%", user_id)).fetchall()
    else:
        clients = conn.execute("SELECT * FROM clients WHERE user_id = ? ORDER BY id ASC", (user_id,)).fetchall()

    conn.close()

    return render_template(
        'clients/clients.html',
        clients=clients,
        search_query=search
    )


@app.route('/edit_client/<int:id>', methods=['GET', 'POST'])
def edit_client(id):

    if 'user_id' not in session:
        return redirect(url_for('login'))

    user_id = session['user_id']
    conn = get_db()

    if request.method == 'POST':
        conn.execute("""
            UPDATE clients
            SET client_name=?
            WHERE id=? AND user_id=?
        """, (
            request.form['client_name'],
            id,
            user_id
        ))
        conn.commit()
        conn.close()
        return redirect(url_for('clients'))

    client = conn.execute("SELECT * FROM clients WHERE id=? AND user_id=?", (id, user_id)).fetchone()
    conn.close()

    return render_template('clients/edit_client.html', client=client)


@app.route('/delete_client/<int:id>')
def delete_client(id):

    if 'user_id' not in session:
        return redirect(url_for('login'))

    user_id = session['user_id']
    conn = get_db()
    conn.execute("DELETE FROM transactions WHERE client_id=? AND user_id=?", (id, user_id))
    conn.execute("DELETE FROM clients WHERE id=? AND user_id=?", (id, user_id))
    conn.commit()
    conn.close()

    return redirect(url_for('clients'))


@app.route('/delete_transaction/<int:id>')
def delete_transaction(id):

    if 'user_id' not in session:
        return redirect(url_for('login'))

    user_id = session['user_id']
    conn = get_db()
    conn.execute("DELETE FROM transactions WHERE id=? AND user_id=?", (id, user_id))
    conn.commit()
    conn.close()

    return redirect(url_for('transactions'))


# =========================
# TRANSACTIONS
# =========================
@app.route('/transactions', methods=['GET', 'POST'])
def transactions():

    if 'user_id' not in session:
        return redirect(url_for('login'))

    user_id = session['user_id']
    conn = get_db()

    if request.method == 'POST':
        tx_date = request.form.get('transaction_date', '').strip() or date.today().strftime('%Y-%m-%d')
        conn.execute("""
            INSERT INTO transactions (
                client_id,
                service_id,
                amount,
                payment_method,
                payment_status,
                transaction_date,
                notes,
                user_id
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            request.form['client_id'],
            request.form['service_id'],
            request.form['amount'],
            request.form['payment_method'],
            request.form['payment_status'],
            tx_date,
            request.form.get('notes', '').strip(),
            user_id
        ))
        conn.commit()
        return redirect(url_for('transactions'))

    search = request.args.get('search')

    if search:
        transactions = conn.execute("""
            SELECT t.*, c.client_name, s.service_name
            FROM transactions t
            JOIN clients c ON t.client_id = c.id
            JOIN services s ON t.service_id = s.id
            WHERE (c.client_name LIKE ?
               OR s.service_name LIKE ?
               OR t.payment_status LIKE ?
               OR t.payment_method LIKE ?
               OR t.amount LIKE ?
               OR t.id LIKE ?
               OR t.transaction_date LIKE ?)
               AND t.user_id = ?
            ORDER BY t.id DESC
        """, (f"%{search}%", f"%{search}%", f"%{search}%", f"%{search}%", f"%{search}%", f"%{search}%", f"%{search}%", user_id)).fetchall()
    else:
        transactions = conn.execute("""
            SELECT t.*, c.client_name, s.service_name
            FROM transactions t
            JOIN clients c ON t.client_id = c.id
            JOIN services s ON t.service_id = s.id
            WHERE t.user_id = ?
            ORDER BY t.id DESC
        """, (user_id,)).fetchall()

    clients = conn.execute("""
        SELECT * FROM clients
        WHERE id NOT IN (
            SELECT DISTINCT client_id FROM transactions WHERE user_id = ?
        )
        AND user_id = ?
        ORDER BY id ASC
    """, (user_id, user_id)).fetchall()
    services = conn.execute("SELECT * FROM services WHERE user_id = ? ORDER BY id ASC", (user_id,)).fetchall()
    today_str = date.today().strftime('%Y-%m-%d')

    conn.close()

    return render_template(
        "transactions/transactions.html",
        transactions=transactions,
        clients=clients,
        services=services,
        search_query=search,
        today_str=today_str
    )


@app.route('/edit_transaction/<int:id>', methods=['GET', 'POST'])
def edit_transaction(id):

    if 'user_id' not in session:
        return redirect(url_for('login'))

    user_id = session['user_id']
    conn = get_db()

    if request.method == 'POST':
        tx_date = request.form.get('transaction_date', '').strip() or date.today().strftime('%Y-%m-%d')
        conn.execute("""
            UPDATE transactions
            SET client_id=?, service_id=?, amount=?, payment_method=?, payment_status=?, transaction_date=?
            WHERE id=? AND user_id=?
        """, (
            request.form.get('client_id', '').strip(),
            request.form.get('service_id', '').strip(),
            request.form.get('amount', '').strip(),
            request.form.get('payment_method', '').strip(),
            request.form.get('payment_status', '').strip(),
            tx_date,
            id,
            user_id
        ))
        conn.commit()
        conn.close()
        return redirect(url_for('transactions'))

    transaction = conn.execute("""
        SELECT t.*, c.client_name, s.service_name
        FROM transactions t
        JOIN clients c ON t.client_id = c.id
        JOIN services s ON t.service_id = s.id
        WHERE t.id=? AND t.user_id=?
    """, (id, user_id)).fetchone()

    clients = conn.execute("""
        SELECT * FROM clients
        WHERE user_id = ? AND (
            id = ? OR id NOT IN (
                SELECT DISTINCT client_id FROM transactions WHERE user_id = ?
            )
        )
        ORDER BY id ASC
    """, (user_id, transaction['client_id'], user_id)).fetchall()
    services = conn.execute("SELECT * FROM services WHERE user_id=?", (user_id,)).fetchall()
    conn.close()

    return render_template(
        'transactions/edit_transaction.html',
        transaction=transaction,
        clients=clients,
        services=services
    )


def auto_archive_past_months(user_id):
    today = date.today()
    current_month_key = today.strftime('%Y-%m')

    conn = get_db()
    try:
        # Get all unique months that exist in the transactions table
        existing_months = conn.execute("""
            SELECT DISTINCT strftime('%Y-%m', transaction_date) as m_key 
            FROM transactions 
            WHERE transaction_date IS NOT NULL AND transaction_date != '' AND user_id = ?
        """, (user_id,)).fetchall()
        
        for row in existing_months:
            month_key = row['m_key']
            # If the month is older than the current active month
            if month_key and month_key < current_month_key:
                # Check if this month is already archived
                archived = conn.execute("""
                    SELECT 1 FROM monthly_records WHERE month_name = ? AND user_id = ?
                """, (month_key, user_id)).fetchone()
                
                if not archived:
                    # Calculate metrics for this past month
                    month_capital = conn.execute("""
                        SELECT IFNULL(SUM(amount), 0) FROM daily_capital
                        WHERE strftime('%Y-%m', record_date) = ? AND user_id = ?
                    """, (month_key, user_id)).fetchone()[0]

                    gross_paid_sales = conn.execute("""
                        SELECT IFNULL(SUM(amount), 0) FROM transactions 
                        WHERE payment_status='Paid' AND strftime('%Y-%m', transaction_date) = ? AND user_id = ?
                    """, (month_key, user_id)).fetchone()[0]

                    paid_sales = gross_paid_sales - month_capital

                    pending_sales = conn.execute("""
                        SELECT IFNULL(SUM(amount), 0) FROM transactions 
                        WHERE payment_status='Pending' AND strftime('%Y-%m', transaction_date) = ? AND user_id = ?
                    """, (month_key, user_id)).fetchone()[0]

                    total_sales = paid_sales

                    tx_count = conn.execute("""
                        SELECT COUNT(*) FROM transactions 
                        WHERE strftime('%Y-%m', transaction_date) = ? AND user_id = ?
                    """, (month_key, user_id)).fetchone()[0]

                    # Insert the finalized snapshot into archives
                    conn.execute("""
                        INSERT OR REPLACE INTO monthly_records (
                            month_name, total_sales, paid_sales, pending_sales, transaction_count, saved_at, user_id
                        ) VALUES (?, ?, ?, ?, ?, DATETIME('now', 'localtime'), ?)
                    """, (month_key, total_sales, paid_sales, pending_sales, tx_count, user_id))
        conn.commit()
    except Exception as e:
        print("Auto-archiver error:", e)
    finally:
        conn.close()


# =========================
# MONTHLY SALES RECORDS
# =========================
@app.route('/monthly_records')
def monthly_records():

    if 'user_id' not in session:
        return redirect(url_for('login'))

    user_id = session['user_id']

    # Auto-archive past months
    auto_archive_past_months(user_id)

    today = date.today()
    month_name = today.strftime('%B %Y')
    month_key = today.strftime('%Y-%m')

    conn = get_db()

    # Calculate active stats for the current month
    current_tx_count = conn.execute("""
        SELECT COUNT(*) FROM transactions 
        WHERE strftime('%Y-%m', transaction_date) = ? AND user_id = ?
    """, (month_key, user_id)).fetchone()[0]

    current_month_capital = conn.execute("""
        SELECT IFNULL(SUM(amount), 0) FROM daily_capital
        WHERE strftime('%Y-%m', record_date) = ? AND user_id = ?
    """, (month_key, user_id)).fetchone()[0]

    gross_paid_sales = conn.execute("""
        SELECT IFNULL(SUM(amount), 0) FROM transactions 
        WHERE payment_status='Paid' AND strftime('%Y-%m', transaction_date) = ? AND user_id = ?
    """, (month_key, user_id)).fetchone()[0]

    current_paid_sales = gross_paid_sales - current_month_capital

    current_pending_sales = conn.execute("""
        SELECT IFNULL(SUM(amount), 0) FROM transactions 
        WHERE payment_status='Pending' AND strftime('%Y-%m', transaction_date) = ? AND user_id = ?
    """, (month_key, user_id)).fetchone()[0]

    current_total_sales = current_paid_sales

    # Fetch archived monthly records
    archives = conn.execute("""
        SELECT * FROM monthly_records WHERE user_id = ? ORDER BY month_name DESC
    """, (user_id,)).fetchall()

    conn.close()

    return render_template(
        'monthly_records.html',
        current_month_name=month_name,
        current_month_key=month_key,
        current_tx_count=current_tx_count,
        current_paid_sales=current_paid_sales,
        current_pending_sales=current_pending_sales,
        current_total_sales=current_total_sales,
        archives=archives
    )


@app.route('/save_monthly_record/<month_name>', methods=['POST'])
def save_monthly_record(month_name):

    if 'user_id' not in session:
        return redirect(url_for('login'))

    user_id = session['user_id']
    conn = get_db()

    # Query metrics dynamically from transactions and daily_capital tables for this month
    month_capital = conn.execute("""
        SELECT IFNULL(SUM(amount), 0) FROM daily_capital
        WHERE strftime('%Y-%m', record_date) = ? AND user_id = ?
    """, (month_name, user_id)).fetchone()[0]

    gross_paid_sales = conn.execute("""
        SELECT IFNULL(SUM(amount), 0) FROM transactions 
        WHERE payment_status='Paid' AND strftime('%Y-%m', transaction_date) = ? AND user_id = ?
    """, (month_name, user_id)).fetchone()[0]

    paid_sales = gross_paid_sales - month_capital

    pending_sales = conn.execute("""
        SELECT IFNULL(SUM(amount), 0) FROM transactions 
        WHERE payment_status='Pending' AND strftime('%Y-%m', transaction_date) = ? AND user_id = ?
    """, (month_name, user_id)).fetchone()[0]

    total_sales = paid_sales

    tx_count = conn.execute("""
        SELECT COUNT(*) FROM transactions 
        WHERE strftime('%Y-%m', transaction_date) = ? AND user_id = ?
    """, (month_name, user_id)).fetchone()[0]

    # Insert or replace record
    conn.execute("""
        INSERT OR REPLACE INTO monthly_records (
            month_name, total_sales, paid_sales, pending_sales, transaction_count, saved_at, user_id
        ) VALUES (?, ?, ?, ?, ?, DATETIME('now', 'localtime'), ?)
    """, (month_name, total_sales, paid_sales, pending_sales, tx_count, user_id))

    conn.commit()
    conn.close()

    return redirect(url_for('monthly_records'))


@app.route('/delete_monthly_record/<int:id>')
def delete_monthly_record(id):

    if 'user_id' not in session:
        return redirect(url_for('login'))

    user_id = session['user_id']
    conn = get_db()
    conn.execute("DELETE FROM monthly_records WHERE id=? AND user_id=?", (id, user_id))
    conn.commit()
    conn.close()

    return redirect(url_for('monthly_records'))


# =========================
# DAILY SALES & CAPITAL
# =========================
@app.route('/daily_ledger', methods=['GET', 'POST'])
def daily_ledger():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    user_id = session['user_id']
    today_str = date.today().strftime('%Y-%m-%d')
    conn = get_db()

    # Calculate Today's Sales (Completed / Paid payments dated today)
    today_sales = conn.execute("""
        SELECT IFNULL(SUM(amount), 0) FROM transactions 
        WHERE payment_status = 'Paid' AND transaction_date = ? AND user_id = ?
    """, (today_str, user_id)).fetchone()[0]

    # Calculate Today's Capital (Outlays recorded today)
    today_capital = conn.execute("""
        SELECT IFNULL(SUM(amount), 0) FROM daily_capital 
        WHERE record_date = ? AND user_id = ?
    """, (today_str, user_id)).fetchone()[0]

    # Get detailed capital entries
    capital_entries = conn.execute("""
        SELECT id, amount, description, record_date FROM daily_capital 
        WHERE user_id = ?
        ORDER BY record_date DESC, id DESC
    """, (user_id,)).fetchall()

    # Get daily aggregates (Daily Sales vs Daily Capital history)
    daily_history = conn.execute("""
        SELECT d.date_val,
               IFNULL((SELECT SUM(amount) FROM transactions WHERE payment_status='Paid' AND transaction_date=d.date_val AND user_id=?), 0) as sales_total,
               IFNULL((SELECT SUM(amount) FROM daily_capital WHERE record_date=d.date_val AND user_id=?), 0) as capital_total
        FROM (
            SELECT DISTINCT transaction_date as date_val FROM transactions WHERE transaction_date IS NOT NULL AND transaction_date != '' AND user_id = ?
            UNION
            SELECT DISTINCT record_date as date_val FROM daily_capital WHERE record_date IS NOT NULL AND record_date != '' AND user_id = ?
        ) d
        ORDER BY d.date_val DESC
    """, (user_id, user_id, user_id, user_id)).fetchall()

    conn.close()

    return render_template(
        'daily_ledger.html',
        today_str=today_str,
        today_sales=today_sales,
        today_capital=today_capital,
        capital_entries=capital_entries,
        daily_history=daily_history
    )


@app.route('/save_daily_capital', methods=['POST'])
def save_daily_capital():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    user_id = session['user_id']
    amount = request.form.get('amount')
    description = request.form.get('description', '').strip()
    record_date = request.form.get('record_date')

    if not amount or not description or not record_date:
        return redirect(url_for('daily_ledger'))

    conn = get_db()
    conn.execute("""
        INSERT INTO daily_capital (amount, description, record_date, user_id)
        VALUES (?, ?, ?, ?)
    """, (amount, description, record_date, user_id))
    conn.commit()
    conn.close()

    return redirect(url_for('daily_ledger'))


@app.route('/delete_daily_capital/<int:id>')
def delete_daily_capital(id):
    if 'user_id' not in session:
        return redirect(url_for('login'))

    user_id = session['user_id']
    conn = get_db()
    conn.execute("DELETE FROM daily_capital WHERE id=? AND user_id=?", (id, user_id))
    conn.commit()
    conn.close()

    return redirect(url_for('daily_ledger'))


@app.route('/api/services')
def api_services():

    if 'user_id' not in session:
        return jsonify([])

    user_id = session['user_id']
    conn = get_db()
    services_raw = conn.execute("SELECT service_name, price FROM services WHERE user_id = ? ORDER BY price ASC", (user_id,)).fetchall()
    conn.close()

    return jsonify([{'name': s[0], 'price': s[1]} for s in services_raw])


# =========================
# RUN APP (ALWAYS LAST)
# =========================
if __name__ == '__main__':
    print(app.url_map)
    app.run(host='0.0.0.0', debug=True)