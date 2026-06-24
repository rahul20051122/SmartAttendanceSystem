from flask import Flask, render_template, request, redirect, url_for, flash, Response
from database import init_db, insert_student, get_all_students, delete_student_by_id, insert_faculty, get_all_faculty, delete_faculty_by_id

# Instantiate the Flask application
app = Flask(__name__)

# Secret key is required to use Flask's session messaging system (flash)
app.secret_key = 'smart_attendance_system_secret_key_change_me'

@app.route('/')
def home():
    """
    Dashboard route. Fetches registered students and faculty, calculates stats for today's attendance,
    and displays them on the dashboard homepage.
    """
    from attendance_manager import get_today_attendance
    
    students_list = get_all_students()
    faculty_list = get_all_faculty()
    today_records = get_today_attendance()
    
    total_students = len(students_list)
    total_faculty = len(faculty_list)
    total_present = len(today_records)
    
    # Calculate attendance percentage
    if total_students > 0:
        attendance_percentage = round((total_present / total_students) * 100, 1)
    else:
        attendance_percentage = 0.0
        
    return render_template(
        'index.html',
        students=students_list,
        faculty=faculty_list,
        total_students=total_students,
        total_faculty=total_faculty,
        total_present=total_present,
        attendance_percentage=attendance_percentage
    )

@app.route('/register', methods=['GET', 'POST'])
def register_student():
    """
    Student registration route.
    - GET: Displays the blank registration form to the user.
    - POST: Captures student details submitted via the form, processes them,
      and attempts to write them to the SQLite database.
    """
    if request.method == 'POST':
        # Retrieve form data submitted by the user
        name = request.form.get('name', '').strip()
        roll_number = request.form.get('roll_number', '').strip()
        department = request.form.get('department', '').strip()
        email = request.form.get('email', '').strip()
        
        # Simple backend validation checks
        if not name or not roll_number or not department or not email:
            flash("All fields are required!", "danger")
            return redirect(url_for('register_student'))
            
        # Attempt to insert the student into the database
        success = insert_student(name, roll_number, department, email)
        
        if success:
            # Send a success message to the next page and redirect to the dashboard
            flash(f"Student '{name}' registered successfully!", "success")
            return redirect(url_for('home'))
        else:
            # Integrity error triggered, likely due to duplicate roll number
            flash(f"Error: Roll Number '{roll_number}' is already registered!", "danger")
            return redirect(url_for('register_student'))

    # If request is GET, just render the blank registration form
    return render_template('register.html')

@app.route('/delete/<int:student_id>', methods=['POST'])
def delete_student_route(student_id):
    """
    Deletes a student from the database, deletes their face datasets from disk,
    and removes their attendance logs.
    """
    import os
    import shutil
    
    # 1. Retrieve base directory for dataset path
    base_dir = os.path.dirname(os.path.abspath(__file__))
    dataset_dir = os.path.join(base_dir, "dataset", str(student_id))
    
    # 2. Delete the student's face dataset directory if it exists
    if os.path.exists(dataset_dir):
        try:
            shutil.rmtree(dataset_dir)
        except Exception as e:
            flash(f"Error removing face dataset files: {str(e)}", "danger")
            return redirect(url_for('home'))
            
    # 3. Delete student and attendance logs from the database
    success = delete_student_by_id(student_id)
    if success:
        flash("Student details and all associated logs deleted successfully! Please train the model to update face embeddings.", "success")
    else:
        flash("Failed to delete student from the database.", "danger")
        
    return redirect(url_for('home'))

@app.route('/register_faculty', methods=['POST'])
def register_faculty_route():
    """
    Faculty registration POST handler.
    Captures faculty details submitted via form and writes them to the database.
    """
    name = request.form.get('name', '').strip()
    employee_id = request.form.get('employee_id', '').strip()
    department = request.form.get('department', '').strip()
    
    if not name or not employee_id or not department:
        flash("All fields are required for faculty registration!", "danger")
        return redirect(url_for('register_student'))
        
    success = insert_faculty(name, employee_id, department)
    
    if success:
        flash(f"Faculty '{name}' registered successfully!", "success")
    else:
        flash(f"Error: Employee ID '{employee_id}' is already registered!", "danger")
        
    return redirect(url_for('home'))

