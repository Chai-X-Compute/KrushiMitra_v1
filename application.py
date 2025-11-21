from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from flask_cors import CORS
from dotenv import load_dotenv
import os
import requests
from datetime import datetime, timedelta
import json
import time
from functools import wraps
from database import db, init_db, User, Resource, Transaction
from urllib.parse import quote_plus
import boto3
from werkzeug.utils import secure_filename
import uuid
import firebase_admin
from firebase_admin import credentials, auth

# Load environment variables
load_dotenv()

# Firebase initialization
try:
    # Check if already initialized
    firebase_admin.get_app()
except ValueError:
    # Not initialized, do initialization
    try:
        service_account_path = os.path.join(os.path.dirname(__file__), 'serviceAccountKey.json')
        if os.path.exists(service_account_path):
            cred = credentials.Certificate(service_account_path)
            firebase_admin.initialize_app(cred)
            print("✅ Firebase initialized successfully")
        else:
            print("❌ Firebase service account file not found")
            if os.environ.get('VERCEL'):
                # On Vercel, we need Firebase working
                raise Exception("Firebase configuration required for Vercel deployment")
    except Exception as e:
        print(f"❌ Firebase initialization error: {str(e)}")
        if os.environ.get('VERCEL'):
            raise

application = Flask(__name__)

# Security configuration
if os.environ.get('VERCEL') or os.environ.get('PRODUCTION'):
    if not os.getenv('SECRET_KEY'):
        raise ValueError("SECRET_KEY must be set in production")
    application.config['SECRET_KEY'] = os.getenv('SECRET_KEY')
    application.config['SESSION_COOKIE_SECURE'] = True
    application.config['SESSION_COOKIE_HTTPONLY'] = True
    application.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
    application.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=1)
    application.config['SESSION_COOKIE_NAME'] = '__Host-session'  # Secure naming
else:
    # Development settings
    application.config['SECRET_KEY'] = os.getenv('SECRET_KEY') or 'dev-secret-change-me'
    print("⚠️ Using development secret key. Do not use in production!")
db_url = os.getenv('DATABASE_URL')
if not db_url:
    db_user = os.getenv('DB_USER')
    db_password = os.getenv('DB_PASS') or os.getenv('DB_PASSWORD')
    db_host = os.getenv('DB_HOST')
    db_name = os.getenv('DB_NAME')
    db_port = os.getenv('DB_PORT', '3306')
    if all([db_user, db_password, db_host, db_name]):
        safe_password = quote_plus(db_password)
        # Add connection pooling and retry parameters
        params = {
            'pool_size': int(os.getenv('DB_POOL_SIZE', '10')),
            'max_overflow': int(os.getenv('DB_MAX_OVERFLOW', '20')),
            'pool_timeout': int(os.getenv('DB_POOL_TIMEOUT', '30')),
            'pool_recycle': int(os.getenv('DB_POOL_RECYCLE', '1800')),  # 30 minutes
            'pool_pre_ping': True  # Enable connection health checks
        }
        param_str = '&'.join(f'{k}={v}' for k, v in params.items())
        db_url = f"mysql+pymysql://{db_user}:{safe_password}@{db_host}:{db_port}/{db_name}?{param_str}"
if not db_url:
    raise ValueError("DATABASE_URL environment variable is not set. Please provide a valid MySQL connection string.")
application.config['SQLALCHEMY_DATABASE_URI'] = db_url
application.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
application.config['UPLOAD_FOLDER'] = 'static/uploads'
application.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size

# Configure CORS
if os.environ.get('VERCEL') or os.environ.get('PRODUCTION'):
    # Production CORS settings
    allowed_origins = os.getenv('ALLOWED_ORIGINS', '').split(',')
    CORS(application, 
         resources={r"/api/*": {"origins": allowed_origins}},
         supports_credentials=True)
else:
    # Development CORS settings
    CORS(application)
    print("⚠️ Using development CORS settings. Configure ALLOWED_ORIGINS in production!")

# Initialize database
init_db(application)

# AWS S3 Configuration
s3_client = None
if os.getenv('AWS_ACCESS_KEY_ID'):
    try:
        s3_client = boto3.client(
            's3',
            aws_access_key_id=os.getenv('AWS_ACCESS_KEY_ID'),
            aws_secret_access_key=os.getenv('AWS_SECRET_ACCESS_KEY'),
            region_name=os.getenv('AWS_REGION')
        )
        # Test S3 connection and bucket access
        s3_client.head_bucket(Bucket=os.getenv('S3_BUCKET'))
        print("✅ S3 connection and bucket access verified")
    except Exception as e:
        print(f"❌ S3 initialization failed: {e}")
        # On Vercel, we need S3 working
        if os.environ.get('VERCEL'):
            raise Exception("S3 configuration required for Vercel deployment")

