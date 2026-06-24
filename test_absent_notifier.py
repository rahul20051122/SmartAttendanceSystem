# test_absent_notifier.py
# Automated integration test script for the Automatic Absent Student Notifier.

import sys
import os
import sqlite3
from datetime import datetime

# Add root folder to sys.path if not present
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

import absent_notifier
from database import init_db

# Mocks for email sending to execute database and logic verification without SMTP dependencies
sent_emails_log = []

def mock_send_absent_email(student_name, student_email, date_str):
    """Mock implementation that records sent emails in-memory."""
    sent_emails_log.append({
        "name": student_name,
        "email": student_email,
        "date": date_str
    })
    print(f"[MOCK EMAIL] Alert sent to {student_name} <{student_email}> for date {date_str}.")
    return True

# Apply monkeypatching mock
absent_notifier.send_absent_email = mock_send_absent_email

def run_tests():
    print("==================================================")
    print("Smart Attendance System: Running Absent Notifier Tests")
    print("==================================================")
    
    # Connect to the DB to setup test data
    conn = absent_notifier.get_db_connection()
    cursor = conn.cursor()
    
    # 1. Setup a clean environment - Ensure tables exist
    init_db()
    absent_notifier.init_notifier_db()
    
    today_str = datetime.now().strftime("%Y-%m-%d")
    test_roll = "TEST-ROLL-999"
    test_name = "Jane Doe Test"
    test_email = "janedoe@example.com"
    test_dept = "Computer Science"
    
    # Remove existing test student if they exist (clean run safety)
    cursor.execute("SELECT id FROM Students WHERE roll_number = ?", (test_roll,))
    existing = cursor.fetchone()
    if existing:
        student_id = existing['id']
        cursor.execute("DELETE FROM attendance WHERE student_id = ?", (student_id,))
        cursor.execute("DELETE FROM absent_emails_sent WHERE student_id = ?", (student_id,))
        cursor.execute("DELETE FROM Students WHERE id = ?", (student_id,))
        conn.commit()

    # 2. Insert dummy student
    print("Step 1: Registering a new test student...")
    cursor.execute(
        "INSERT INTO Students (name, roll_number, department, email) VALUES (?, ?, ?, ?)",
        (test_name, test_roll, test_dept, test_email)
    )
    conn.commit()
    
    # Get the inserted student's id
    cursor.execute("SELECT id FROM Students WHERE roll_number = ?", (test_roll,))
    student_id = cursor.fetchone()['id']
    print(f"Test student registered with ID: {student_id}")

    try:
        # 3. Test first absent email execution
        print("\nStep 2: Testing first notifier run (student is absent today)...")
        sent_emails_log.clear()
        
        # Run check
        absent_notifier.check_and_notify_absent_students(target_date=today_str)
        
        # Verify that we tried to send 1 email and logged it
        assert len(sent_emails_log) == 1, "Failed: Email should have been sent to the absent student."
        assert sent_emails_log[0]['email'] == test_email, "Failed: Wrong student email notified."
        print("Success: Notified absent student correctly.")
        
        # Check database tracking table
        cursor.execute(
            "SELECT 1 FROM absent_emails_sent WHERE student_id = ? AND date = ?",
            (student_id, today_str)
        )
        record = cursor.fetchone()
        assert record is not None, "Failed: Sent email was not recorded in absent_emails_sent tracking table."
        print("Success: Verification database record exists in absent_emails_sent.")

        # 4. Test duplicate prevention on second execution
        print("\nStep 3: Testing duplicate prevention (running notifier again for today)...")
        sent_emails_log.clear()
        
        absent_notifier.check_and_notify_absent_students(target_date=today_str)
        
        assert len(sent_emails_log) == 0, "Failed: Duplicate email was dispatched for the same day."
        print("Success: Duplicate prevention succeeded (no email sent on rerun).")

        # 5. Test when student marks attendance (no longer absent)
        print("\nStep 4: Testing behavior after student marks attendance...")
        # Clear tracker to check if attendance prevents dispatch even without the tracker entry
        cursor.execute("DELETE FROM absent_emails_sent WHERE student_id = ?", (student_id,))
        # Mark present
        cursor.execute(
            "INSERT INTO attendance (student_id, date, time, status) VALUES (?, ?, ?, ?)",
            (student_id, today_str, "09:00:00", "Present")
        )
        conn.commit()
        
        sent_emails_log.clear()
        absent_notifier.check_and_notify_absent_students(target_date=today_str)
        
        assert len(sent_emails_log) == 0, "Failed: Notified student who is marked Present today."
        print("Success: Present student is not notified.")

    except AssertionError as ae:
        print(f"\n❌ TEST FAILED: {ae}")
    except Exception as e:
        print(f"\n❌ TEST ERRORED: {e}")
    else:
        print("\n✅ ALL TESTS PASSED SUCCESSFULLY!")
        
    finally:
        # 6. Cleanup database records
        print("\nStep 5: Cleaning up test data...")
        cursor.execute("DELETE FROM attendance WHERE student_id = ?", (student_id,))
        cursor.execute("DELETE FROM absent_emails_sent WHERE student_id = ?", (student_id,))
        cursor.execute("DELETE FROM Students WHERE id = ?", (student_id,))
        conn.commit()
        conn.close()
        print("Cleanup completed.")

if __name__ == "__main__":
    run_tests()
