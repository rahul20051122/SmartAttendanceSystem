import os
import sqlite3
from datetime import datetime

# Define database location relative to the location of this script
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "attendance.db")

def get_db_connection():
    """
    Establishes and returns a connection to the SQLite database.
    Using row_factory allows accessing columns like dictionary keys, e.g., row['status'].
    """
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def create_attendance_table():
    """
    Creates the 'attendance' table in the database if it does not already exist.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Execute the CREATE TABLE query
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS attendance (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id INTEGER,
            date TEXT,
            time TEXT,
            status TEXT
        )
    ''')
    
    conn.commit()
    conn.close()
    print("Table 'attendance' checked/created successfully.")

def attendance_exists(student_id):
    """
    Checks if a student has already had their attendance marked today.
    
    Parameters:
        student_id (int): The unique ID of the student.
        
    Returns:
        bool: True if attendance was already marked today, False otherwise.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Get today's date in YYYY-MM-DD format
    today_date = datetime.now().strftime("%Y-%m-%d")
    
    # Check if a record exists for this student_id on today's date
    cursor.execute(
        "SELECT id FROM attendance WHERE student_id = ? AND date = ?",
        (student_id, today_date)
    )
    record = cursor.fetchone()
    conn.close()
    
    return record is not None

def mark_attendance(student_id):
    """
    Marks attendance for a student for the current day.
    Checks first if the student exists and if the record exists to prevent duplicates.
    
    Parameters:
        student_id (int): The unique ID of the student.
        
    Returns:
        tuple: (bool, str) representing (success_status, message).
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        # 1. Verify if the student exists in the database
        cursor.execute("SELECT name, email FROM Students WHERE id = ?", (student_id,))
        student = cursor.fetchone()
        if not student:
            return False, f"Error: Student with ID {student_id} does not exist."
            
        s_name = student['name']
        s_email = student['email']
        
        # 2. Check if student already marked present today
        today_date = datetime.now().strftime("%Y-%m-%d")
        cursor.execute(
            "SELECT id FROM attendance WHERE student_id = ? AND date = ?",
            (student_id, today_date)
        )
        if cursor.fetchone() is not None:
            return False, "Attendance already marked for today."
            
        # 3. Insert new attendance record
        current_date = datetime.now().strftime("%Y-%m-%d")
        current_time = datetime.now().strftime("%H:%M:%S")
        status = "Present"
        
        cursor.execute(
            "INSERT INTO attendance (student_id, date, time, status) VALUES (?, ?, ?, ?)",
            (student_id, current_date, current_time, status)
        )
        conn.commit()

        # Dispatch email asynchronously to prevent blocking the webcam interface
        if s_email:
            from email_notifier import send_attendance_email_async
            send_attendance_email_async(s_name, s_email, current_date, current_time)

        return True, f"Attendance marked successfully as '{status}' at {current_time}."
    except sqlite3.Error as e:
        return False, f"Database error occurred: {str(e)}"
    finally:
        conn.close()

def get_today_attendance():
    """
    Fetches all attendance records marked for the current day.
    Joins with 'Students' table to retrieve the student's name and roll number.
    
    Returns:
        list: A list of sqlite3.Row objects containing today's attendance details.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Get today's date in YYYY-MM-DD format
    today_date = datetime.now().strftime("%Y-%m-%d")
    
    # SQL Query performing an INNER JOIN to retrieve student details along with attendance records
    query = """
        SELECT a.id, a.student_id, s.name, s.roll_number, a.date, a.time, a.status 
        FROM attendance a
        INNER JOIN Students s ON a.student_id = s.id
        WHERE a.date = ?
        ORDER BY a.time DESC
    """
    
    try:
        cursor.execute(query, (today_date,))
        records = cursor.fetchall()
        return records
    except sqlite3.Error:
        # Fallback to query only 'attendance' if Students table join fails or schema differs
        try:
            cursor.execute("SELECT * FROM attendance WHERE date = ? ORDER BY time DESC", (today_date,))
            return cursor.fetchall()
        except sqlite3.Error:
            # If the attendance table does not exist in the database yet, return an empty list
            return []
    finally:
        conn.close()

