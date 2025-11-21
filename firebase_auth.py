from functools import wraps
from flask import request, jsonify, session
from firebase_admin import auth
import os

def verify_firebase_token():
    """Verify Firebase ID token from Authorization header"""
    auth_header = request.headers.get('Authorization', '')
    if not auth_header.startswith('Bearer '):
        return None, 'No Bearer token provided'
    
    token = auth_header.split('Bearer ')[1]
    try:
        # For testing: if we're in development and it's a custom token
        if os.getenv('FLASK_ENV') == 'development':
            try:
                # First try to verify as custom token
                decoded_claims = auth.verify_id_token(token, check_revoked=False)
            except:
                # If that fails, try parsing the custom token directly
                if '.' in token:  # Basic check for JWT format
                    # For testing, extract UID from custom token
                    decoded_claims = {'uid': token.split('.')[0]}
                else:
                    decoded_claims = {'uid': token}  # Fallback for simple tokens
        else:
            # In production, always verify as ID token
            decoded_claims = auth.verify_id_token(token)
        
        if not decoded_claims or 'uid' not in decoded_claims:
            return None, 'Invalid token format'
            
        return decoded_claims, None
    except Exception as e:
        return None, f'Invalid token: {str(e)}'

def firebase_auth_required(f):
    """Decorator to require Firebase authentication"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        decoded_token, error = verify_firebase_token()
        if error:
            return jsonify({'success': False, 'message': error}), 401
        return f(*args, firebase_uid=decoded_token['uid'], **kwargs)
    return decorated_function