@app.route('/delete_faculty/<int:faculty_id>', methods=['POST'])
def delete_faculty_route(faculty_id):
    """
    Deletes a faculty member from the database.
    """
    success = delete_faculty_by_id(faculty_id)
    if success:
        flash("Faculty details deleted successfully!", "success")
    else:
        flash("Failed to delete faculty from the database.", "danger")
        
    return redirect(url_for('home'))

@app.route('/capture/<int:student_id>')
def capture_faces(student_id):
    """
    Redirects the legacy capture URL to the new live capture page.
    """
    return redirect(url_for('capture_live', student_id=student_id))

@app.route('/capture_live/<int:student_id>')
def capture_live(student_id):
    """
    Renders the professional browser-based face capture page.
    """
    from database import get_db_connection
    
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT name, roll_number, department FROM Students WHERE id = ?", (student_id,))
    student = cursor.fetchone()
    conn.close()
    
    if not student:
        flash("Student profile not found!", "danger")
        return redirect(url_for('home'))
        
    return render_template(
        'capture_live.html',
        student_id=student_id,
        student_name=student['name'],
        roll_number=student['roll_number'],
        department=student['department']
    )

@app.route('/webcam_stream/<int:student_id>')
def video_feed_capture(student_id):
    """
    Returns the multipart stream for live face capture.
    """
    from face_capture import generate_capture_frames
    return Response(
        generate_capture_frames(student_id),
        mimetype='multipart/x-mixed-replace; boundary=frame'
    )

@app.route('/capture_progress/<int:student_id>')
def capture_progress(student_id):
    """
    API endpoint returning current capture progress count as JSON.
    """
    from face_capture import get_capture_progress
    progress = get_capture_progress(student_id)
    return {"progress": progress}

@app.route('/train')
def train_model_route():
    """
    Triggers the training process for the face recognition model.
    - Calls the train_recognizer function from train_model.py.
    - Displays a success or error message on the dashboard via Flask's flash system.
    - Redirects back to the dashboard homepage.
    """
    from train_model import train_recognizer
    success, message = train_recognizer()
    
    if success:
        flash(message, "success")
    else:
        flash(message, "danger")
        
    return redirect(url_for('home'))

