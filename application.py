from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from flask_cors import CORS
from dotenv import load_dotenv
import os
import requests
from datetime import datetime, timedelta
import json
from functools import wraps
from database import db, init_db, User, Resource, Transaction
from urllib.parse import quote_plus
import boto3
from werkzeug.utils import secure_filename
import uuid

# Load environment variables
load_dotenv()

application = Flask(__name__)
application.config['SECRET_KEY'] = os.getenv('SECRET_KEY')
db_url = os.getenv('DATABASE_URL')
if not db_url:
    db_user = os.getenv('DB_USER')
    db_password = os.getenv('DB_PASS') or os.getenv('DB_PASSWORD')
    db_host = os.getenv('DB_HOST')
    db_name = os.getenv('DB_NAME')
    db_port = os.getenv('DB_PORT', '3306')
    if all([db_user, db_password, db_host, db_name]):
        safe_password = quote_plus(db_password)
        db_url = f"mysql+pymysql://{db_user}:{safe_password}@{db_host}:{db_port}/{db_name}"
if not db_url:
    raise ValueError("DATABASE_URL environment variable is not set. Please provide a valid MySQL connection string.")
application.config['SQLALCHEMY_DATABASE_URI'] = db_url
application.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
application.config['UPLOAD_FOLDER'] = 'static/uploads'
application.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size

CORS(application)

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
    except Exception as e:
        print(f"S3 initialization failed: {e}")

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
        if 'user_id' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

# Create upload folder if it doesn't exist
os.makedirs(application.config['UPLOAD_FOLDER'], exist_ok=True)

@application.route('/')
def index():
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))

@application.route('/login')
def login():
    return render_template('login.html')

@application.route('/signup')
def signup():
    return render_template('signup.html')

@application.route('/dashboard')
@login_required
def dashboard():
    user = User.query.get(session['user_id'])
    return render_template('dashboard.html', user=user)

@application.route('/marketplace')
@login_required
def marketplace():
    return render_template('marketplace.html')

@application.route('/add-resource')
@login_required
def add_resource():
    return render_template('add_resource.html')

@application.route('/my-resources')
@login_required
def my_resources():
    return render_template('my_resources.html')

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
        
        # Check if user already exists
        existing_user = User.query.filter_by(email=data['email']).first()
        if existing_user:
            return jsonify({'success': False, 'message': 'User already exists'}), 400
        
        # Create new user
        user = User(
            firebase_uid=data.get('firebase_uid', str(uuid.uuid4())),
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
        
        # Find user by email or firebase_uid
        user = User.query.filter_by(email=data['email']).first()
        
        if not user:
            return jsonify({'success': False, 'message': 'User not found'}), 404
        
        session['user_id'] = user.id
        
        return jsonify({
            'success': True,
            'message': 'Login successful',
            'user': {
                'id': user.id,
                'name': user.name,
                'email': user.email,
                'location': user.location
            }
        })
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@application.route('/api/auth/logout', methods=['POST'])
def logout():
    session.pop('user_id', None)
    return jsonify({'success': True, 'message': 'Logged out successfully'})

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
            weather_data = {
                'temperature': data['main']['temp'],
                'feels_like': data['main']['feels_like'],
                'humidity': data['main']['humidity'],
                'description': data['weather'][0]['description'],
                'icon': data['weather'][0]['icon'],
                'wind_speed': data['wind']['speed'],
                'city': data['name'],
                'country': data['sys']['country'],
                'lat': data['coord']['lat'],
                'lon': data['coord']['lon']
            }
            print(f"✅ Weather data for: {weather_data['city']}, {weather_data['country']}")
            return jsonify({'success': True, 'data': weather_data})
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
                'image_url': resource.image_url,
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
                
                # Save to local storage first (always works)
                filepath = os.path.join(application.config['UPLOAD_FOLDER'], unique_filename)
                file.save(filepath)
                image_url = f"/static/uploads/{unique_filename}"
                print(f"✅ Image saved locally: {image_url}")
                
                # Optionally try to upload to S3 (if configured)
                if s3_client:
                    try:
                        with open(filepath, 'rb') as f:
                            s3_client.upload_fileobj(
                                f,
                                os.getenv('S3_BUCKET'),
                                unique_filename
                            )
                        s3_url = f"https://{os.getenv('S3_BUCKET')}.s3.{os.getenv('AWS_REGION')}.amazonaws.com/{unique_filename}"
                        image_url = s3_url  # Use S3 URL if upload successful
                        print(f"✅ Image also uploaded to S3: {s3_url}")
                    except Exception as e:
                        print(f"⚠️  S3 upload failed (using local): {e}")
            else:
                print(f"⚠️  No valid image file provided or invalid file type")
        
        # Create resource
        resource = Resource(
            owner_id=session['user_id'],
            name=request.form['name'],
            category=request.form['category'],
            description=request.form.get('description', ''),
            price=float(request.form['price']),
            listing_type=request.form['listing_type'],
            condition=request.form.get('condition', 'good'),
            age_years=int(request.form.get('age_years', 0)),
            quality=int(request.form.get('quality', 5)),
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
