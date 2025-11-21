import os
import sys
import boto3
import firebase_admin
from firebase_admin import credentials, auth
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

print("="*50)
print("SYSTEM CONNECTION TEST")
print("="*50)

# Load environment variables
load_dotenv()

def test_database_connection():
    print("\n🔍 Testing Database Connection...")
    try:
        db_url = os.getenv('DATABASE_URL')
        if not db_url:
            print("❌ DATABASE_URL not found in .env file")
            return False
            
        engine = create_engine(db_url)
        with engine.connect() as conn:
            result = conn.execute(text("SELECT 1"))
            if result.scalar() == 1:
                print("✅ Database connection successful")
                return True
    except Exception as e:
        print(f"❌ Database connection failed: {str(e)}")
        return False

def test_s3_connection():
    print("\n🔍 Testing S3 Connection...")
    try:
        s3 = boto3.client(
            's3',
            aws_access_key_id=os.getenv('AWS_ACCESS_KEY_ID'),
            aws_secret_access_key=os.getenv('AWS_SECRET_ACCESS_KEY'),
            region_name=os.getenv('AWS_REGION')
        )
        # Try to list buckets as a connection test
        s3.list_buckets()
        print("✅ S3 connection successful")
        
        # Test bucket access
        bucket = os.getenv('S3_BUCKET')
        if bucket:
            try:
                s3.head_bucket(Bucket=bucket)
                print(f"✅ Access to S3 bucket '{bucket}' successful")
                return True
            except Exception as e:
                print(f"❌ Cannot access S3 bucket '{bucket}': {str(e)}")
                return False
        else:
            print("⚠️ S3_BUCKET not set in .env")
            return False
    except Exception as e:
        print(f"❌ S3 connection failed: {str(e)}")
        return False

def test_firebase_connection():
    print("\n🔍 Testing Firebase Connection...")
    try:
        # Check if Firebase is already initialized
        try:
            firebase_admin.get_app()
            print("✅ Firebase already initialized")
            return True
        except ValueError:
            # Initialize with service account
            cred_path = 'serviceAccountKey.json'
            if os.path.exists(cred_path):
                cred = credentials.Certificate(cred_path)
                firebase_admin.initialize_app(cred)
                print("✅ Firebase initialization successful")
                return True
            else:
                print("❌ Firebase service account file not found")
                return False
    except Exception as e:
        print(f"❌ Firebase connection failed: {str(e)}")
        return False

def test_weather_api():
    print("\n🔍 Testing Weather API...")
    api_key = os.getenv('OPENWEATHER_API_KEY')
    if not api_key:
        print("⚠️ OPENWEATHER_API_KEY not set in .env")
        return False
    
    try:
        import requests
        # Test with a known location (London)
        response = requests.get(
            f"https://api.openweathermap.org/data/2.5/weather?q=London&appid={api_key}&units=metric"
        )
        if response.status_code == 200:
            print("✅ Weather API connection successful")
            return True
        else:
            print(f"❌ Weather API returned status code: {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ Weather API connection failed: {str(e)}")
        return False

if __name__ == "__main__":
    # Test all connections
    db_ok = test_database_connection()
    s3_ok = test_s3_connection()
    firebase_ok = test_firebase_connection()
    weather_ok = test_weather_api()
    
    # Print summary
    print("\n" + "="*50)
    print("CONNECTION TEST SUMMARY")
    print("="*50)
    print(f"Database: {'✅' if db_ok else '❌'}")
    print(f"AWS S3: {'✅' if s3_ok else '❌'}")
    print(f"Firebase: {'✅' if firebase_ok else '❌'}")
    print(f"Weather API: {'✅' if weather_ok else '❌'}")
    print("="*50)
    
    if all([db_ok, s3_ok, firebase_ok, weather_ok]):
        print("\n🎉 All systems are working correctly!")
    else:
        print("\n⚠️ Some systems are not working. Please check the error messages above.")
