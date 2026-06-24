import os
import cv2
import numpy as np
from face_recognition import open_webcam, close_webcam

# Dictionary to track capture progress for active student capture sessions
# Key: student_id (int), Value: count (int)
capture_progress_state = {}

def get_capture_progress(student_id):
    """Retrieves the current captured image count for a given student ID."""
    try:
        return capture_progress_state.get(int(student_id), 0)
    except (ValueError, TypeError):
        return 0

def generate_capture_frames(student_id):
    """
    Generator that captures video from the webcam, detects faces,
    crops and standardizes them, saves 50 samples into dataset/<student_id>/,
    and yields JPEG frame bytes for Flask streaming.
    """
    # 1. Initialize variables
    try:
        student_id = int(student_id)
    except ValueError:
        print("[Face Capture] Error: Invalid student ID format.")
        return

    capture_progress_state[student_id] = 0
    sample_count = 0
    max_samples = 50
    frame_count = 0

    # 2. Setup Haar Cascade face detector
    cascade_path = cv2.data.haarcascades + 'haarcascade_frontalface_default.xml'
    face_classifier = cv2.CascadeClassifier(cascade_path)
    if face_classifier.empty():
        print("[Face Capture] Error: Haar Cascade detector XML failed to load.")
        return

    # 3. Setup dataset directory
    base_dir = os.path.dirname(os.path.abspath(__file__))
    dataset_dir = os.path.join(base_dir, "dataset", str(student_id))
    try:
        os.makedirs(dataset_dir, exist_ok=True)
    except OSError as e:
        print(f"[Face Capture] Error creating dataset directory: {e}")
        return

    print(f"[Face Capture] Capture started for student ID: {student_id}")
    
    # 4. Open webcam
    video_capture = None
    try:
        video_capture, index = open_webcam("Face Capture Stream")
        if video_capture is None or index == -1:
            # Yield camera-busy placeholder frame
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

        # 5. Capture Loop
        while True:
            ret, frame = video_capture.read()
            if not ret:
                print("[Face Capture] Error: Failed to read frame from camera.")
                break

            frame_count += 1
            gray_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

            # Detect faces on every frame for visual tracking boxes
            faces = face_classifier.detectMultiScale(
                gray_frame, 
                scaleFactor=1.3, 
                minNeighbors=5, 
                minSize=(100, 100)
            )

            for (x, y, w, h) in faces:
                # Draw a tracking bounding box (Cyan)
                cv2.rectangle(frame, (x, y), (x+w, y+h), (0, 215, 230), 2)

                # Save face crop every 3rd frame to ensure dataset variety (head rotation/movement)
                if frame_count % 3 == 0 and sample_count < max_samples:
                    sample_count += 1
                    cropped_face = frame[y:y+h, x:x+w]
                    resized_face = cv2.resize(cropped_face, (200, 200))
                    image_filename = os.path.join(dataset_dir, f"image{sample_count}.jpg")
                    cv2.imwrite(image_filename, resized_face)
                    
                    # Update active session progress
                    capture_progress_state[student_id] = sample_count
                    print(f"[Face Capture] Saved sample {sample_count}/{max_samples} for Student ID: {student_id}")

                # Overlay current captured count on visual box (Green)
                cv2.putText(
                    frame,
                    f"Captured: {sample_count}/{max_samples}",
                    (x, y - 10),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.6,
                    (0, 255, 0),
                    2
                )
                break # Process only one face at a time

            # Overlay quit instructions on the web video stream
            cv2.putText(
                frame,
                "Position your face inside the screen and move slightly",
                (20, 40),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.6,
                (255, 255, 255),
                1
            )

            # Encode frame to JPEG
            ret, buffer = cv2.imencode('.jpg', frame)
            if not ret:
                continue

            frame_bytes = buffer.tobytes()
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')

            # Break loop when capture target of 50 samples is achieved
            if sample_count >= max_samples:
                print(f"[Face Capture] Capture finished for student ID: {student_id}")
                break

    finally:
        if video_capture is not None:
            close_webcam(video_capture, "Face Capture Stream")
