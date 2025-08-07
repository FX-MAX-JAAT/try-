from flask import Blueprint, request, jsonify, session
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import check_password_hash, generate_password_hash
from utils import get_db, User, safe_db_execute, validate_username, validate_password_strength, sanitize_message
import logging
import os

api = Blueprint('api', __name__)
DATABASE = os.environ.get('DATABASE_PATH', 'chat.db')

@api.route('/api/login', methods=['POST'])
def api_login():
    data = request.get_json()
    username = data.get('username', '').strip()
    password = data.get('password', '').strip()
    
    # Validate username format
    is_valid, msg = validate_username(username)
    if not is_valid:
        return jsonify({'error': msg}), 400
    
    try:
        user = safe_db_execute(
            DATABASE,
            "SELECT * FROM users WHERE username = ?", 
            (username,), 
            fetch_one=True
        )
        if user and check_password_hash(user["password"], password):
            user_obj = User(username)
            login_user(user_obj, remember=False)
            session.permanent = True
            logging.info(f"User {username} logged in via API")
            return jsonify({'success': True, 'username': username})
        else:
            logging.warning(f"Failed API login attempt for username: {username}")
            return jsonify({'error': 'Invalid credentials'}), 401
    except Exception as e:
        logging.error(f"API login error: {e}")
        return jsonify({'error': 'Login failed'}), 500

@api.route('/api/register', methods=['POST'])
def api_register():
    data = request.get_json()
    username = data.get('username', '').strip()
    password = data.get('password', '').strip()
    
    # Validate username
    is_valid, msg = validate_username(username)
    if not is_valid:
        return jsonify({'error': msg}), 400
    
    # Validate password strength
    is_strong, pwd_msg = validate_password_strength(password)
    if not is_strong:
        return jsonify({'error': pwd_msg}), 400
    
    try:
        # Check if username already exists
        existing_user = safe_db_execute(
            DATABASE,
            "SELECT id FROM users WHERE username = ?", 
            (username,), 
            fetch_one=True
        )
        if existing_user:
            return jsonify({'error': 'Username already exists'}), 400
        
        # Create new user
        hashed = generate_password_hash(password, method='pbkdf2:sha256')
        safe_db_execute(
            DATABASE,
            "INSERT INTO users (username, password) VALUES (?, ?)", 
            (username, hashed)
        )
        
        logging.info(f"New user registered via API: {username}")
        return jsonify({'success': True, 'message': 'Registration successful'})
        
    except Exception as e:
        logging.error(f"API registration error: {e}")
        return jsonify({'error': 'Registration failed'}), 500

@api.route('/api/logout', methods=['POST'])
@login_required
def api_logout():
    logout_user()
    return jsonify({'success': True})

@api.route('/api/messages', methods=['GET'])
@login_required
def api_get_messages():
    try:
        db = get_db(DATABASE)
        messages = db.execute(
            "SELECT username, message, timestamp FROM messages ORDER BY id DESC LIMIT 100"
        ).fetchall()
        messages = list(reversed(messages))
        
        return jsonify({
            'messages': [
                {
                    'username': msg['username'],
                    'message': msg['message'],
                    'timestamp': msg['timestamp']
                } for msg in messages
            ]
        })
    except Exception as e:
        logging.error(f"API get messages error: {e}")
        return jsonify({'error': 'Failed to load messages'}), 500

@api.route('/api/friends', methods=['GET'])
@login_required
def api_get_friends():
    try:
        db = get_db(DATABASE)
        friends = db.execute("""
            SELECT DISTINCT 
                CASE 
                    WHEN user = ? THEN friend 
                    ELSE user 
                END as friend_name
            FROM friendships 
            WHERE user = ? OR friend = ?
        """, (current_user.id, current_user.id, current_user.id)).fetchall()
        
        return jsonify({
            'friends': [f['friend_name'] for f in friends]
        })
    except Exception as e:
        logging.error(f"API get friends error: {e}")
        return jsonify({'error': 'Failed to load friends'}), 500

@api.route('/api/friend-requests', methods=['GET'])
@login_required
def api_get_friend_requests():
    try:
        db = get_db(DATABASE)
        pending = db.execute(
            "SELECT * FROM friend_requests WHERE to_user=? AND status='pending'", 
            (current_user.id,)
        ).fetchall()
        
        return jsonify({
            'pending_requests': [
                {
                    'id': req['id'],
                    'from_user': req['from_user'],
                    'created_at': req['created_at']
                } for req in pending
            ]
        })
    except Exception as e:
        logging.error(f"API get friend requests error: {e}")
        return jsonify({'error': 'Failed to load friend requests'}), 500

