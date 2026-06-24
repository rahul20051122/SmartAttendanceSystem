import os
import cv2
import sqlite3
import numpy as np
import time
import threading

# Import the mark_attendance method from the project database manager
from attendance_manager import mark_attendance

# ----------------- Face Recognition Configuration -----------------
# LBPH recognizer predict confidence score (distance) threshold.
# Values below this threshold are recognized as registered students.
# Values equal or above this threshold are classified as "Unknown Person".
# A recommended default value is 65. Lower value is stricter.
RECOGNITION_THRESHOLD = 65

# ----------------- OpenCV-Only Liveness Tracking Configuration -----------------
# Face center displacement threshold in pixels to confirm head movement/liveness
# Time allowed (in seconds) to perform movement before liveness fails
# Duration (in seconds) of user inactivity before resetting their liveness state
MOVEMENT_THRESHOLD = 15
LIVENESS_TIMEOUT = 5.0
SESSION_TIMEOUT = 5.0

# Global dictionary to track student session states across real-time video frames
# Structure:
# student_id: {
#     'liveness_confirmed': bool,
#     'liveness_failed': bool,
#     'attendance_marked': bool,
#     'start_time': float,
#     'last_seen': float,
#     'centers': list of (cx, cy)
# }
session_states = {}

# Global camera access locks
camera_lock = threading.Lock()
camera_busy = False


def get_student_name(student_id):
    """
    Connects to the SQLite database (attendance.db) and queries
    the 'Students' table to fetch the name of the student corresponding
    to the given integer student_id.
    
    Parameters:
        student_id (int): The unique database ID of the student.
        
    Returns:
        str: The name of the student, or None if not found/error occurs.
    """
    # Build absolute path to database relative to the script location
    base_dir = os.path.dirname(os.path.abspath(__file__))
    db_path = os.path.join(base_dir, "attendance.db")
    
    # Establish connection to SQLite database
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    try:
        # Retrieve the student's name corresponding to their ID
        cursor.execute("SELECT name FROM Students WHERE id = ?", (student_id,))
        row = cursor.fetchone()
        if row:
            return row[0] # Return the name string from the query result
        return None
    except sqlite3.Error as e:
        print(f"Database Query Error: {str(e)}")
        return None
    finally:
        # Always close connection to prevent locking the database
        conn.close()

def open_webcam(purpose="Recognition"):
    """
    Attempts to open camera index 0 under the global camera lock.
    Uses DirectShow (cv2.CAP_DSHOW) first on Windows, then falls back to default.
    Returns:
        tuple: (video_capture_object, index_used) or (None, -1)
    """
    global camera_busy
    
    print(f"[Camera Manager] [{purpose}] Requesting camera access...")
    with camera_lock:
        if camera_busy:
            print(f"[Camera Manager] [{purpose}] Access denied: Camera is busy.")
            return None, -1
        camera_busy = True
        
    print(f"[Camera Manager] [{purpose}] Camera busy lock acquired.")
    print(f"[Camera Manager] [{purpose}] Capture started.")
    
    index = 0
    
    # 1. Try DirectShow backend (CAP_DSHOW) on Windows first
    try:
        print(f"[Camera Manager] [{purpose}] Attempting index {index} via DSHOW...")
        cap = cv2.VideoCapture(index, cv2.CAP_DSHOW)
        if cap.isOpened():
            print(f"[Camera Manager] [{purpose}] Camera opened successfully.")
            return cap, index
        else:
            if cap is not None:
                cap.release()
    except Exception as e:
        print(f"[Camera Manager] [{purpose}] DSHOW exception on index {index}: {str(e)}")
        
    # 2. Try default backend fallback
    try:
        print(f"[Camera Manager] [{purpose}] Attempting index {index} via Default...")
        cap = cv2.VideoCapture(index)
        if cap.isOpened():
            print(f"[Camera Manager] [{purpose}] Camera opened successfully.")
            return cap, index
        else:
            if cap is not None:
                cap.release()
    except Exception as e:
        print(f"[Camera Manager] [{purpose}] Default exception on index {index}: {str(e)}")

    print(f"[Camera Manager] [{purpose}] CRITICAL ERROR: Camera index {index} is unavailable.")
    with camera_lock:
        camera_busy = False
    return None, -1

def close_webcam(cap, purpose="Recognition"):
    """
    Releases the VideoCapture object, closes windows, and releases the camera busy lock.
    """
    global camera_busy
    print(f"[Camera Manager] [{purpose}] Closing camera...")
    if cap is not None:
        try:
            cap.release()
            print(f"[Camera Manager] [{purpose}] Camera released.")
        except Exception as e:
            print(f"[Camera Manager] [{purpose}] Error releasing camera: {str(e)}")
            
    try:
        cv2.destroyAllWindows()
    except Exception as e:
        print(f"[Camera Manager] [{purpose}] Error destroying windows: {str(e)}")
        
    with camera_lock:
        camera_busy = False
    print(f"[Camera Manager] [{purpose}] Capture finished. Camera busy lock released.")


