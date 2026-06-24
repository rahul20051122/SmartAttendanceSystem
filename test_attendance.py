# Import the required function modules from attendance_manager
from attendance_manager import create_attendance_table, mark_attendance
from database import init_db, insert_student, get_db_connection

if __name__ == "__main__":
    print("--- Smart Attendance System: Testing Attendance Manager ---")
    
    # 1. Initialize the database and check tables
    print("Step 1: Checking and initializing the database table...")
    init_db()
    create_attendance_table()
    
    # 2. Insert a dummy student for testing validation
    print("\nRegistering a test student...")
    test_roll = "TEST-ROLL-001"
    test_name = "Test Student"
    test_email = "test@example.com"
    test_dept = "CSE"
    
    # Clean up student if they exist from previous failed runs
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM Students WHERE roll_number = ?", (test_roll,))
    existing = cursor.fetchone()
    if existing:
        student_id = existing['id']
        cursor.execute("DELETE FROM attendance WHERE student_id = ?", (student_id,))
        cursor.execute("DELETE FROM absent_emails_sent WHERE student_id = ?", (student_id,))
        cursor.execute("DELETE FROM Students WHERE id = ?", (student_id,))
        conn.commit()
        
    # Insert new student
    insert_student(test_name, test_roll, test_dept, test_email)
    
    # Get the ID of the inserted student
    cursor.execute("SELECT id FROM Students WHERE roll_number = ?", (test_roll,))
    student_id = cursor.fetchone()['id']
    conn.close()
    
    print(f"Test Student registered with ID: {student_id}")
    
    # 3. Attempt to mark attendance for the registered student
    print(f"\nStep 2: Attempting to mark attendance for Student ID: {student_id}...")
    success, message = mark_attendance(student_id)
    
    # 4. Print the success status and return message from the manager
    print("--------------------------------------------------")
    print(f"Success Status: {success}")
    print(f"Message:        {message}")
    print("--------------------------------------------------")
    
    # 5. Attempt to mark it a second time to test the duplicate prevention check
    print(f"\nStep 3: Attempting to mark duplicate attendance for Student ID: {student_id}...")
    success_duplicate, message_duplicate = mark_attendance(student_id)
    
    print("--------------------------------------------------")
    print(f"Success Status (Duplicate Test): {success_duplicate}")
    print(f"Message (Duplicate Test):        {message_duplicate}")
    print("--------------------------------------------------")
    
    # 6. Clean up test data
    print("\nStep 4: Cleaning up test data...")
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM attendance WHERE student_id = ?", (student_id,))
    cursor.execute("DELETE FROM absent_emails_sent WHERE student_id = ?", (student_id,))
    cursor.execute("DELETE FROM Students WHERE id = ?", (student_id,))
    conn.commit()
    conn.close()
    print("Cleanup completed.")
