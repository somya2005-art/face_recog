from flask import Flask, render_template, Response, request, jsonify, redirect, url_for, session, flash
import cv2
import datetime
import numpy as np
import base64
import time
import os
import re
import mysql.connector
from mysql.connector import Error
from dotenv import load_dotenv
import hashlib

# Load environment variables
load_dotenv()

# Initialize Flask app
app = Flask(__name__)
app.secret_key = 'your_secret_key_here'  # Change this to a secure secret key

# Configure upload folder for scan images
UPLOAD_FOLDER = 'static/images'
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

# Initialize camera
camera = cv2.VideoCapture(0)
camera.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
camera.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

# Load face detection model
face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")

# Global variables for scan functionality
scan_logs = []
scan_line_y = 0
scan_direction = 1
last_scan_time = 0
scan_cooldown = 3

# Database configuration
db_config = {
    'host': os.getenv('DB_HOST'),
    'database': os.getenv('DB_NAME'),
    'user': os.getenv('DB_USER'),
    'password': os.getenv('DB_PASSWORD'),
    'port': os.getenv('DB_PORT')
}

def get_db_connection():
    try:
        connection = mysql.connector.connect(**db_config)
        return connection
    except Error as e:
        print(f"Error connecting to MySQL: {e}")
        return None

def init_db():
    connection = get_db_connection()
    if connection:
        try:
            cursor = connection.cursor()
            
            # Create users table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    username VARCHAR(50) UNIQUE NOT NULL,
                    password VARCHAR(255) NOT NULL,
                    name VARCHAR(100) NOT NULL,
                    email VARCHAR(100) UNIQUE NOT NULL,
                    department VARCHAR(50) NOT NULL,
                    role VARCHAR(50) NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Create scan_logs table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS scan_logs (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    user_id INT NOT NULL,
                    scan_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    status VARCHAR(50) NOT NULL,
                    FOREIGN KEY (user_id) REFERENCES users(id)
                )
            """)
            
            connection.commit()
            print("Database tables created successfully")
        except Error as e:
            print(f"Error creating tables: {e}")
        finally:
            cursor.close()
            connection.close()

def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def verify_password(password, hashed):
    return hash_password(password) == hashed

def register_user(username, password, email):
    connection = get_db_connection()
    if connection:
        try:
            cursor = connection.cursor()
            
            # Check if username or email already exists
            cursor.execute("SELECT * FROM users WHERE username = %s OR email = %s", (username, email))
            if cursor.fetchone():
                return False, "Username or email already exists"
            
            # Insert new user with default values
            hashed_password = hash_password(password)
            cursor.execute("""
                INSERT INTO users (username, password, email, name, department, role)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (username, hashed_password, email, username, 'Default', 'User'))
            
            connection.commit()
            return True, "Registration successful"
        except Error as e:
            return False, f"Database error: {str(e)}"
        finally:
            cursor.close()
            connection.close()
    return False, "Database connection failed"

def authenticate_user(username, password):
    connection = get_db_connection()
    if connection:
        try:
            cursor = connection.cursor(dictionary=True)
            cursor.execute("SELECT * FROM users WHERE username = %s", (username,))
            user = cursor.fetchone()
            
            if user and verify_password(password, user['password']):
                return True, user
            return False, "Invalid username or password"
        except Error as e:
            return False, f"Database error: {str(e)}"
        finally:
            cursor.close()
            connection.close()
    return False, "Database connection failed"

def log_scan(user_id, status):
    connection = get_db_connection()
    if connection:
        try:
            cursor = connection.cursor()
            cursor.execute("""
                INSERT INTO scan_logs (user_id, status)
                VALUES (%s, %s)
            """, (user_id, status))
            connection.commit()
        except Error as e:
            print(f"Error logging scan: {e}")
        finally:
            cursor.close()
            connection.close()

# Initialize database tables
init_db()

def validate_email(email):
    """Validate email format."""
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return bool(re.match(pattern, email))

def validate_password(password):
    """Validate password strength."""
    if len(password) < 8:
        return False, "Password must be at least 8 characters long"
    if not re.search(r'[A-Z]', password):
        return False, "Password must contain at least one uppercase letter"
    if not re.search(r'[a-z]', password):
        return False, "Password must contain at least one lowercase letter"
    if not re.search(r'\d', password):
        return False, "Password must contain at least one number"
    return True, ""

