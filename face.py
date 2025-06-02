from flask import Flask, render_template, Response, request, jsonify
import cv2
import datetime
import numpy as np

app = Flask(__name__)

camera = cv2.VideoCapture(0)
face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
scan_logs = []
scan_line_y = 0
scan_direction = 1  # 1 for moving down, -1 for moving up

def generate_frames():
    global scan_line_y, scan_direction
    while True:
        success, frame = camera.read()
        if not success:
            break
        else:
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            faces = face_cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(100, 100))

            for (x, y, w, h) in faces:
                cv2.rectangle(frame, (x, y), (x + w, y + h), (255, 0, 0), 2)  # Blue face rectangle

                # Scanning line effect
                scan_line_y += scan_direction * 5
                if scan_line_y > h or scan_line_y < 0:
                    scan_direction *= -1  # Reverse direction

                scan_line_position = y + scan_line_y
                cv2.line(frame, (x, scan_line_position), (x + w, scan_line_position), (0, 255, 0), 2)

            _, buffer = cv2.imencode('.jpg', frame)
            frame = buffer.tobytes()
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')

@app.route("/")
def home():
    return render_template("index.html", scan_logs=scan_logs)

@app.route("/video_feed")
def video_feed():
    return Response(generate_frames(), mimetype="multipart/x-mixed-replace; boundary=frame")

@app.route("/start-scan", methods=["POST"])
def start_scan():
    data = request.json
    if data and data.get("action") == "scan":
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        scan_logs.append(f"Face scanned at {timestamp}")
        return jsonify({"success": True, "message": "Face scan started"})
    return jsonify({"success": False, "message": "Invalid request"})

@app.route('/feedback')
def feedback():
    return render_template('feedback.html')

if __name__ == "__main__":
    app.run(debug=True)