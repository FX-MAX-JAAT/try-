import sqlite3
from flask import Flask, request, g, jsonify, session
from flask_socketio import SocketIO, send, emit, join_room
from flask_login import (
    LoginManager, UserMixin,
    login_required,
    current_user
)
from werkzeug.security import generate_password_hash, check_password_hash
from flask_wtf import CSRFProtect
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from datetime import datetime, timedelta
import os
import logging
from functools import wraps
import bleach
import secrets
from threading import Lock
from flask_cors import CORS
from utils import get_db, init_db, User, safe_db_execute, validate_username, validate_password_strength, sanitize_message

app = Flask(__name__)

# Enable CORS for frontend
CORS(app, origins=["https://your-frontend-domain.netlify.app", "http://localhost:3000"], 
     supports_credentials=True)

# Security configurations
app.config["SECRET_KEY"] = os.environ.get('SECRET_KEY') or secrets.token_hex(32)
app.config['WTF_CSRF_TIME_LIMIT'] = 3600  # 1 hour CSRF token lifetime
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(hours=2)  # 2 hour session timeout
app.config['SESSION_COOKIE_SECURE'] = os.environ.get('FLASK_ENV') == 'production'
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'

DATABASE = os.environ.get('DATABASE_PATH', 'chat.db')

# Configure logging with more detail
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(name)s %(message)s',
    handlers=[
        logging.FileHandler('chat_app.log'),
        logging.StreamHandler()
    ]
)

# Initialize security extensions
csrf = CSRFProtect(app)
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["200 per day", "50 per hour"]
)
limiter.init_app(app)

# Connected users tracking
connected_users = set()

# Initialize Flask extensions - auto-detect best async mode
socketio = SocketIO(app, cors_allowed_origins=["https://your-frontend-domain.netlify.app", "http://localhost:3000"])
login_manager = LoginManager()
login_manager.login_view = "login"
login_manager.session_protection = "strong"
login_manager.init_app(app)

# Register API blueprint
from api import api
app.register_blueprint(api)

# Initialize database for production
with app.app_context():
    init_db(DATABASE)

@app.teardown_appcontext
def close_db(exception):
    db = g.pop("db", None)
    if db is not None:
        db.close()

@login_manager.user_loader
def load_user(user_id):
    try:
        db = get_db(DATABASE)
        user = db.execute("SELECT username FROM users WHERE username = ?", (user_id,)).fetchone()
        return User(user_id) if user else None
    except sqlite3.Error as e:
        logging.error(f"Error loading user {user_id}: {e}")
        return None

# SocketIO authentication decorator
def socketio_login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            return False
        return f(*args, **kwargs)
    return decorated_function

@app.route("/")
def index():
    return "Chat App Backend API - Use the frontend to interact with the application"

@socketio.on("message")
@socketio_login_required
def handle_public_message(data):
    if not current_user.is_authenticated:
        return False
    
    try:
        db = get_db(DATABASE)
        username = current_user.id
        msg = data.get("msg", "").strip()
        
        # Validate message
        if not msg or len(msg) > 500:
            return False
        
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        db.execute("INSERT INTO messages (username, message, timestamp) VALUES (?, ?, ?)",
                   (username, msg, timestamp))
        db.commit()
        send({"msg": msg, "user": username, "time": timestamp}, broadcast=True)
    except sqlite3.Error as e:
        logging.error(f"Message handling error: {e}")
        return False

@socketio.on("connect")
def on_connect():
    if current_user.is_authenticated:
        join_room(current_user.id)

@socketio.on("private_message")
@socketio_login_required
def handle_private(data):
    if not current_user.is_authenticated:
        return False
    
    try:
        db = get_db(DATABASE)
        to_user = data.get("to", "").strip()
        msg = data.get("msg", "").strip()
        
        # Validate message and recipient
        if not msg or not to_user or len(msg) > 500:
            return False
        
        # Check if users are friends
        friendship = db.execute(
            "SELECT id FROM friendships WHERE (user=? AND friend=?) OR (user=? AND friend=?)",
            (current_user.id, to_user, to_user, current_user.id)
        ).fetchone()
        
        if not friendship:
            return False  # Only allow messages between friends
        
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        db.execute("INSERT INTO private_messages (from_user, to_user, message, timestamp) VALUES (?, ?, ?, ?)",
                   (current_user.id, to_user, msg, timestamp))
        db.commit()
        
        emit("private_message", {
            "msg": msg,
            "from": current_user.id,
            "time": timestamp
        }, room=to_user)
        emit("private_message", {
            "msg": msg,
            "from": "You",
            "time": timestamp
        }, room=current_user.id)
    except sqlite3.Error as e:
        logging.error(f"Private message handling error: {e}")
        return False

if __name__ == "__main__":
    socketio.run(app, debug=True)
