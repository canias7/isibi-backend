import os
import secrets
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta

# Email configuration - Try SendGrid first, fallback to SMTP
SENDGRID_API_KEY = os.getenv("SENDGRID_API_KEY")
SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")
SMTP_FROM = os.getenv("SMTP_FROM", SMTP_USER)
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:3000")

# Try importing SendGrid
try:
    from sendgrid import SendGridAPIClient
    from sendgrid.helpers.mail import Mail
    SENDGRID_AVAILABLE = True
except ImportError:
    SENDGRID_AVAILABLE = False


def generate_reset_token():
    """Generate a secure random token for password reset"""
    return secrets.token_urlsafe(32)


def send_reset_email(email: str, reset_token: str) -> dict:
    """
    Send password reset email
    
    Args:
        email: User's email address
        reset_token: Password reset token
    
    Returns:
        {"success": bool, "error": str (if failed)}
    """
    # Try SendGrid first (works on Render without network access)
    if SENDGRID_AVAILABLE and SENDGRID_API_KEY:
        return send_reset_email_sendgrid(email, reset_token)
    
    # Check if we have any email method configured
    if not SENDGRID_API_KEY and (not SMTP_USER or not SMTP_PASSWORD):
        error_msg = "Email not configured. Please set SENDGRID_API_KEY environment variable in Render."
        print(f"❌ {error_msg}")
        return {
            "success": False,
            "error": error_msg
        }
    
    # Try SMTP (will fail on Render due to network restrictions)
    print("⚠️ SendGrid not available, attempting SMTP (may fail on Render due to network restrictions)...")
    
    try:
        # Create reset link
        reset_link = f"{FRONTEND_URL}/reset-password?token={reset_token}"
        
        # Create email message
        msg = MIMEMultipart('alternative')
        msg['Subject'] = "Password Reset Request - ISIBI Voice AI"
        msg['From'] = SMTP_FROM
        msg['To'] = email
        
        # Plain text version
        text = f"""
Password Reset Request

You requested to reset your password for your ISIBI Voice AI account.

Click the link below to reset your password:
{reset_link}

This link will expire in 1 hour.

If you didn't request this, please ignore this email.

- ISIBI Team
        """
        
        # HTML version
        html = get_reset_email_html(reset_link)
        
        # Attach both versions
        part1 = MIMEText(text, 'plain')
        part2 = MIMEText(html, 'html')
        msg.attach(part1)
        msg.attach(part2)
        
        # Send email
        server = smtplib.SMTP(SMTP_HOST, SMTP_PORT)
        server.starttls()
        server.login(SMTP_USER, SMTP_PASSWORD)
        server.send_message(msg)
        server.quit()
        
        print(f"✅ Password reset email sent to {email}")
        
        return {"success": True}
    
    except Exception as e:
        error_msg = str(e)
        
        # Provide helpful error message for network issues
        if "Network is unreachable" in error_msg or "Errno 101" in error_msg:
            error_msg = "SMTP blocked by Render. Please use SendGrid instead. Set SENDGRID_API_KEY in environment variables."
            print(f"❌ {error_msg}")
        else:
            print(f"❌ Failed to send email via SMTP: {e}")
        
        return {"success": False, "error": error_msg}


def send_reset_email_sendgrid(email: str, reset_token: str) -> dict:
    """
    Send password reset email using SendGrid API
    """
    try:
        reset_link = f"{FRONTEND_URL}/reset-password?token={reset_token}"
        
        message = Mail(
            from_email=SMTP_FROM or 'noreply@isibi.com',
            to_emails=email,
            subject='Password Reset Request - ISIBI Voice AI',
            html_content=get_reset_email_html(reset_link)
        )
        
        sg = SendGridAPIClient(SENDGRID_API_KEY)
        response = sg.send(message)
        
        print(f"✅ Password reset email sent to {email} via SendGrid")
        return {"success": True}
    
    except Exception as e:
        print(f"❌ Failed to send email via SendGrid: {e}")
        return {"success": False, "error": str(e)}


def get_reset_email_html(reset_link: str) -> str:
    """Get HTML template for reset email"""
    return f"""
<!DOCTYPE html>
<html>
<head>
    <style>
        body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
        .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
        .header {{ background: #4F46E5; color: white; padding: 20px; text-align: center; border-radius: 5px 5px 0 0; }}
        .content {{ background: #f9f9f9; padding: 30px; border-radius: 0 0 5px 5px; }}
        .button {{ display: inline-block; padding: 12px 30px; background: #4F46E5; color: white; text-decoration: none; border-radius: 5px; margin: 20px 0; }}
        .footer {{ text-align: center; margin-top: 20px; color: #666; font-size: 12px; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>Password Reset Request</h1>
        </div>
        <div class="content">
            <p>Hello,</p>
            <p>You requested to reset your password for your ISIBI Voice AI account.</p>
            <p>Click the button below to reset your password:</p>
            <p style="text-align: center;">
                <a href="{reset_link}" class="button">Reset Password</a>
            </p>
            <p>Or copy and paste this link into your browser:</p>
            <p style="word-break: break-all; color: #4F46E5;">{reset_link}</p>
            <p><strong>This link will expire in 1 hour.</strong></p>
            <p>If you didn't request this, please ignore this email. Your password will remain unchanged.</p>
            <div class="footer">
                <p>ISIBI Voice AI Platform</p>
                <p>This is an automated message, please do not reply.</p>
            </div>
        </div>
    </div>
</body>
</html>
"""