# Weather API Configuration
WEATHER_API_KEY = os.getenv('WEATHER_API_KEY')
WEATHER_BASE_URL = "https://api.openweathermap.org/data/2.5"

# Allowed file extensions
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Check session for Flask user_id
        if 'user_id' not in session:
            # Check for Firebase token in Authorization header
            auth_header = request.headers.get('Authorization')
            if not auth_header or not auth_header.startswith('Bearer '):
                if request.is_json or request.path.startswith('/api/'):
                    return jsonify({'success': False, 'message': 'Authentication required'}), 401
                return redirect(url_for('login', next=request.url))
            
            try:
                # Verify the token with Firebase
                id_token = auth_header.split('Bearer ')[1]
                decoded_token = auth.verify_id_token(id_token)
                firebase_uid = decoded_token['uid']
                
                # Find user by Firebase UID
                user = User.query.filter_by(firebase_uid=firebase_uid).first()
                if not user:
                    if request.is_json or request.path.startswith('/api/'):
                        return jsonify({'success': False, 'message': 'User not found'}), 404
                    return redirect(url_for('login', next=request.url))
                
                # Set session
                session['user_id'] = user.id
            except Exception as e:
                if request.is_json or request.path.startswith('/api/'):
                    return jsonify({'success': False, 'message': 'Invalid authentication token'}), 401
                return redirect(url_for('login', next=request.url))
        
        return f(*args, **kwargs)
    return decorated_function

# Create upload folder if it doesn't exist
os.makedirs(application.config['UPLOAD_FOLDER'], exist_ok=True)

@application.route('/')
def index():
    # Allow browsing without login, redirect to marketplace
    return redirect(url_for('marketplace'))

@application.route('/login')
def login():
    next_url = request.args.get('next', url_for('dashboard'))
    # If user is already logged in, redirect to next_url
    if 'user_id' in session:
        return redirect(next_url)
    return render_template('login.html', next_url=next_url)

@application.route('/signup')
def signup():
    return render_template('signup.html')

@application.route('/dashboard')
def dashboard():
    user = None
    if 'user_id' in session:
        user = User.query.get(session['user_id'])
    return render_template('dashboard.html', user=user)

@application.route('/marketplace')
def marketplace():
    user = None
    if 'user_id' in session:
        user = User.query.get(session['user_id'])
    return render_template('marketplace.html', user=user)

@application.route('/add-resource')
@login_required
def add_resource():
    user = User.query.get(session['user_id'])
    return render_template('add_resource.html', user=user)

@application.route('/my-resources')
@login_required
def my_resources():
    user = User.query.get(session['user_id'])
    return render_template('my_resources.html', user=user)

@application.route('/profile')
@login_required
def profile():
    user = User.query.get(session['user_id'])
    return render_template('profile.html', user=user)

# API Routes

