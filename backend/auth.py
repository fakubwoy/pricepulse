# auth.py
import secrets
from datetime import datetime, timedelta
from functools import wraps
from flask import request, jsonify, current_app
from models import User, UserSession
from database import db

def generate_session_token():
    """Generate a secure session token"""
    return secrets.token_urlsafe(32)

def create_user_session(user_id, expires_in_days=30):
    """Create a new session for a user"""
    session_token = generate_session_token()
    expires_at = datetime.utcnow() + timedelta(days=expires_in_days)
    
    session = UserSession(
        user_id=user_id,
        session_token=session_token,
        expires_at=expires_at
    )
    
    db.session.add(session)
    db.session.commit()
    
    return session_token

def get_current_user():
    """Get the current authenticated user from the session token"""
    auth_header = request.headers.get('Authorization')
    if not auth_header or not auth_header.startswith('Bearer '):
        return None
    
    token = auth_header.split(' ')[1]
    
    session = UserSession.query.filter_by(
        session_token=token, 
        is_active=True
    ).first()
    
    if not session or session.is_expired():
        if session:
            session.is_active = False
            db.session.commit()
        return None
    
    return session.user

def login_required(f):
    """Decorator to require authentication for endpoints"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        user = get_current_user()
        if not user:
            return jsonify({'error': 'Authentication required'}), 401
        
        # Add user to request context
        request.current_user = user
        return f(*args, **kwargs)
    
    return decorated_function

def logout_user(session_token):
    """Logout a user by deactivating their session"""
    session = UserSession.query.filter_by(
        session_token=session_token, 
        is_active=True
    ).first()
    
    if session:
        session.is_active = False
        db.session.commit()
        return True
    
    return False

def cleanup_expired_sessions():
    """Clean up expired sessions - can be run periodically"""
    expired_sessions = UserSession.query.filter(
        UserSession.expires_at < datetime.utcnow(),
        UserSession.is_active == True
    ).all()
    
    for session in expired_sessions:
        session.is_active = False
    
    db.session.commit()
    return len(expired_sessions)