def get_attendance_by_date(selected_date):
    """
    Fetches all attendance records marked for a specific date (YYYY-MM-DD).
    Joins with 'Students' table to retrieve the student's name and roll number.
    
    Parameters:
        selected_date (str): The target date in YYYY-MM-DD format.
        
    Returns:
        list: A list of sqlite3.Row objects containing the attendance details.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # SQL Query performing an INNER JOIN to retrieve student details along with attendance records
    query = """
        SELECT a.id, a.student_id, s.name, s.roll_number, a.date, a.time, a.status 
        FROM attendance a
        INNER JOIN Students s ON a.student_id = s.id
        WHERE a.date = ?
        ORDER BY a.time DESC
    """
    
    try:
        cursor.execute(query, (selected_date,))
        records = cursor.fetchall()
        return records
    except sqlite3.Error:
        # Fallback to query only 'attendance' if Students table join fails or schema differs
        try:
            cursor.execute("SELECT * FROM attendance WHERE date = ? ORDER BY time DESC", (selected_date,))
            return cursor.fetchall()
        except sqlite3.Error:
            # If the attendance table does not exist in the database yet, return an empty list
            return []
    finally:
        conn.close()

def get_analytics_summary():
    """
    Returns a dictionary containing key metrics:
    - total_students: Total count of registered students
    - total_records: Total count of all attendance entries
    - present_today: Total count of students marked present today
    - absent_today: Total count of students absent today (total_students - present_today)
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        today_date = datetime.now().strftime("%Y-%m-%d")
        
        # Total Students
        cursor.execute("SELECT COUNT(*) FROM Students")
        total_students = cursor.fetchone()[0] or 0
        
        # Total Attendance Records
        cursor.execute("SELECT COUNT(*) FROM attendance")
        total_records = cursor.fetchone()[0] or 0
        
        # Present Today
        cursor.execute("SELECT COUNT(DISTINCT student_id) FROM attendance WHERE date = ?", (today_date,))
        present_today = cursor.fetchone()[0] or 0
        
        # Absent Today
        absent_today = max(0, total_students - present_today)
        
        return {
            "total_students": total_students,
            "total_records": total_records,
            "present_today": present_today,
            "absent_today": absent_today
        }
    finally:
        conn.close()

def get_monthly_attendance_data():
    """
    Fetches the count of marked attendance records grouped by month (YYYY-MM).
    Returns a tuple of (labels, values) for Chart.js.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        # Group and count by month
        query = """
            SELECT strftime('%Y-%m', date) as month, COUNT(*) as count
            FROM attendance
            GROUP BY month
            ORDER BY month ASC
        """
        cursor.execute(query)
        rows = cursor.fetchall()
        
        labels = []
        values = []
        for row in rows:
            month_str = row['month']
            try:
                dt = datetime.strptime(month_str, "%Y-%m")
                formatted_label = dt.strftime("%b %Y")
            except Exception:
                formatted_label = month_str
            
            labels.append(formatted_label)
            values.append(row['count'])
            
        return labels, values
    finally:
        conn.close()

def get_student_attendance_stats():
    """
    Fetches attendance stats for each student:
    - name, roll_number, department
    - present_count (number of days marked present)
    - percentage (present_count / total_days * 100)
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        # 1. Get total unique dates when attendance was marked
        cursor.execute("SELECT COUNT(DISTINCT date) FROM attendance")
        total_days = cursor.fetchone()[0] or 0
        
        # 2. Get present count for all students
        query = """
            SELECT s.id, s.name, s.roll_number, s.department, COUNT(a.id) as present_count
            FROM Students s
            LEFT JOIN attendance a ON s.id = a.student_id
            GROUP BY s.id, s.name, s.roll_number, s.department
            ORDER BY s.name ASC
        """
        cursor.execute(query)
        rows = cursor.fetchall()
        
        stats = []
        for row in rows:
            present_count = row['present_count']
            pct = round((present_count / total_days) * 100, 1) if total_days > 0 else 0.0
            stats.append({
                "id": row['id'],
                "name": row['name'],
                "roll_number": row['roll_number'],
                "department": row['department'],
                "present_count": present_count,
                "percentage": pct
            })
            
        return stats, total_days
    finally:
        conn.close()

# Test block to verify functionalities when run directly
if __name__ == "__main__":
    print("Running attendance manager test script...")
    create_attendance_table()
    
    # Fetch today's records
    today_records = get_today_attendance()
    print(f"Retrieved {len(today_records)} attendance record(s) for today.")
