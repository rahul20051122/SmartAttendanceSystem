import os
import sqlite3

# Define the database path.
# To prevent database files from being created in random folders when running Flask,
# we base the path on the location of this database.py file.
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "attendance.db")

def get_db_connection():
    """
    Establishes and returns a connection to the SQLite database.
    Setting row_factory allows us to access column values by their column names,
    e.g., row['name'] instead of row[1].
    """
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """
    Creates the database tables (Students and Attendance) if they don't already exist.
    This is called when the application starts up.
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    # Database Migration: Check if 'Students' table exists and uses AUTOINCREMENT
    cursor.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='Students'")
    row = cursor.fetchone()
    if row:
        table_sql = row[0]
        if "AUTOINCREMENT" in table_sql.upper():
            print("Database migration: Removing AUTOINCREMENT from Students table schema...")
            # 1. Rename existing Students table to temp table
            cursor.execute("ALTER TABLE Students RENAME TO Students_old")
            
            # 2. Create the new Students table without AUTOINCREMENT
            cursor.execute('''
                CREATE TABLE Students (
                    id INTEGER PRIMARY KEY,
                    name TEXT NOT NULL,
                    roll_number TEXT UNIQUE NOT NULL,
                    department TEXT NOT NULL,
                    email TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # 3. Copy data from the old table to the new table
            cursor.execute('''
                INSERT INTO Students (id, name, roll_number, department, email, created_at)
                SELECT id, name, roll_number, department, email, created_at FROM Students_old
            ''')
            
            # 4. Drop the temp table
            cursor.execute("DROP TABLE Students_old")
            
            # 5. Remove the Students record from sqlite_sequence if it exists
            try:
                cursor.execute("DELETE FROM sqlite_sequence WHERE name='Students'")
            except sqlite3.Error:
                pass
                
            conn.commit()
            print("Database migration complete: AUTOINCREMENT removed from Students table.")

    # Create the Students table (without AUTOINCREMENT)
    # - id: Unique identifier (Primary Key)
    # - name: Student's name (cannot be empty)
    # - roll_number: Student's unique roll number (cannot be duplicated)
    # - department: Student's department (e.g., CSE, ECE)
    # - created_at: The date and time when the student was registered
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS Students (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            roll_number TEXT UNIQUE NOT NULL,
            department TEXT NOT NULL,
            email TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Create the Attendance table
    # - id: Unique attendance record identifier
    # - student_id: Links to the student's id in the Students table (Foreign Key)
    # - date: The date of attendance (e.g., YYYY-MM-DD)
    # - time: The time of attendance (e.g., HH:MM:SS)
    # - status: 'Present' or 'Absent'
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS Attendance (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id INTEGER NOT NULL,
            date TEXT NOT NULL,
            time TEXT NOT NULL,
            status TEXT NOT NULL,
            FOREIGN KEY (student_id) REFERENCES Students (id)
        )
    ''')

    # Create the Faculty table
    # - id: Unique identifier (Primary Key)
    # - name: Faculty's name (cannot be empty)
    # - employee_id: Faculty's unique employee identifier (cannot be duplicated)
    # - department: Faculty's department (e.g., CSE, ECE)
    # - created_at: Timestamp when registered
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS Faculty (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            employee_id TEXT UNIQUE NOT NULL,
            department TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Create the absent_emails_sent table
    # - id: Unique identifier
    # - student_id: Links to the student's id in the Students table (Foreign Key)
    # - date: The date when the email was sent
    # - sent_at: Timestamp when sent
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS absent_emails_sent (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id INTEGER NOT NULL,
            date TEXT NOT NULL,
            sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (student_id) REFERENCES Students (id),
            UNIQUE(student_id, date)
        )
    ''')

    # Database Migration: Check if 'email' column exists in Students, add it if missing
    try:
        cursor.execute("PRAGMA table_info(Students)")
        columns = [col[1] for col in cursor.fetchall()]
        if 'email' not in columns:
            cursor.execute("ALTER TABLE Students ADD COLUMN email TEXT")
            conn.commit()
            print("Database migration: Added 'email' column to Students table.")
    except sqlite3.Error as migration_err:
        print(f"Database migration warning: {str(migration_err)}")

    # Save (commit) the changes and close the connection
    conn.commit()
    conn.close()
    print("Database connection established and tables checked/created.")

def insert_student(name, roll_number, department, email=None):
    """
    Inserts a new student record into the Students table.
    Returns True if successfully inserted, or False if the roll number already exists.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        # Execute the INSERT command with placeholders to prevent SQL Injection
        cursor.execute(
            "INSERT INTO Students (name, roll_number, department, email) VALUES (?, ?, ?, ?)",
            (name, roll_number, department, email)
        )
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        # sqlite3.IntegrityError is raised if the roll_number already exists (UNIQUE constraint fails)
        return False
    finally:
        # Always close the connection when done
        conn.close()

def delete_student_by_id(student_id):
    """
    Deletes a student record and their attendance logs from the database.
    Returns True on success, or False if an error occurs.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        # Delete the student's absent emails sent logs first
        cursor.execute("DELETE FROM absent_emails_sent WHERE student_id = ?", (student_id,))
        # Delete the student's attendance records
        cursor.execute("DELETE FROM attendance WHERE student_id = ?", (student_id,))
        # Delete the student record itself
        cursor.execute("DELETE FROM Students WHERE id = ?", (student_id,))
        conn.commit()
        return True
    except sqlite3.Error as e:
        print(f"Database error during student deletion: {str(e)}")
        return False
    finally:
        conn.close()

def insert_faculty(name, employee_id, department):
    """
    Inserts a new faculty record into the Faculty table.
    Returns True if successfully inserted, or False if employee_id already exists.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "INSERT INTO Faculty (name, employee_id, department) VALUES (?, ?, ?)",
            (name, employee_id, department)
        )
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()

def get_all_faculty():
    """
    Fetches all registered faculty from the Faculty table.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM Faculty ORDER BY created_at DESC")
    faculty = cursor.fetchall()
    conn.close()
    return faculty

def delete_faculty_by_id(faculty_id):
    """
    Deletes a faculty record from the Faculty table.
    Returns True on success, or False if an error occurs.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM Faculty WHERE id = ?", (faculty_id,))
        conn.commit()
        return True
    except sqlite3.Error as e:
        print(f"Database error during faculty deletion: {str(e)}")
        return False
    finally:
        conn.close()

def get_all_students():
    """
    Fetches all registered students from the Students table.
    Ordered by registration time (newest first).
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM Students ORDER BY created_at DESC")
    students = cursor.fetchall()
    conn.close()
    return students