@application.route('/api/auth/register', methods=['POST'])
def register():
    try:
        data = request.json
        
        # Get the ID token from Authorization header
        auth_header = request.headers.get('Authorization', '')
        if not auth_header.startswith('Bearer '):
            return jsonify({'success': False, 'message': 'No Bearer token provided'}), 401
        
        id_token = auth_header.split('Bearer ')[1]
        try:
            # For testing: if we're in development and it looks like a custom token
            if os.getenv('FLASK_ENV') == 'development':
                firebase_uid = id_token  # Use token directly as UID in dev mode
            else:
                # In production, always verify tokens
                decoded_token = auth.verify_id_token(id_token)
                firebase_uid = decoded_token['uid']
        except Exception as e:
            return jsonify({'success': False, 'message': 'Invalid ID token'}), 401
        
        # Check if user already exists
        existing_user = User.query.filter((User.email == data['email']) | (User.firebase_uid == firebase_uid)).first()
        if existing_user:
            # Update existing user's Firebase UID if needed
            if existing_user.firebase_uid != firebase_uid:
                existing_user.firebase_uid = firebase_uid
                db.session.commit()
            session['user_id'] = existing_user.id
            return jsonify({
                'success': True,
                'message': 'User already exists, updated Firebase UID',
                'user': {
                    'id': existing_user.id,
                    'name': existing_user.name,
                    'email': existing_user.email
                }
            })
        
        # Create new user
        user = User(
            firebase_uid=firebase_uid,
            email=data['email'],
            name=data['name'],
            phone=data.get('phone', ''),
            location=data.get('location', ''),
            language_preference=data.get('language', 'en')
        )
        
        db.session.add(user)
        db.session.commit()
        
        session['user_id'] = user.id
        
        return jsonify({
            'success': True,
            'message': 'Registration successful',
            'user': {
                'id': user.id,
                'name': user.name,
                'email': user.email
            }
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500

@application.route('/api/auth/login', methods=['POST'])
def api_login():
    try:
        data = request.json
        if not data:
            return jsonify({
                'success': False,
                'message': 'Missing request body',
                'error': 'MISSING_DATA'
            }), 400

        # Get the ID token from Authorization header
        auth_header = request.headers.get('Authorization', '')
        if not auth_header.startswith('Bearer '):
            return jsonify({
                'success': False,
                'message': 'No Bearer token provided',
                'error': 'MISSING_TOKEN'
            }), 401
        
        id_token = auth_header.split('Bearer ')[1]
        try:
            # For testing: if we're in development and it looks like a custom token
            if os.getenv('FLASK_ENV') == 'development':
                firebase_uid = id_token  # Use token directly as UID in dev mode
                app.logger.debug('Development mode: Using token as UID')
            else:
                # In production, always verify tokens
                decoded_token = auth.verify_id_token(id_token)
                firebase_uid = decoded_token['uid']
                app.logger.debug(f'Production mode: Verified token for UID {firebase_uid}')
        except Exception as e:
            app.logger.error(f'Token verification error: {str(e)}')
            return jsonify({
                'success': False,
                'message': 'Invalid authentication token',
                'error': 'INVALID_TOKEN'
            }), 401
        
        # Find user by email or firebase_uid
        user = User.query.filter((User.email == data.get('email')) | 
                               (User.firebase_uid == firebase_uid)).first()
        
        if not user:
            return jsonify({
                'success': False,
                'message': 'User not found. Please register first.',
                'error': 'USER_NOT_FOUND'
            }), 404
        
        # Update Firebase UID if needed
        if user.firebase_uid != firebase_uid:
            try:
                user.firebase_uid = firebase_uid
                db.session.commit()
                app.logger.info(f'Updated Firebase UID for user {user.id}')
            except Exception as e:
                app.logger.error(f'Failed to update Firebase UID: {str(e)}')
                db.session.rollback()
                return jsonify({
                    'success': False,
                    'message': 'Failed to update user data',
                    'error': 'DATABASE_ERROR'
                }), 500
        
        session['user_id'] = user.id
        
        return jsonify({
            'success': True,
            'message': 'Login successful',
            'user': {
                'id': user.id,
                'name': user.name,
                'email': user.email,
                'location': user.location,
                'phone': user.phone,
                'language_preference': user.language_preference,
                'firebase_uid': user.firebase_uid
            }
        })
    except Exception as e:
        app.logger.error(f'Login error: {str(e)}')
        return jsonify({
            'success': False,
            'message': 'An error occurred during login',
            'error': 'SERVER_ERROR'
        }), 500

@application.route('/api/auth/logout', methods=['POST'])
def logout():
    session.pop('user_id', None)
    return jsonify({'success': True, 'message': 'Logged out successfully'})

@application.route('/api/config/firebase')
def firebase_config():
    try:
        config = {
            'apiKey': os.getenv('FIREBASE_API_KEY'),
            'authDomain': os.getenv('FIREBASE_AUTH_DOMAIN'),
            'projectId': os.getenv('FIREBASE_PROJECT_ID'),
            'storageBucket': os.getenv('FIREBASE_STORAGE_BUCKET'),
            'messagingSenderId': os.getenv('FIREBASE_MESSAGING_SENDER_ID'),
            'appId': os.getenv('FIREBASE_APP_ID')
        }
        # Verify all required fields are present
        if not all(config.values()):
            missing = [k for k, v in config.items() if not v]
            app.logger.error(f'Missing Firebase config values: {missing}')
            return jsonify({
                'success': False,
                'message': 'Firebase configuration is incomplete'
            }), 500
        return jsonify({'success': True, 'config': config})
    except Exception as e:
        app.logger.error(f'Error getting Firebase config: {str(e)}')
        return jsonify({
            'success': False,
            'message': 'Failed to load Firebase configuration'
        }), 500

@application.route('/api/weather', methods=['GET'])
def get_weather():
    try:
        lat = request.args.get('lat')
        lon = request.args.get('lon')
        city = request.args.get('city')
        
        print(f"🌍 Weather request - Lat: {lat}, Lon: {lon}, City: {city}")
        
        if lat and lon:
            url = f"{WEATHER_BASE_URL}/weather?lat={lat}&lon={lon}&appid={WEATHER_API_KEY}&units=metric"
            print(f"📍 Using coordinates: {lat}, {lon}")
        elif city:
            url = f"{WEATHER_BASE_URL}/weather?q={city},IN&appid={WEATHER_API_KEY}&units=metric"
            print(f"🏙️ Using city: {city}")
        else:
            return jsonify({'success': False, 'message': 'Location required'}), 400
        
        print(f"🌐 API URL: {url}")
        response = requests.get(url, timeout=10)
        data = response.json()
        
        print(f"📊 API Response Status: {response.status_code}")
        
        if response.status_code == 200:
            # Return the full OpenWeatherMap response JSON so the frontend
            # display functions (which expect fields like `main`, `weather`,
            # `sys`, etc.) can use it directly.
            print(f"✅ Weather data for: {data.get('name')}, {data.get('sys', {}).get('country')}")
            return jsonify({'success': True, 'data': data})
        else:
            print(f"❌ Weather API error: {data.get('message', 'Unknown error')}")
            return jsonify({'success': False, 'message': data.get('message', 'Weather data not found')}), 404
            
    except Exception as e:
        print(f"❌ Weather exception: {str(e)}")
        return jsonify({'success': False, 'message': str(e)}), 500

@application.route('/api/weather/forecast', methods=['GET'])
def get_forecast():
    try:
        lat = request.args.get('lat')
        lon = request.args.get('lon')
        
        if not lat or not lon:
            return jsonify({'success': False, 'message': 'Location required'}), 400
        
        url = f"{WEATHER_BASE_URL}/forecast?lat={lat}&lon={lon}&appid={WEATHER_API_KEY}&units=metric"
        response = requests.get(url)
        data = response.json()
        
        if response.status_code == 200:
            forecast_list = []
            for item in data['list'][:8]:  # Next 24 hours (3-hour intervals)
                forecast_list.append({
                    'time': item['dt_txt'],
                    'temperature': item['main']['temp'],
                    'description': item['weather'][0]['description'],
                    'icon': item['weather'][0]['icon']
                })
            
            return jsonify({'success': True, 'data': forecast_list})
        else:
            return jsonify({'success': False, 'message': 'Forecast data not found'}), 404
            
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@application.route('/api/resources', methods=['GET'])
def get_resources():
    try:
        category = request.args.get('category')
        sort_by = request.args.get('sort', 'newest')
        search = request.args.get('search', '')
        
        query = Resource.query.filter_by(is_available=True)
        
        if category and category != 'all':
            query = query.filter_by(category=category)
        
        if search:
            query = query.filter(Resource.name.ilike(f'%{search}%'))
        
        # Sorting
        if sort_by == 'price_low':
            query = query.order_by(Resource.price.asc())
        elif sort_by == 'price_high':
            query = query.order_by(Resource.price.desc())
        elif sort_by == 'rating':
            query = query.order_by(Resource.rating.desc())
        else:  # newest
            query = query.order_by(Resource.created_at.desc())
        
        resources = query.all()
        
        resources_list = []
        for resource in resources:
            owner = User.query.get(resource.owner_id)
            # Validate and set fallback for image URL
            image_url = resource.image_url
            if not image_url or not image_url.strip():
                image_url = '/static/images/placeholder.svg'
            elif image_url.startswith('/static/'):
                # For local files, check if they exist
                file_path = os.path.join(application.root_path, image_url.lstrip('/'))
                if not os.path.exists(file_path):
                    image_url = '/static/images/placeholder.svg'
            
            resources_list.append({
                'id': resource.id,
                'name': resource.name,
                'category': resource.category,
                'description': resource.description,
                'price': resource.price,
                'listing_type': resource.listing_type,
                'condition': resource.condition,
                'age_years': resource.age_years,
                'quality': resource.quality,
                'image_url': image_url,
                'rating': resource.rating,
                'owner': {
                    'name': owner.name,
                    'phone': owner.phone,
                    'location': owner.location
                },
                'created_at': resource.created_at.isoformat()
            })
        
        return jsonify({'success': True, 'data': resources_list})
        
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@application.route('/api/resources/my', methods=['GET'])
@login_required
def get_my_resources():
    try:
        resources = Resource.query.filter_by(owner_id=session['user_id']).all()
        
        resources_list = []
        for resource in resources:
            resources_list.append({
                'id': resource.id,
                'name': resource.name,
                'category': resource.category,
                'description': resource.description,
                'price': resource.price,
                'listing_type': resource.listing_type,
                'condition': resource.condition,
                'is_available': resource.is_available,
                'image_url': resource.image_url,
                'rating': resource.rating,
                'created_at': resource.created_at.isoformat()
            })
        
        return jsonify({'success': True, 'data': resources_list})
        
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@application.route('/api/resources', methods=['POST'])
@login_required
def create_resource():
    try:
        # Handle file upload
        image_url = '/static/images/placeholder.svg'
        
        if 'image' in request.files:
            file = request.files['image']
            if file and file.filename and allowed_file(file.filename):
                filename = secure_filename(file.filename)
                unique_filename = f"{uuid.uuid4()}_{filename}"
                
                # Check if we're on Vercel (or other cloud platform)
                is_vercel = os.environ.get('VERCEL', False)
                
                if s3_client:
                    try:
                        # Validate file size before upload
                        file.seek(0, os.SEEK_END)
                        size = file.tell()
                        file.seek(0)
                        
                        if size > application.config['MAX_CONTENT_LENGTH']:
                            return jsonify({
                                'success': False,
                                'message': f'File too large. Maximum size is {application.config["MAX_CONTENT_LENGTH"] / (1024 * 1024)}MB'
                            }), 413

                        # Validate content type
                        content_type = file.content_type
                        if not content_type.startswith('image/'):
                            return jsonify({
                                'success': False,
                                'message': 'Invalid file type. Only images are allowed.'
                            }), 415

                        # Ensure the bucket exists
                        bucket = os.getenv('S3_BUCKET')
                        try:
                            s3_client.head_bucket(Bucket=bucket)
                        except:
                            app.logger.error(f"S3 bucket {bucket} not found or not accessible")
                            return jsonify({
                                'success': False,
                                'message': 'Storage configuration error'
                            }), 500

                        # Upload with retry
                        max_retries = 3
                        for attempt in range(max_retries):
                            try:
                                s3_client.upload_fileobj(
                                    file,
                                    bucket,
                                    unique_filename,
                                    ExtraArgs={
                                        'ContentType': content_type,
                                        'CacheControl': 'max-age=31536000'  # 1 year cache
                                    }
                                )
                                s3_url = f"https://{bucket}.s3.{os.getenv('AWS_REGION')}.amazonaws.com/{unique_filename}"
                                image_url = s3_url
                                app.logger.info(f"✅ Image uploaded to S3: {s3_url}")
                                break
                            except Exception as e:
                                if attempt == max_retries - 1:
                                    app.logger.error(f"❌ S3 upload failed after {max_retries} attempts: {str(e)}")
                                    return jsonify({
                                        'success': False,
                                        'message': 'Failed to upload image'
                                    }), 500
                                app.logger.warning(f"⚠️ S3 upload attempt {attempt + 1} failed: {str(e)}")
                                time.sleep(1)  # Wait before retry
                                
                    except Exception as e:
                        app.logger.error(f"❌ S3 upload error: {str(e)}")
                        return jsonify({
                            'success': False,
                            'message': 'Failed to process image upload'
                        }), 500
                
                # Only try local storage if we're not on Vercel and S3 upload failed
                elif not is_vercel:
                    try:
                        os.makedirs(application.config['UPLOAD_FOLDER'], exist_ok=True)
                        filepath = os.path.join(application.config['UPLOAD_FOLDER'], unique_filename)
                        file.save(filepath)
                        image_url = f"/static/uploads/{unique_filename}"
                        print(f"✅ Image saved locally: {image_url}")
                    except Exception as e:
                        print(f"❌ Local save failed: {e}")
                        return jsonify({'success': False, 'message': 'Failed to save image'}), 500
                else:
                    # We're on Vercel but S3 isn't configured
                    return jsonify({'success': False, 'message': 'Image upload not available - S3 not configured'}), 500
            else:
                print(f"⚠️ No valid image file provided or invalid file type")
        
        # Validate image URL before creating resource
        if not image_url or not isinstance(image_url, str) or not image_url.strip():
            image_url = '/static/images/placeholder.svg'
        
        # Create resource
        resource = Resource(
            owner_id=session['user_id'],
            name=request.form['name'],
            category=request.form['category'],
            description=request.form.get('description', ''),
            # Use safe conversions for numeric fields. If fields are missing or
            # empty strings, fall back to sensible defaults to avoid ValueError.
            price=float(request.form.get('price') or 0.0),
            listing_type=request.form.get('listing_type') or 'sell',
            condition=request.form.get('condition', 'good'),
            age_years=int(request.form.get('age_years') or 0),
            quality=int(request.form.get('quality') or 5),
            image_url=image_url,
            location=request.form.get('location', '')
        )
        
        db.session.add(resource)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Resource added successfully',
            'resource_id': resource.id
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500

@application.route('/api/resources/<int:resource_id>', methods=['GET'])
def get_resource_detail(resource_id):
    try:
        resource = Resource.query.get(resource_id)
        
        if not resource:
            return jsonify({'success': False, 'message': 'Resource not found'}), 404
        
        # Get owner information
        owner = User.query.get(resource.owner_id)
        
        # Validate image URL
        image_url = resource.image_url
        if not image_url or not isinstance(image_url, str) or not image_url.strip():
            image_url = '/static/images/placeholder.svg'
        elif image_url.startswith('/static/'):
            file_path = os.path.join(application.root_path, image_url.lstrip('/'))
            if not os.path.exists(file_path):
                image_url = '/static/images/placeholder.svg'
        
        resource_data = {
            'id': resource.id,
            'name': resource.name,
            'description': resource.description,
            'category': resource.category,
            'listing_type': resource.listing_type,
            'price': float(resource.price),
            'condition': resource.condition,
            'age': resource.age_years,
            'quality': resource.quality,
            'location': resource.location,
            'image_url': image_url,
            'is_available': resource.is_available,
            'created_at': resource.created_at.isoformat() if resource.created_at else None,
            'owner': {
                'name': owner.name if owner else 'Owner',
                'email': owner.email if owner else '',
                'phone': owner.phone if owner else '',
                'location': owner.location if owner else ''
            }
        }
        
        return jsonify({'success': True, 'data': resource_data})
        
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@application.route('/api/resources/<int:resource_id>', methods=['PUT'])
@login_required
def update_resource(resource_id):
    try:
        resource = Resource.query.get(resource_id)
        
        if not resource:
            return jsonify({'success': False, 'message': 'Resource not found'}), 404
        
        if resource.owner_id != session['user_id']:
            return jsonify({'success': False, 'message': 'Unauthorized'}), 403
        
        data = request.json
        
        if 'is_available' in data:
            resource.is_available = data['is_available']
        if 'price' in data:
            resource.price = data['price']
        if 'description' in data:
            resource.description = data['description']
        
        db.session.commit()
        
        return jsonify({'success': True, 'message': 'Resource updated successfully'})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500

@application.route('/api/resources/<int:resource_id>', methods=['DELETE'])
@login_required
def delete_resource(resource_id):
    try:
        resource = Resource.query.get(resource_id)
        
        if not resource:
            return jsonify({'success': False, 'message': 'Resource not found'}), 404
        
        if resource.owner_id != session['user_id']:
            return jsonify({'success': False, 'message': 'Unauthorized'}), 403
        
        db.session.delete(resource)
        db.session.commit()
        
        return jsonify({'success': True, 'message': 'Resource deleted successfully'})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500

@application.route('/api/user/profile', methods=['GET'])
@login_required
def get_profile():
    try:
        user = User.query.get(session['user_id'])
        
        return jsonify({
            'success': True,
            'data': {
                'id': user.id,
                'name': user.name,
                'email': user.email,
                'phone': user.phone,
                'location': user.location,
                'language_preference': user.language_preference,
                'created_at': user.created_at.isoformat()
            }
        })
        
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@application.route('/api/user/profile', methods=['PUT'])
@login_required
def update_profile():
    try:
        user = User.query.get(session['user_id'])
        data = request.json
        
        if 'name' in data:
            user.name = data['name']
        if 'phone' in data:
            user.phone = data['phone']
        if 'location' in data:
            user.location = data['location']
        if 'language_preference' in data:
            user.language_preference = data['language_preference']
        
        db.session.commit()
        
        return jsonify({'success': True, 'message': 'Profile updated successfully'})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500


app = application  # Vercel entry point

if __name__ == '__main__':
    # The following block is for local development and should not be run in production.
    # In a production environment like Elastic Beanstalk, a WSGI server like Gunicorn is used.
    # with application.app_context():
    #     db.create_all()
    application.run(debug=True, host='0.0.0.0', port=int(os.getenv('PORT', 3000)))
