import sqlite3
import logging
import bleach
from threading import Lock
from flask import g
from flask_login import UserMixin

# Thread-safe lock for database operations
db_lock = Lock()

def get_db(database_path):
    if "db" not in g:
        try:
            g.db = sqlite3.connect(database_path)
            g.db.row_factory = sqlite3.Row
        except sqlite3.Error as e:
            logging.error(f"Database connection error: {e}")
            raise
    return g.db

def init_db(database_path):
    try:
        db = get_db(database_path)
        db.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL CHECK(length(username) <= 50),
            password TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL,
            message TEXT NOT NULL CHECK(length(message) <= 500),
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS friend_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            from_user TEXT NOT NULL,
            to_user TEXT NOT NULL,
            status TEXT DEFAULT 'pending',
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(from_user, to_user)
        );
        CREATE TABLE IF NOT EXISTS friendships (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user TEXT NOT NULL,
            friend TEXT NOT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user, friend)
        );
        CREATE TABLE IF NOT EXISTS private_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            from_user TEXT NOT NULL,
            to_user TEXT NOT NULL,
            message TEXT NOT NULL CHECK(length(message) <= 500),
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        );
        """)
        db.commit()
        logging.info("Database initialized successfully")
    except sqlite3.Error as e:
        logging.error(f"Database initialization error: {e}")
        raise

class User(UserMixin):
    def __init__(self, username):
        self.id = username

# Security utility functions
def sanitize_message(message):
    """Sanitize user input to prevent XSS attacks"""
    allowed_tags = []  # No HTML tags allowed in messages
    return bleach.clean(message, tags=allowed_tags, strip=True)

def validate_password_strength(password):
    """Validate password strength"""
    if len(password) < 8:
        return False, "Password must be at least 8 characters long."
    if not any(c.isupper() for c in password):
        return False, "Password must contain at least one uppercase letter."
    if not any(c.islower() for c in password):
        return False, "Password must contain at least one lowercase letter."
    if not any(c.isdigit() for c in password):
        return False, "Password must contain at least one number."
    return True, "Password is strong."

def validate_username(username):
    """Validate username format"""
    if not username or len(username) < 3:
        return False, "Username must be at least 3 characters long."
    if len(username) > 50:
        return False, "Username must be 50 characters or less."
    if not username.replace('_', '').replace('-', '').isalnum():
        return False, "Username can only contain letters, numbers, hyphens, and underscores."
    return True, "Username is valid."

# Enhanced database operations with proper error handling
def safe_db_execute(database_path, query, params=(), fetch_one=False, fetch_all=False):
    """Execute database queries safely with proper error handling"""
    try:
        with db_lock:
            db = get_db(database_path)
            cursor = db.execute(query, params)
            if fetch_one:
                result = cursor.fetchone()
            elif fetch_all:
                result = cursor.fetchall()
            else:
                result = cursor
            db.commit()
            return result
    except sqlite3.Error as e:
        logging.error(f"Database error: {e} - Query: {query} - Params: {params}")
        db.rollback()
        raise
