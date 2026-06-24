import os
import sqlite3
import smtplib
import logging
import threading
import time
from datetime import datetime, timedelta
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# Define path configurations
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_FILE = os.path.join(BASE_DIR, "absent_notifier.log")
DB_PATH = os.path.join(BASE_DIR, "attendance.db")

# Setup logging configuration (logs to file and terminal console)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] (%(filename)s:%(lineno)d): %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("absent_notifier")

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
    # If email_config is missing or fails to import, default to secure standard Gmail
    SMTP_SERVER = os.environ.get("SMTP_SERVER", "smtp.gmail.com")
    try:
        SMTP_PORT = int(os.environ.get("SMTP_PORT", 587))
    except ValueError:
        SMTP_PORT = 587
    SMTP_USE_TLS = os.environ.get("SMTP_USE_TLS", "True").lower() in ("true", "1", "yes")

def get_db_connection():
    """Creates a connection to the SQLite database."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_notifier_db():
    """Initializes the database tables required for the absent notifier tracker."""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
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
        conn.commit()
        logger.info("Notifier tracking database checked/initialized successfully.")
    except sqlite3.Error as e:
        logger.error(f"Error checking/initializing notifier tracking database: {e}")
    finally:
        conn.close()

def send_absent_email(student_name, student_email, date_str):
    """Sends the absent alert email to the specified student email."""
    if not student_email:
        logger.warning(f"Skip email dispatch: Student '{student_name}' does not have a registered email address.")
        return False

    if not SMTP_EMAIL or not SMTP_PASSWORD or SMTP_EMAIL == "your-email@gmail.com" or SMTP_PASSWORD == "your-gmail-app-password":
        logger.error("Skip email dispatch: SMTP credentials are not configured. Please set SMTP_EMAIL and SMTP_PASSWORD env variables.")
        return False

    try:
        msg = MIMEMultipart()
        msg['From'] = SMTP_EMAIL
        msg['To'] = student_email
        msg['Subject'] = "Attendance Alert"

        # Specific user-requested email template
        body = f"Dear {student_name},\n\n" \
               f"Our records indicate that your attendance was not marked today ({date_str}).\n\n" \
               f"If this is incorrect, please contact your faculty or administrator.\n\n" \
               f"Regards,\n" \
               f"Smart Attendance System"
               
        msg.attach(MIMEText(body, 'plain'))

        # Standard secure Gmail SMTP process
        server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
        server.ehlo()
        if SMTP_USE_TLS:
            server.starttls()
            server.ehlo()
        server.login(SMTP_EMAIL, SMTP_PASSWORD)
        server.sendmail(SMTP_EMAIL, student_email, msg.as_string())
        server.quit()
        logger.info(f"Successfully sent absent notification email to {student_name} ({student_email})")
        return True
    except Exception as e:
        logger.error(f"Failed to send email to {student_email}: {str(e)}")
        return False

def check_and_notify_absent_students(target_date=None):
    """
    Identifies absent students for target_date and dispatches alert emails.
    Prevents duplicate notifications for the same day.
    """
    if target_date is None:
        target_date = datetime.now().strftime("%Y-%m-%d")

    logger.info(f"Starting check for absent students on: {target_date}")
    
    # Initialize the tracker table
    init_notifier_db()

    conn = get_db_connection()
    cursor = conn.cursor()

    # Query: Find students who:
    # 1. do not have any entry in 'attendance' for target_date
    # 2. do not have any entry in 'absent_emails_sent' for target_date
    query = """
        SELECT s.id, s.name, s.email, s.roll_number
        FROM Students s
        WHERE NOT EXISTS (
            SELECT 1 FROM attendance a
            WHERE a.student_id = s.id AND a.date = ?
        )
        AND NOT EXISTS (
            SELECT 1 FROM absent_emails_sent e
            WHERE e.student_id = s.id AND e.date = ?
        )
    """
    
    try:
        cursor.execute(query, (target_date, target_date))
        absent_students = cursor.fetchall()
        
        if not absent_students:
            logger.info(f"No new absent students to notify for {target_date}.")
            return

        logger.info(f"Found {len(absent_students)} absent student(s) requiring notification.")

        for student in absent_students:
            s_id = student['id']
            s_name = student['name']
            s_email = student['email']
            
            # Attempt to send the email
            success = send_absent_email(s_name, s_email, target_date)
            
            if success:
                # Record successful notification in tracking table
                try:
                    cursor.execute(
                        "INSERT INTO absent_emails_sent (student_id, date) VALUES (?, ?)",
                        (s_id, target_date)
                    )
                    conn.commit()
                    logger.info(f"Logged absent alert email for Student ID {s_id} on {target_date}.")
                except sqlite3.Error as db_err:
                    logger.error(f"Error logging sent email in database for Student ID {s_id}: {db_err}")
                    
    except sqlite3.Error as e:
        logger.error(f"Database error executing absent check: {e}")
    finally:
        conn.close()

_scheduler_thread = None

def run_scheduler_loop():
    """Scheduler background loop that runs the notifier daily at 5:00 PM (17:00)."""
    logger.info("Daily scheduler background thread loop initiated.")
    while True:
        try:
            now = datetime.now()
            # Set the target notification time to 5:00 PM today
            target_time = now.replace(hour=17, minute=0, second=0, microsecond=0)
            
            # If 5:00 PM has already passed, schedule for 5:00 PM tomorrow
            if now >= target_time:
                target_time += timedelta(days=1)
                
            sleep_duration = (target_time - now).total_seconds()
            logger.info(f"Scheduler sleeping for {sleep_duration:.1f} seconds. Next run at: {target_time}")
            
            # Sleep until target time
            time.sleep(sleep_duration)
            
            # Execute notifier
            logger.info("Scheduler limit reached. Triggering automatic absent check...")
            check_and_notify_absent_students()
            
        except Exception as e:
            logger.error(f"Error in scheduler daemon loop: {e}", exc_info=True)
            # Sleep 60 seconds before retrying to prevent high CPU usage on loop failures
            time.sleep(60)

def start_scheduler():
    """Starts the absent notifier scheduler in a daemon thread if it is not already running."""
    global _scheduler_thread
    if _scheduler_thread is not None and _scheduler_thread.is_alive():
        logger.info("Scheduler thread is already active.")
        return

    _scheduler_thread = threading.Thread(target=run_scheduler_loop, name="AbsentNotifierScheduler")
    _scheduler_thread.daemon = True
    _scheduler_thread.start()
    logger.info("Scheduler thread spawned successfully.")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Absent Student Notification Module")
    parser.add_argument("--now", action="store_true", help="Run the notifier immediately for today")
    parser.add_argument("--date", type=str, help="Run the notifier for a specific date (YYYY-MM-DD)")
    parser.add_argument("--scheduler", action="store_true", help="Start the scheduler and keep it running in the foreground")
    
    args = parser.parse_args()
    
    # Pre-initialize notifier database
    init_notifier_db()
    
    if args.now:
        logger.info("Running manual notification check for today...")
        check_and_notify_absent_students()
    elif args.date:
        logger.info(f"Running manual notification check for target date: {args.date}...")
        check_and_notify_absent_students(target_date=args.date)
    elif args.scheduler:
        logger.info("Starting scheduler in foreground mode...")
        try:
            run_scheduler_loop()
        except KeyboardInterrupt:
            logger.info("Foreground scheduler stopped by user.")
    else:
        print("Smart Attendance System - Absent Notifier CLI")
        print("Usage:")
        print("  python absent_notifier.py --now             Run notification check immediately for today")
        print("  python absent_notifier.py --date YYYY-MM-DD  Run notification check for a specific date")
        print("  python absent_notifier.py --scheduler       Start the scheduler in the foreground")
