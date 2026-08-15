import os

# Central Configuration for Sales Manager Application

BASE_DIR = os.path.abspath(os.path.dirname(__file__))

# Flask Application Secret Key
SECRET_KEY = os.environ.get('SECRET_KEY', 'sales-manager-secure-prod-key-2026-v2')

# Gmail Real-Time SMTP Delivery Configuration
# To send live emails directly to your physical Gmail inbox:
# 1. Enable 2-Step Verification on your Google/Gmail Account
# 2. Generate a 16-character App Password (Google Account > Security > App Passwords)
# 3. Enter your Gmail address and 16-character App Password below:
MAIL_SERVER = os.environ.get('MAIL_SERVER', 'smtp.gmail.com')
MAIL_PORT = int(os.environ.get('MAIL_PORT', 587))
MAIL_USERNAME = os.environ.get('MAIL_USERNAME', '')  # e.g., "your_gmail@gmail.com"
MAIL_PASSWORD = os.environ.get('MAIL_PASSWORD', '')  # 16-character Google App Password

# Security & Lockout Parameters
MAX_OTP_ATTEMPTS = 3  # Lock out after 3 failed OTP guesses
OTP_EXPIRY_MINUTES = 10  # OTP valid for 10 minutes
OTP_COOLDOWN_SECONDS = 60  # 60s cooldown before resending new code