@app.route('/video_feed')
def video_feed():
    """
    Webcam video streaming route. Returns the face recognition camera feed.
    """
    from face_recognition import generate_recognition_frames
    return Response(generate_recognition_frames(), mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/camera_test')
def camera_test():
    """
    Diagnostics route. Runs a quick open_webcam() check and renders camera_test.html
    with current status and index details.
    """
    from face_recognition import open_webcam, close_webcam
    cap, index = open_webcam("Webcam Diagnostic Route")
    if cap is not None:
        close_webcam(cap, "Webcam Diagnostic Route")
        status = "Online"
    else:
        status = "Offline"
        
    return render_template('camera_test.html', status=status, index=index)

@app.route('/camera_test_feed')
def camera_test_feed():
    """
    Returns the raw diagnostic video stream.
    """
    from face_recognition import generate_diagnostic_frames
    return Response(generate_diagnostic_frames(), mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/mark_attendance')
def mark_attendance_page():
    """
    Renders the dedicated standalone face recognition attendance page.
    """
    from attendance_manager import get_today_attendance
    records = get_today_attendance()
    return render_template('mark_attendance.html', records=records)

@app.route('/api/today_attendance')
def api_today_attendance():
    """
    API endpoint returning today's marked attendance records as JSON.
    """
    from attendance_manager import get_today_attendance
    records = get_today_attendance()
    data = []
    for r in records:
        data.append({
            "name": r['name'],
            "roll_number": r['roll_number'],
            "time": r['time']
        })
    return {"records": data}
        
@app.route('/attendance_report')
def attendance_report():
    """
    Renders today's attendance report page.
    Fetches records using get_today_attendance() from attendance_manager.py.
    """
    from attendance_manager import get_today_attendance
    records = get_today_attendance()
    return render_template('attendance_report.html', records=records)

@app.route('/attendance_history', methods=['GET'])
def attendance_history():
    """
    Renders the attendance history query page.
    Fetches attendance records for the selected date (defaults to today).
    """
    from datetime import datetime
    from attendance_manager import get_attendance_by_date
    
    # Retrieve target date from query parameters; fallback to current date
    selected_date = request.args.get('date', datetime.now().strftime("%Y-%m-%d"))
    
    records = get_attendance_by_date(selected_date)
    return render_template(
        'attendance_history.html',
        records=records,
        selected_date=selected_date
    )

@app.route('/export_excel')
def export_excel():
    """
    Exports today's attendance records to an Excel file using Pandas and openpyxl,
    and sends it to the browser as a download attachment.
    """
    import io
    import pandas as pd
    from flask import send_file
    from attendance_manager import get_today_attendance
    
    records = get_today_attendance()
    
    if not records:
        flash("No attendance records to export today!", "danger")
        return redirect(url_for('home'))
        
    # Convert records to a list of dicts to easily load into a Pandas DataFrame
    data = []
    for r in records:
        data.append({
            "Record ID": r['id'],
            "Student ID": r['student_id'],
            "Student Name": r['name'],
            "Roll Number": r['roll_number'],
            "Date": r['date'],
            "Time": r['time'],
            "Status": r['status']
        })
        
    df = pd.DataFrame(data)
    
    # Create an in-memory byte buffer to write Excel data to
    buffer = io.BytesIO()
    
    # Use Pandas ExcelWriter with openpyxl engine
    with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name="Today's Attendance")
        
    # Rewind the buffer to the beginning before reading from it
    buffer.seek(0)
    
    return send_file(
        buffer,
        as_attachment=True,
        download_name="attendance_report.xlsx",
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

@app.route('/about')
def about_page():
    """
    Renders the dedicated About & Instructions page.
    """
    return render_template('about.html')

@app.route('/analytics')
def analytics_page():
    """
    Attendance Analytics Dashboard route.
    Fetches statistics summary, monthly trend, and individual student stats.
    Calculates top 5 regular students and alerts for students with < 75% attendance.
    """
    from attendance_manager import (
        get_analytics_summary,
        get_monthly_attendance_data,
        get_student_attendance_stats
    )
    
    # 1. Summary Cards data
    summary = get_analytics_summary()
    
    # 2. Monthly Trend Chart data
    monthly_labels, monthly_values = get_monthly_attendance_data()
    
    # 3. Individual Student Stats
    student_stats, total_days = get_student_attendance_stats()
    
    # 4. Top 5 Regular Students: sorted by present_count desc, then name asc
    top_students = sorted(
        student_stats,
        key=lambda x: (-x['present_count'], x['name'])
    )[:5]
    
    # 5. Low Attendance Warnings: students below 75% (only check if total_days > 0)
    low_attendance_warnings = []
    if total_days > 0:
        low_attendance_warnings = [s for s in student_stats if s['percentage'] < 75.0]
        
    # 6. Extract arrays for student charts
    student_names = [s['name'] for s in student_stats]
    student_pcts = [s['percentage'] for s in student_stats]
        
    return render_template(
        'analytics.html',
        summary=summary,
        monthly_labels=monthly_labels,
        monthly_values=monthly_values,
        student_stats=student_stats,
        student_names=student_names,
        student_pcts=student_pcts,
        top_students=top_students,
        low_attendance_warnings=low_attendance_warnings,
        total_days=total_days
    )


if __name__ == "__main__":
    # Initialize the database and create tables if they do not exist
    init_db()
    
    # Start the background scheduler for daily absent student email notification at 5:00 PM.
    # Since the development server runs with use_reloader=False, we start the scheduler directly.
    from absent_notifier import start_scheduler
    start_scheduler()
    
    # Start the Flask development server on Windows 11
    # debug=True enables auto-reloading when you make changes to files
    app.run(debug=True, use_reloader=False)