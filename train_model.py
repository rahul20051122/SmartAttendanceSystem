import os
import cv2
import numpy as np

def train_recognizer():
    """
    Scans the dataset folder, converts all student images to grayscale,
    trains the LBPH Face Recognizer, and saves the trained model as trainer.yml.
    
    Returns:
        tuple: (True, success_message) on success, or (False, error_message) on failure.
    """
    # Initialize the LBPH Face Recognizer
    try:
        recognizer = cv2.face.LBPHFaceRecognizer_create()
    except AttributeError:
        return False, "LBPH Face Recognizer is not available. Please install 'opencv-contrib-python' via pip."

    face_samples = []
    labels = []

    # Get the project root directory path
    base_dir = os.path.dirname(os.path.abspath(__file__))
    dataset_path = os.path.join(base_dir, "dataset")

    # Check if dataset directory exists
    if not os.path.exists(dataset_path):
        return False, "Dataset directory 'dataset' not found. Please register students and capture faces first."

    # Read directories in the dataset folder
    try:
        student_folders = os.listdir(dataset_path)
    except Exception as e:
        return False, f"Failed to list dataset directory: {str(e)}"

    for folder_name in student_folders:
        folder_path = os.path.join(dataset_path, folder_name)
        
        # We only process directories
        if not os.path.isdir(folder_path):
            continue
            
        # The folder name is the student's ID (integer label)
        try:
            student_id = int(folder_name)
        except ValueError:
            # Skip folders that are not numeric
            continue

        # Get all image files inside the student's folder
        try:
            image_names = os.listdir(folder_path)
        except Exception as e:
            continue

        for image_name in image_names:
            # Filter only image files
            if not image_name.lower().endswith(('.jpg', '.jpeg', '.png')):
                continue

            image_path = os.path.join(folder_path, image_name)
            
            # Read the image in grayscale mode directly
            gray_image = cv2.imread(image_path, cv2.IMREAD_GRAYSCALE)
            
            if gray_image is None:
                continue
            
            # Append training data
            face_samples.append(gray_image)
            labels.append(student_id)

    # Check if we found any face samples for training
    if len(face_samples) == 0:
        return False, "No valid training images found in the dataset directory. Make sure you have captured faces first."

    # Train the recognizer model
    try:
        # Train LBPH face recognizer with face samples and corresponding student ID labels
        recognizer.train(face_samples, np.array(labels, dtype=np.int32))
        
        # Save the trained model to trainer.yml in the root folder
        model_save_path = os.path.join(base_dir, "trainer.yml")
        recognizer.write(model_save_path)
        
        unique_students_trained = len(set(labels))
        return True, f"Successfully trained model with {len(face_samples)} face images from {unique_students_trained} student(s)! Saved to 'trainer.yml'."
        
    except Exception as e:
        return False, f"Error occurred during training: {str(e)}"

if __name__ == "__main__":
    print("Starting Face Recognition Training...")
    success, message = train_recognizer()
    print("--------------------------------------------------")
    if success:
        print(f"SUCCESS: {message}")
    else:
        print(f"FAILED: {message}")
    print("--------------------------------------------------")