@api.route('/api/send-friend-request/<to_user>', methods=['POST'])
@login_required
def api_send_friend_request(to_user):
    try:
        db = get_db(DATABASE)
        if to_user == current_user.id:
            return jsonify({'error': 'Cannot add yourself'}), 400
        
        # Check if user exists
        user_exists = db.execute("SELECT username FROM users WHERE username = ?", (to_user,)).fetchone()
        if not user_exists:
            return jsonify({'error': 'User not found'}), 404
        
        existing = db.execute(
            "SELECT id FROM friend_requests WHERE from_user=? AND to_user=? AND status='pending'",
            (current_user.id, to_user)).fetchone()
        already = db.execute(
            "SELECT id FROM friendships WHERE (user=? AND friend=?) OR (user=? AND friend=?)",
            (current_user.id, to_user, to_user, current_user.id)).fetchone()
        
        if not existing and not already:
            db.execute("INSERT INTO friend_requests (from_user, to_user) VALUES (?, ?)", (current_user.id, to_user))
            db.commit()
            return jsonify({'success': True, 'message': 'Friend request sent'})
        else:
            return jsonify({'error': 'Request already sent or you\'re already friends'}), 400
    except Exception as e:
        logging.error(f"API send friend request error: {e}")
        return jsonify({'error': 'Failed to send friend request'}), 500

@api.route('/api/respond-friend-request/<int:req_id>/<action>', methods=['POST'])
@login_required
def api_respond_friend_request(req_id, action):
    try:
        db = get_db(DATABASE)
        req = db.execute("SELECT * FROM friend_requests WHERE id=?", (req_id,)).fetchone()
        if req and req["to_user"] == current_user.id:
            if action == "accept":
                db.execute("UPDATE friend_requests SET status='accepted' WHERE id=?", (req_id,))
                db.execute("INSERT INTO friendships (user, friend) VALUES (?, ?)",
                           (req["from_user"], req["to_user"]))
                db.commit()
                return jsonify({'success': True, 'message': 'Friend request accepted'})
            else:
                db.execute("UPDATE friend_requests SET status='rejected' WHERE id=?", (req_id,))
                db.commit()
                return jsonify({'success': True, 'message': 'Friend request rejected'})
        else:
            return jsonify({'error': 'Friend request not found'}), 404
    except Exception as e:
        logging.error(f"API respond friend request error: {e}")
        return jsonify({'error': 'Failed to respond to friend request'}), 500

@api.route('/api/private-messages/<friend_username>', methods=['GET'])
@login_required
def api_get_private_messages(friend_username):
    try:
        db = get_db(DATABASE)
        # Check if users are friends
        friendship = db.execute(
            "SELECT id FROM friendships WHERE (user=? AND friend=?) OR (user=? AND friend=?)",
            (current_user.id, friend_username, friend_username, current_user.id)
        ).fetchone()
        
        if not friendship:
            return jsonify({'error': 'You can only chat with friends'}), 403
        
        # Get private message history
        messages = db.execute("""
            SELECT from_user, to_user, message, timestamp 
            FROM private_messages 
            WHERE (from_user = ? AND to_user = ?) OR (from_user = ? AND to_user = ?) 
            ORDER BY id DESC LIMIT 100
        """, (current_user.id, friend_username, friend_username, current_user.id)).fetchall()
        
        messages = list(reversed(messages))
        
        return jsonify({
            'messages': [
                {
                    'from_user': msg['from_user'],
                    'to_user': msg['to_user'],
                    'message': msg['message'],
                    'timestamp': msg['timestamp']
                } for msg in messages
            ]
        })
    except Exception as e:
        logging.error(f"API get private messages error: {e}")
        return jsonify({'error': 'Failed to load private messages'}), 500

@api.route('/api/search-users', methods=['GET'])
@login_required
def api_search_users():
    query = request.args.get('query', '').strip()
    if not query or len(query) < 2:
        return jsonify(users=[])
    
    # Sanitize search query
    query = sanitize_message(query)
    
    try:
        search_pattern = f"%{query}%"
        users = safe_db_execute(DATABASE, """
            SELECT DISTINCT u.username, 
                   CASE WHEN f.user IS NOT NULL OR f.friend IS NOT NULL THEN 1 ELSE 0 END as is_friend,
                   CASE WHEN fr.id IS NOT NULL THEN 1 ELSE 0 END as has_pending_request
            FROM users u
            LEFT JOIN friendships f ON (f.user = ? AND f.friend = u.username) OR (f.friend = ? AND f.user = u.username)
            LEFT JOIN friend_requests fr ON (fr.from_user = ? AND fr.to_user = u.username AND fr.status = 'pending')
            WHERE u.username LIKE ? AND u.username != ? AND u.username != 'admin'
            LIMIT 10
        """, (current_user.id, current_user.id, current_user.id, search_pattern, current_user.id), fetch_all=True)
        
        result = []
        for user in users:
            status = 'available'
            if user['is_friend']:
                status = 'friend'
            elif user['has_pending_request']:
                status = 'pending'
            
            result.append({
                'username': sanitize_message(user['username']),
                'status': status
            })
        
        return jsonify(users=result)
    except Exception as e:
        logging.error(f"API search users error: {e}")
        return jsonify(users=[], error="Search failed"), 500
