# email_notifier.py
# Helper module to send email notifications in a background thread.

import os
import threading
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# Load SMTP email configuration from environment variables with fallback to email_config
SMTP_EMAIL = os.environ.get("SMTP_EMAIL")
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD")

try:
    import email_config
    if not SMTP_EMAIL or SMTP_EMAIL.strip() == "":
        if hasattr(email_config, "SMTP_EMAIL") and email_config.SMTP_EMAIL != "your-email@gmail.com":
            SMTP_EMAIL = email_config.SMTP_EMAIL
    if not SMTP_PASSWORD or SMTP_PASSWORD.strip() == "":
        if hasattr(email_config, "SMTP_PASSWORD") and email_config.SMTP_PASSWORD != "your-gmail-app-password":
            SMTP_PASSWORD = email_config.SMTP_PASSWORD
            
    SMTP_SERVER = os.environ.get("SMTP_SERVER", getattr(email_config, "SMTP_SERVER", "smtp.gmail.com"))
    
    port_env = os.environ.get("SMTP_PORT")
    if port_env:
        try:
            SMTP_PORT = int(port_env)
        except ValueError:
            SMTP_PORT = 587
    else:
        SMTP_PORT = getattr(email_config, "SMTP_PORT", 587)
        
    tls_env = os.environ.get("SMTP_USE_TLS")
    if tls_env:
        SMTP_USE_TLS = tls_env.lower() in ("true", "1", "yes")
    else:
        SMTP_USE_TLS = getattr(email_config, "SMTP_USE_TLS", True)
except ImportError:
    SMTP_SERVER = os.environ.get("SMTP_SERVER", "smtp.gmail.com")
    try:
        SMTP_PORT = int(os.environ.get("SMTP_PORT", 587))
    except ValueError:
        SMTP_PORT = 587
    SMTP_USE_TLS = os.environ.get("SMTP_USE_TLS", "True").lower() in ("true", "1", "yes")

def send_attendance_email_async(student_name, student_email, date_str, time_str):
    """
    Spawns a background thread to send the attendance notification email.
    This prevents SMTP server connection lag from blocking the camera frame loop.
    """
    # Create a daemon thread so it terminates automatically when the main app exits
    thread = threading.Thread(
        target=send_email_worker,
        args=(student_name, student_email, date_str, time_str)
    )
    thread.daemon = True
    thread.start()

def send_email_worker(student_name, student_email, date_str, time_str):
    """
    Worker function executed in the background thread to handle SMTP transmission.
    """
    # Verify if student has an email registered
    if not student_email:
        print("[Email Notification] Skip: Student does not have an email registered.")
        return

    # Skip sending if the user hasn't updated the default configuration
    if not SMTP_EMAIL or not SMTP_PASSWORD or SMTP_EMAIL == "your-email@gmail.com" or SMTP_PASSWORD == "your-gmail-app-password":
        print("[Email Notification] Skip: SMTP credentials are not configured. Please set SMTP_EMAIL and SMTP_PASSWORD env variables.")
        return

    try:
        # Create message container
        msg = MIMEMultipart()
        msg['From'] = SMTP_EMAIL
        msg['To'] = student_email
        msg['Subject'] = "Attendance Recorded"

        # Email body template
        body = f"""Hello {student_name},

Your attendance has been successfully recorded.

Date: {date_str}
Time: {time_str}
"""
        msg.attach(MIMEText(body, 'plain'))

        # Connect to the specified SMTP server
        server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
        server.ehlo()

        # Start TLS encryption if enabled
        if SMTP_USE_TLS:
            server.starttls()
            server.ehlo()

        # Login using SMTP credentials
        server.login(SMTP_EMAIL, SMTP_PASSWORD)
        
        # Send email
        server.sendmail(SMTP_EMAIL, student_email, msg.as_string())
        server.quit()
        print(f"[Email Notification] Success: Attendance confirmation email sent to {student_email}.")
    except Exception as e:
        print(f"[Email Notification] Error: Failed to send email to {student_email}. Details: {str(e)}")