def generate_frames():
    """Generate video frames with face detection."""
    global scan_line_y, scan_direction
    while True:
        success, frame = camera.read()
        if not success:
            break
        else:
            frame = cv2.flip(frame, 1)
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            
            faces = face_cascade.detectMultiScale(
                gray,
                scaleFactor=1.1,
                minNeighbors=3,
                minSize=(50, 50),
                flags=cv2.CASCADE_SCALE_IMAGE
            )

            for (x, y, w, h) in faces:
                cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 255, 0), 2)
                cv2.putText(frame, "Face Detected", (x, y-10), 
                           cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 255, 0), 2)

                scan_line_y += scan_direction * 5
                if scan_line_y > h or scan_line_y < 0:
                    scan_direction *= -1

                scan_line_position = y + scan_line_y
                cv2.line(frame, (x, scan_line_position), (x + w, scan_line_position), (0, 255, 0), 2)

            _, buffer = cv2.imencode('.jpg', frame)
            frame_bytes = buffer.tobytes()

            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')

@app.route("/")
def home():
    """Home route - always show login page first."""
    return render_template("login.html")

@app.route("/login", methods=['GET', 'POST'])
def login():
    """Handle user login."""
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        success, result = authenticate_user(username, password)
        if success:
            session['user_id'] = result['id']
            session['username'] = result['username']
            session['name'] = result['name']
            session['role'] = result['role']
            session['department'] = result['department']
            flash('Login successful!', 'success')
            return redirect(url_for('userinfo'))
        else:
            flash(result, 'error')
    
    return render_template("login.html")

@app.route("/userinfo")
def userinfo():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    connection = get_db_connection()
    if connection:
        try:
            cursor = connection.cursor(dictionary=True)
            cursor.execute("""
                SELECT * FROM users WHERE id = %s
            """, (session['user_id'],))
            user = cursor.fetchone()
            
            if user:
                return render_template('userinfo.html', user=user)
        except Error as e:
            flash(f"Database error: {str(e)}", 'error')
        finally:
            cursor.close()
            connection.close()
    
    return redirect(url_for('login'))

@app.route("/scan")
def scan():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    return render_template('scan.html')

@app.route("/video_feed")
def video_feed():
    """Stream video feed with face detection."""
    return Response(generate_frames(), mimetype="multipart/x-mixed-replace; boundary=frame")

@app.route("/start-scan", methods=["POST"])
def start_scan():
    """Handle face scanning process."""
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Please login first'})
    
    global last_scan_time
    current_time = time.time()
    
    if last_scan_time and (current_time - last_scan_time) < scan_cooldown:
        remaining_time = int(scan_cooldown - (current_time - last_scan_time))
        return jsonify({
            'success': False,
            'message': f'Please wait {remaining_time} seconds before scanning again'
        })
    
    try:
        # Get user information
        connection = get_db_connection()
        if not connection:
            return jsonify({'success': False, 'message': 'Database connection failed'})
        
        cursor = connection.cursor(dictionary=True)
        cursor.execute("SELECT name, email, department, role FROM users WHERE id = %s", (session['user_id'],))
        user_info = cursor.fetchone()
        cursor.close()
        connection.close()
        
        if not user_info:
            return jsonify({'success': False, 'message': 'User information not found'})
        
        ret, frame = camera.read()
        if not ret:
            return jsonify({'success': False, 'message': 'Failed to capture frame'})
        
        # Flip frame horizontally for mirror view
        frame = cv2.flip(frame, 1)
        
        # Convert to grayscale for face detection
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        
        # Detect faces with more lenient parameters
        faces = face_cascade.detectMultiScale(
            gray,
            scaleFactor=1.1,
            minNeighbors=3,
            minSize=(50, 50),
            flags=cv2.CASCADE_SCALE_IMAGE
        )
        
        if len(faces) == 0:
            return jsonify({'success': False, 'message': 'No face detected'})
        elif len(faces) > 1:
            return jsonify({'success': False, 'message': 'Multiple faces detected'})
        
        # Save the captured frame
        scan_filename = f'scan_{session["user_id"]}_{int(time.time())}.jpg'
        scan_image_path = os.path.join('static', 'images', scan_filename)
        cv2.imwrite(scan_image_path, frame)
        
        # Log the scan
        log_scan(session['user_id'], 'success')
        
        # Update session with scan information
        session['last_scan_time'] = current_time
        session['scan_image'] = scan_filename
        
        last_scan_time = current_time
        
        # Add scan time and image to user info
        user_info['scan_time'] = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        user_info['scan_image'] = scan_filename
        
        return jsonify({
            'success': True,
            'message': 'Face detected successfully',
            'user_info': user_info,
            'face_count': len(faces)
        })
        
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

@app.route("/logout")
def logout():
    """Handle user logout."""
    session.clear()
    flash('You have been logged out successfully.', 'success')
    return redirect(url_for('login'))

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        email = request.form['email']
        
        success, message = register_user(username, password, email)
        if success:
            flash(message, 'success')
            return redirect(url_for('login'))
        else:
            flash(message, 'error')
    
    return render_template('register.html')

@app.route('/feedback')
def feedback():
    return render_template('feedback.html')

if __name__ == "__main__":
    app.run(debug=True)
