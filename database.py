from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import time
import os

db = SQLAlchemy()

def init_db(app):
    db.init_app(app)
    max_retries = 5
    retry_delay = 2  # seconds
    
    with app.app_context():
        # Test the database connection with retries
        for attempt in range(max_retries):
            try:
                with db.engine.connect() as connection:
                    # Test query to ensure connection is working
                    connection.execute(db.text("SELECT 1"))
                    print(f"\n✅ Database connection successful (attempt {attempt + 1}/{max_retries}).\n")
                    break
            except Exception as e:
                if attempt < max_retries - 1:
                    print(f"\n⚠️ Database connection attempt {attempt + 1}/{max_retries} failed.")
                    print(f"   Error: {str(e)}")
                    print(f"   Retrying in {retry_delay} seconds...")
                    time.sleep(retry_delay)
                    retry_delay *= 2  # Exponential backoff
                else:
                    print("\n" + "="*60)
                    print("❌ AWS RDS DATABASE CONNECTION FAILED!")
                    print(f"   Error: {str(e)}")
                    print("   Please check the following:")
                    print("     1. The `DATABASE_URL` in your .env file is correct.")
                    print("     2. The RDS instance is running and accessible.")
                    print("     3. The security groups for your RDS instance allow connections from your IP.")
                    print("     4. The database server is not at maximum connections.")
                    print("="*60 + "\n")
                    if app.config.get('TESTING') or os.environ.get('VERCEL'):
                        raise  # Re-raise in testing/production environments
                    else:
                        # In development, fall back to SQLite
                        print("\n⚠️ Falling back to SQLite database for development.\n")
                        app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///dev.db'
                        db.init_app(app)
                        with app.app_context():
                            db.create_all()
                        return
                    
        try:
            # Create tables with proper error handling
            db.create_all()
            print("✅ Database tables created/verified successfully")
        except Exception as e:
            print("❌ Failed to create/verify database tables")
            print(f"   Error: {str(e)}")
            if app.config.get('TESTING') or os.environ.get('VERCEL'):
                raise  # Re-raise in testing/production environments

class User(db.Model):
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    firebase_uid = db.Column(db.String(128), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    name = db.Column(db.String(100), nullable=False)
    phone = db.Column(db.String(20))
    location = db.Column(db.String(200))
    language_preference = db.Column(db.String(10), default='en')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    resources = db.relationship('Resource', backref='owner', lazy=True, cascade='all, delete-orphan')
    transactions = db.relationship('Transaction', backref='user', lazy=True)
    
    def __repr__(self):
        return f'<User {self.email}>'

class Resource(db.Model):
    __tablename__ = 'resources'
    
    id = db.Column(db.Integer, primary_key=True)
    owner_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    name = db.Column(db.String(200), nullable=False)
    category = db.Column(db.String(50), nullable=False)  # tools, livestock, electronics, fertilizers, etc.
    description = db.Column(db.Text)
    price = db.Column(db.Float, nullable=False)
    listing_type = db.Column(db.String(20), nullable=False)  # rent, borrow, sell
    condition = db.Column(db.String(20))  # new, good, fair, poor
    age_years = db.Column(db.Integer, default=0)
    quality = db.Column(db.Integer, default=5)  # 1-10 scale
    image_url = db.Column(db.String(500))
    location = db.Column(db.String(200))
    is_available = db.Column(db.Boolean, default=True)
    rating = db.Column(db.Float, default=0.0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    transactions = db.relationship('Transaction', backref='resource', lazy=True)
    
    def __repr__(self):
        return f'<Resource {self.name}>'

class Transaction(db.Model):
    __tablename__ = 'transactions'
    
    id = db.Column(db.Integer, primary_key=True)
    resource_id = db.Column(db.Integer, db.ForeignKey('resources.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    transaction_type = db.Column(db.String(20), nullable=False)  # rent, borrow, buy
    start_date = db.Column(db.DateTime, default=datetime.utcnow)
    end_date = db.Column(db.DateTime)
    status = db.Column(db.String(20), default='pending')  # pending, active, completed, cancelled
    amount = db.Column(db.Float)
    rating = db.Column(db.Integer)  # 1-5 stars
    review = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def __repr__(self):
        return f'<Transaction {self.id}>'
