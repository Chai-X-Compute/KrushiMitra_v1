# 🌾 KrushiMitra: Farmer Resource Pooling & Weather Information System

A comprehensive web-based platform designed to empower farmers by providing real-time weather updates, tool/resource sharing, and multi-language support.

## 🎯 Features

- **👨‍🌾 Farmer Authentication**: Secure login and signup using Firebase Authentication.
- **🌦 Real-Time Weather**: Location-based weather updates using the OpenWeatherMap API.
- **🧰 Resource Marketplace**: A platform for farmers to rent, borrow, or sell tools and resources.
- **🔍 Advanced Search**: Filter resources by category, listing type, and text search.
- **🌐 Multi-language Support**: Interface available in English, Hindi (हिंदी), and Marathi (मराठी).

## 🛠 Technology Stack

- **Backend**: Python, Flask, SQLAlchemy
- **Frontend**: HTML, CSS, JavaScript, Tailwind CSS
- **Database**: AWS RDS (MySQL)
- **Authentication**: Firebase Authentication
- **File Storage**: AWS S3
- **APIs**: OpenWeatherMap API

## 📋 Prerequisites

- Python 3.8+
- `pip` (Python package manager)
- A Firebase project.
- An OpenWeatherMap API key.
- An AWS account with an S3 bucket.

## 🚀 Installation & Setup

### 1. Clone the Repository

```bash
git clone <your-repository-url>
cd <repository-folder>
```

### 2. Configure Environment Variables

Create a file named `.env` in the project root by copying the example file:

```bash
# On Windows
copy .env.example .env

# On macOS/Linux
cp .env.example .env
```

Now, open the `.env` file and add your credentials for Firebase, OpenWeatherMap, and AWS.

### 3. Run the Setup Script

The easiest way to get started is to use the provided scripts. They will create a virtual environment, install dependencies, and start the application.

**On Windows:**

```bash
run.bat
```

**On macOS/Linux:**

```bash
chmod +x run.sh
./run.sh
```

The application will be available at `http://127.0.0.1:5000`.

### 4. Manual Setup

If you prefer to set up the project manually:

```bash
# 1. Create and activate a virtual environment
python -m venv venv
# Windows: venv\Scripts\activate
# macOS/Linux: source venv/bin/activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Run the application
python app.py
```

## ☁️ Cloud Integration (Optional)

For production environments, it is recommended to use AWS services for the database and file storage.

### 🗄️ Database (AWS RDS)

To connect to a production database like AWS RDS (MySQL or PostgreSQL), set the `DATABASE_URL` in your `.env` file. If this is not set, the application will default to a local SQLite database.


**Example for MySQL:**
```
DATABASE_URL="mysql+pymysql://USER:PASSWORD@HOST:PORT/DATABASE"
```

### 🖼️ File Storage (AWS S3)

For scalable file storage, you can configure the application to use an AWS S3 bucket. If you don't provide AWS credentials, images will be stored on the local server in the `static/uploads/` directory.

To enable S3, add the following to your `.env` file:

```
AWS_ACCESS_KEY_ID="YOUR_AWS_ACCESS_KEY_ID"
AWS_SECRET_ACCESS_KEY="YOUR_AWS_SECRET_ACCESS_KEY"
AWS_S3_BUCKET_NAME="YOUR_S3_BUCKET_NAME"
AWS_S3_REGION="YOUR_S3_BUCKET_REGION" # e.g., "us-east-1"
```

## 🗂 Project Structure

```
├── app.py              # Main Flask application with all backend logic
├── database.py         # Defines database models for users, resources, etc.
├── requirements.txt    # All Python dependencies for the project
├── .env.example        # Template for environment variables (API keys, DB connections)
├── run.bat             # Script to run the app on Windows
├── run.sh              # Script to run the app on macOS/Linux
├── templates/          # All HTML files, including:
│   ├── base.html       # Base template for all pages
│   ├── login.html      # User login page with Firebase integration
│   ├── signup.html     # User signup page with Firebase integration
│   ├── dashboard.html  # Main user dashboard
│   └── ...             # Other pages like marketplace, profile, etc.
└── static/             # All static files:
    ├── css/            # CSS files
    ├── js/             # JavaScript files
    └── images/         # Static images and icons
```

## 📄 License

This project is licensed under the MIT License.