def recognize_faces():
    """
    Loads the trained LBPH Face Recognizer model, activates the default webcam,
    detects faces in real time, identifies recognized students, marks their attendance,
    and labels unknown faces. Press the 'ESC' key to close the webcam window.
    """
    # Get the project root folder
    base_dir = os.path.dirname(os.path.abspath(__file__))
    
    # Load the Haar Cascade classifier for frontal face detection
    cascade_path = cv2.data.haarcascades + 'haarcascade_frontalface_default.xml'
    face_classifier = cv2.CascadeClassifier(cascade_path)
    
    if face_classifier.empty():
        print("Error: Could not load the Haar Cascade face detector XML.")
        return

    # Create the LBPH recognizer instance and read the trained weights
    try:
        recognizer = cv2.face.LBPHFaceRecognizer_create()
    except AttributeError:
        print("Error: LBPH Face Recognizer module is not available in your OpenCV installation.")
        print("Please run: pip install opencv-contrib-python")
        return

    # Look for model in trainer/trainer.yml, fallback to project root trainer.yml
    model_path = os.path.join(base_dir, "trainer", "trainer.yml")
    if not os.path.exists(model_path):
        model_path = os.path.join(base_dir, "trainer.yml")

    # If the trainer file doesn't exist anywhere, stop execution
    if not os.path.exists(model_path):
        print(f"Error: Trained model file not found at '{model_path}'.")
        print("Please train your model using train_model.py first.")
        return

    try:
        recognizer.read(model_path)
        print(f"Successfully loaded trained model: {model_path}")
    except Exception as e:
        print(f"Error loading trained model: {str(e)}")
        return

    video_capture = None
    try:
        # Access the default webcam using the robust open_webcam helper
        video_capture, index = open_webcam("Recognition")
        if video_capture is None or index == -1:
            print("[Recognition] Camera is busy or unavailable. Exiting.")
            return

        print("--------------------------------------------------")
        print("Face recognition started. Press 'ESC' key to close.")
        print("--------------------------------------------------")

        while True:
            # Clean up old session states that have expired (timeout > SESSION_TIMEOUT seconds)
            current_time = time.time()
            expired_ids = [sid for sid, state in list(session_states.items()) if current_time - state['last_seen'] > SESSION_TIMEOUT]
            for sid in expired_ids:
                del session_states[sid]

            # Read a frame from the webcam feed
            ret, frame = video_capture.read()
            print(f"[Camera Debug] Recognition index {index} - Frame read status: {ret}")
            if not ret:
                print("Failed to read frame from webcam.")
                break

            # Convert current BGR frame to Grayscale (required for LBPH and landmark alignment)
            gray_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

            # Detect all faces in the frame
            faces = face_classifier.detectMultiScale(
                gray_frame,
                scaleFactor=1.2,
                minNeighbors=5,
                minSize=(100, 100)
            )

            for (x, y, w, h) in faces:
                # Crop detected face region from grayscale frame
                face_roi = gray_frame[y:y+h, x:x+w]
                
                # Predict identity
                student_id, confidence = recognizer.predict(face_roi)

                # Map the LBPH distance score to a visual confidence percentage
                match_percentage = max(0, min(100, round(100 - confidence)))
                confidence_text = f"Confidence: {match_percentage}%"

                # Match threshold check
                if confidence < RECOGNITION_THRESHOLD:
                    student_name = get_student_name(student_id)
                    if not student_name:
                        student_name = "Unknown ID"
                    
                    if student_id not in session_states:
                        session_states[student_id] = {
                            'liveness_confirmed': False,
                            'liveness_failed': False,
                            'attendance_marked': False,
                            'start_time': current_time,
                            'last_seen': current_time,
                            'centers': []
                        }
                    
                    state = session_states[student_id]
                    state['last_seen'] = current_time
                    
                    if state['liveness_failed']:
                        box_color = (0, 0, 255)
                        label_text = f"Name: {student_name}"
                        status_text = "Liveness Check Failed"
                    elif not state['liveness_confirmed']:
                        box_color = (0, 215, 230)
                        label_text = f"Name: {student_name}"
                        status_text = "Please Move Head"

                        cx = x + w // 2
                        cy = y + h // 2
                        state['centers'].append((cx, cy))

                        if len(state['centers']) > 30:
                            state['centers'].pop(0)

                        xs = [c[0] for c in state['centers']]
                        dx = max(xs) - min(xs) if xs else 0

                        if dx >= MOVEMENT_THRESHOLD:
                            state['liveness_confirmed'] = True
                            print(f"[Liveness Verified] Head movement detected (dx={dx}px) for student: {student_name}")
                        elif (current_time - state['start_time']) > LIVENESS_TIMEOUT:
                            state['liveness_failed'] = True
                            print(f"[Liveness Failed] No head movement detected within {LIVENESS_TIMEOUT} seconds for student: {student_name}")
                    else:
                        if not state['attendance_marked']:
                            success, db_status = mark_attendance(student_id)
                            state['attendance_marked'] = True
                            status_text = "Liveness Confirmed"
                            print(f"[Attendance marked] {student_name}: {db_status}")
                        else:
                            status_text = "Attendance Marked"
                        
                        label_text = f"Name: {student_name}"
                        box_color = (0, 255, 0)
                else:
                    label_text = "Unknown Person"
                    status_text = "Not Registered Student"
                    box_color = (0, 0, 255)

                cv2.rectangle(frame, (x, y), (x+w, y+h), box_color, 2)
                cv2.putText(frame, label_text, (x, y - 25), cv2.FONT_HERSHEY_SIMPLEX, 0.75, box_color, 2)
                cv2.putText(frame, confidence_text, (x, y - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.6, box_color, 1)
                cv2.putText(frame, status_text, (x, y + h + 20), cv2.FONT_HERSHEY_SIMPLEX, 0.6, box_color, 1)

            cv2.imshow("Face Recognition - Smart Attendance System", frame)

            key = cv2.waitKey(1) & 0xFF
            if key == 27:
                break
    finally:
        if video_capture is not None:
            close_webcam(video_capture, "Recognition")

def generate_recognition_frames():
    """
    Generator function that captures frames from the webcam, performs real-time
    face recognition, overlays labels/boxes, encodes the frames as JPEG,
    and yields the multipart/x-mixed-replace byte chunks.
    """
    import cv2
    import os
    
    base_dir = os.path.dirname(os.path.abspath(__file__))
    
    # Load Haar Cascade
    cascade_path = cv2.data.haarcascades + 'haarcascade_frontalface_default.xml'
    face_classifier = cv2.CascadeClassifier(cascade_path)
    if face_classifier.empty():
        print("Error: Could not load the Haar Cascade face detector XML.")
        return

    # Load LBPH recognizer
    try:
        recognizer = cv2.face.LBPHFaceRecognizer_create()
    except AttributeError:
        print("Error: LBPH Face Recognizer module is not available.")
        return

    model_path = os.path.join(base_dir, "trainer", "trainer.yml")
    if not os.path.exists(model_path):
        model_path = os.path.join(base_dir, "trainer.yml")

    model_loaded = False
    if os.path.exists(model_path):
        try:
            recognizer.read(model_path)
            model_loaded = True
        except Exception as e:
            print(f"Error loading trained model: {str(e)}")

    video_capture = None
    try:
        video_capture, index = open_webcam("Recognition Stream")
        if video_capture is None or index == -1:
            placeholder = np.zeros((480, 640, 3), dtype=np.uint8)
            cv2.putText(
                placeholder,
                "Camera is busy / in use by another function",
                (40, 240),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.7,
                (0, 0, 255),
                2
            )
            ret, buffer = cv2.imencode('.jpg', placeholder)
            if ret:
                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n\r\n' + buffer.tobytes() + b'\r\n')
            return

        while True:
            # Clean up old session states that have expired (timeout > SESSION_TIMEOUT seconds)
            current_time = time.time()
            expired_ids = [sid for sid, state in list(session_states.items()) if current_time - state['last_seen'] > SESSION_TIMEOUT]
            for sid in expired_ids:
                del session_states[sid]

            ret, frame = video_capture.read()
            print(f"[Camera Debug] Kiosk Stream index {index} - Frame read status: {ret}")
            if not ret:
                break

            # Convert BGR frame to Grayscale (required for landmarks and LBPH)
            gray_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

            # Detect faces
            faces = face_classifier.detectMultiScale(
                gray_frame,
                scaleFactor=1.2,
                minNeighbors=5,
                minSize=(100, 100)
            )

            for (x, y, w, h) in faces:
                face_roi = gray_frame[y:y+h, x:x+w]
                
                if model_loaded:
                    student_id, confidence = recognizer.predict(face_roi)
                    
                    # Map the LBPH distance score to a visual confidence percentage
                    match_percentage = max(0, min(100, round(100 - confidence)))
                    confidence_text = f"Confidence: {match_percentage}%"
                    
                    if confidence < RECOGNITION_THRESHOLD:
                        student_name = get_student_name(student_id)
                        if not student_name:
                            student_name = "Unknown ID"
                        
                        # Initialize session state tracking
                        if student_id not in session_states:
                            session_states[student_id] = {
                                'liveness_confirmed': False,
                                'liveness_failed': False,
                                'attendance_marked': False,
                                'start_time': current_time,
                                'last_seen': current_time,
                                'centers': []
                            }
                        
                        state = session_states[student_id]
                        state['last_seen'] = current_time # Update activity timestamp to keep session active
                        
                        # Check liveness status
                        if state['liveness_failed']:
                            box_color = (0, 0, 255) # Red box
                            label_text = f"Name: {student_name}"
                            status_text = "Liveness Check Failed"
                        elif not state['liveness_confirmed']:
                            # Bounding box is yellow/cyan while verification is in progress
                            box_color = (0, 215, 230)
                            label_text = f"Name: {student_name}"
                            status_text = "Please Move Head"
                            
                            # Track movement
                            cx = x + w // 2
                            cy = y + h // 2
                            state['centers'].append((cx, cy))
                            if len(state['centers']) > 30:
                                state['centers'].pop(0)
                                
                            xs = [c[0] for c in state['centers']]
                            dx = max(xs) - min(xs) if xs else 0
                            
                            if dx >= MOVEMENT_THRESHOLD:
                                state['liveness_confirmed'] = True
                                print(f"[Liveness Verified] Head movement detected (dx={dx}px) for student: {student_name}")
                            elif (current_time - state['start_time']) > LIVENESS_TIMEOUT:
                                state['liveness_failed'] = True
                                print(f"[Liveness Failed] No head movement detected within {LIVENESS_TIMEOUT} seconds for student: {student_name}")
                        else:
                            # Liveness confirmed!
                            if not state['attendance_marked']:
                                success, db_status = mark_attendance(student_id)
                                state['attendance_marked'] = True
                                status_text = "Liveness Confirmed"
                            else:
                                status_text = "Attendance Marked"
                            
                            label_text = f"Name: {student_name}"
                            box_color = (0, 255, 0) # Green box after confirmation
                    else:
                        label_text = "Unknown Person"
                        status_text = "Not Registered Student"
                        box_color = (0, 0, 255) # Red box for unrecognized face
                else:
                    label_text = "Model Not Trained"
                    confidence_text = "No trainer.yml"
                    status_text = "Please train model first"
                    box_color = (0, 0, 255)

                # Draw bounding box
                cv2.rectangle(frame, (x, y), (x+w, y+h), box_color, 2)

                # Display student details above box
                cv2.putText(frame, label_text, (x, y - 25), cv2.FONT_HERSHEY_SIMPLEX, 0.75, box_color, 2)
                cv2.putText(frame, confidence_text, (x, y - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.6, box_color, 1)
                cv2.putText(frame, status_text, (x, y + h + 20), cv2.FONT_HERSHEY_SIMPLEX, 0.6, box_color, 1)

            # Encode as JPEG
            ret, buffer = cv2.imencode('.jpg', frame)
            if not ret:
                continue
            
            frame_bytes = buffer.tobytes()
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
    finally:
        if video_capture is not None:
            close_webcam(video_capture, "Recognition Stream")

def generate_diagnostic_frames():
    """
    Generator function for raw webcam diagnostic streaming.
    Tests camera indexes, overlays status info, logs frame reads/releases,
    and returns bytes stream for the Flask frontend.
    """
    cap = None
    try:
        cap, index = open_webcam("Diagnostic Stream")
        if cap is None or index == -1:
            placeholder = np.zeros((480, 640, 3), dtype=np.uint8)
            cv2.putText(
                placeholder,
                "Camera is busy / in use by another function",
                (40, 240),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.7,
                (0, 0, 255),
                2
            )
            ret, buffer = cv2.imencode('.jpg', placeholder)
            if ret:
                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n\r\n' + buffer.tobytes() + b'\r\n')
            return
            
        while True:
            ret, frame = cap.read()
            print(f"[Camera Debug] Diagnostic Stream index {index} - Frame read status: {ret}")
            if not ret:
                break
                
            # Add diagnostics overlay directly on the raw feed
            cv2.putText(
                frame,
                f"Camera Index: {index} | Status: Online",
                (20, 40),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.7,
                (0, 255, 0),
                2
            )
            
            # Encode frame to jpeg
            ret, buffer = cv2.imencode('.jpg', frame)
            if not ret:
                continue
                
            frame_bytes = buffer.tobytes()
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
    finally:
        if cap is not None:
            close_webcam(cap, "Diagnostic Stream")

# Execute face recognition if run directly as a standalone script
if __name__ == "__main__":
    recognize_faces()
