# email_config.py
# SMTP configuration settings for sending attendance emails.

# For standard Gmail SMTP:
# 1. Set SMTP_SERVER = "smtp.gmail.com"
# 2. Set SMTP_PORT = 587
# 3. Set SMTP_EMAIL to your Gmail address (e.g. user@gmail.com).
# 4. Set SMTP_PASSWORD to your 16-character Gmail App Password (generated in Google Account settings).
#    Do NOT use your main account password.

SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587
SMTP_EMAIL = "your-email@gmail.com"
SMTP_PASSWORD = "your-gmail-app-password"
SMTP_USE_TLS = True