def create_password_reset_request(email: str) -> dict:
    """
    Create a password reset request
    
    Args:
        email: User's email
    
    Returns:
        {
            "success": bool,
            "message": str,
            "error": str (if failed)
        }
    """
    from db import get_conn, sql
    
    conn = get_conn()
    cur = conn.cursor()
    
    try:
        # Check if user exists
        cur.execute(sql("SELECT id, email FROM users WHERE email = {PH}"), (email,))
        user = cur.fetchone()
        
        if not user:
            # Don't reveal if email exists or not (security)
            conn.close()
            return {
                "success": True,
                "message": "If that email exists, a reset link has been sent."
            }
        
        # Generate reset token
        reset_token = generate_reset_token()
        
        # Calculate expiration (1 hour from now)
        expires_at = datetime.now() + timedelta(hours=1)
        
        # Store token in database
        from db import add_column_if_missing
        add_column_if_missing(conn, 'users', 'reset_token', 'TEXT')
        add_column_if_missing(conn, 'users', 'reset_token_expires', 'TIMESTAMP')
        
        cur.execute(sql("""
            UPDATE users
            SET reset_token = {PH},
                reset_token_expires = {PH}
            WHERE email = {PH}
        """), (reset_token, expires_at, email))
        
        conn.commit()
        conn.close()
        
        # Send email
        email_result = send_reset_email(email, reset_token)
        
        if email_result["success"]:
            return {
                "success": True,
                "message": "Password reset email sent. Check your inbox."
            }
        else:
            return {
                "success": False,
                "error": "Failed to send email. Please try again later."
            }
    
    except Exception as e:
        conn.close()
        return {"success": False, "error": str(e)}


def verify_reset_token(token: str) -> dict:
    """
    Verify if reset token is valid and not expired
    
    Args:
        token: Password reset token
    
    Returns:
        {
            "valid": bool,
            "user_id": int (if valid),
            "email": str (if valid),
            "error": str (if invalid)
        }
    """
    from db import get_conn, sql
    
    conn = get_conn()
    cur = conn.cursor()
    
    try:
        cur.execute(sql("""
            SELECT id, email, reset_token_expires
            FROM users
            WHERE reset_token = {PH}
        """), (token,))
        
        user = cur.fetchone()
        conn.close()
        
        if not user:
            return {"valid": False, "error": "Invalid token"}
        
        # Parse user data
        if isinstance(user, dict):
            user_id = user['id']
            email = user['email']
            expires_at = user['reset_token_expires']
        else:
            user_id = user[0]
            email = user[1]
            expires_at = user[2]
        
        # Check if expired
        if isinstance(expires_at, str):
            from dateutil import parser
            expires_at = parser.parse(expires_at)
        
        if datetime.now() > expires_at:
            return {"valid": False, "error": "Token expired"}
        
        return {
            "valid": True,
            "user_id": user_id,
            "email": email
        }
    
    except Exception as e:
        conn.close()
        return {"valid": False, "error": str(e)}


def reset_password_with_token(token: str, new_password: str) -> dict:
    """
    Reset password using token
    
    Args:
        token: Password reset token
        new_password: New password
    
    Returns:
        {"success": bool, "error": str (if failed)}
    """
    # Verify token
    verification = verify_reset_token(token)
    
    if not verification.get("valid"):
        return {
            "success": False,
            "error": verification.get("error", "Invalid token")
        }
    
    user_id = verification["user_id"]
    
    # Update password
    from db import get_conn, sql
    import bcrypt
    
    conn = get_conn()
    cur = conn.cursor()
    
    try:
        # Hash new password
        hashed = bcrypt.hashpw(new_password.encode('utf-8'), bcrypt.gensalt())
        
        # Update password and clear reset token
        cur.execute(sql("""
            UPDATE users
            SET password_hash = {PH},
                reset_token = NULL,
                reset_token_expires = NULL
            WHERE id = {PH}
        """), (hashed.decode('utf-8'), user_id))
        
        conn.commit()
        conn.close()
        
        print(f"✅ Password reset successful for user {user_id}")
        
        return {"success": True, "message": "Password reset successful"}
    
    except Exception as e:
        conn.close()
        return {"success": False, "error": str(e)}
