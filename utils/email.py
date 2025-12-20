"""Email utility functions for sending emails"""
from flask import current_app
from flask_mail import Message
from extensions import mail

def send_password_reset_email(email, reset_token):
    """
    Send password reset email to user
    
    Args:
        email: User's email address
        reset_token: Password reset token to include in the link
    
    Returns:
        bool: True if email was sent successfully, False otherwise
    """
    try:
        # Get frontend URL from config
        frontend_url = current_app.config.get('FRONTEND_URL', 'http://localhost:3000')
        
        # Create reset link
        reset_link = f"{frontend_url}/reset-password?token={reset_token}"
        
        # Get sender from config
        sender = current_app.config.get('MAIL_DEFAULT_SENDER') or current_app.config.get('MAIL_USERNAME')
        if not sender:
            raise ValueError("MAIL_DEFAULT_SENDER or MAIL_USERNAME must be configured")
        
        # Create HTML email with shadcn-style fonts and clickable link
        html_body = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
            line-height: 1.6;
            color: #09090b;
            background-color: #ffffff;
            margin: 0;
            padding: 0;
        }}
        .container {{
            max-width: 600px;
            margin: 0 auto;
            padding: 40px 20px;
            background-color: #ffffff;
        }}
        .header {{
            margin-bottom: 32px;
        }}
        .title {{
            font-size: 24px;
            font-weight: 600;
            color: #09090b;
            margin: 0 0 8px 0;
            letter-spacing: -0.025em;
        }}
        .subtitle {{
            font-size: 14px;
            color: #71717a;
            margin: 0;
        }}
        .content {{
            margin-bottom: 32px;
        }}
        .text {{
            font-size: 14px;
            color: #27272a;
            margin: 0 0 16px 0;
        }}
        .button-container {{
            margin: 32px 0;
        }}
        .button {{
            display: inline-block;
            padding: 10px 20px;
            background-color: #09090b;
            color: #ffffff;
            text-decoration: none;
            border-radius: 6px;
            font-size: 14px;
            font-weight: 500;
            line-height: 1.5;
            transition: background-color 0.2s;
        }}
        .button:hover {{
            background-color: #18181b;
        }}
        .link {{
            color: #09090b;
            text-decoration: underline;
            text-decoration-color: #71717a;
            text-underline-offset: 2px;
        }}
        .link:hover {{
            color: #18181b;
        }}
        .footer {{
            margin-top: 32px;
            padding-top: 24px;
            border-top: 1px solid #e4e4e7;
        }}
        .footer-text {{
            font-size: 12px;
            color: #71717a;
            margin: 0;
        }}
        .link-text {{
            font-size: 12px;
            color: #71717a;
            word-break: break-all;
            font-family: ui-monospace, SFMono-Regular, "SF Mono", Menlo, Consolas, "Liberation Mono", monospace;
            background-color: #fafafa;
            padding: 8px;
            border-radius: 4px;
            margin-top: 16px;
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1 class="title">Password Reset Request</h1>
            <p class="subtitle">Cin7 Uploader</p>
        </div>
        
        <div class="content">
            <p class="text">You requested to reset your password. Click the button below to reset it:</p>
            
            <div class="button-container">
                <a href="{reset_link}" class="button">Reset Password</a>
            </div>
            
            <p class="text">Or copy and paste this link into your browser:</p>
            <div class="link-text">{reset_link}</div>
        </div>
        
        <div class="footer">
            <p class="footer-text">This link will expire in 1 hour. If you didn't request this, please ignore this email.</p>
        </div>
    </div>
</body>
</html>
"""
        
        # Plain text fallback
        text_body = f"""Password Reset Request - Cin7 Uploader

You requested to reset your password. Click the link below to reset it:

{reset_link}

This link will expire in 1 hour. If you didn't request this, please ignore this email.
"""
        
        msg = Message(
            subject='Reset Your Password - Cin7 Uploader',
            sender=sender,
            recipients=[email],
            html=html_body,
            body=text_body
        )
        
        # Send email
        mail.send(msg)
        print(f"Password reset email sent to {email}")
        return True
        
    except Exception as e:
        print(f"Error sending password reset email to {email}: {str(e)}")
        import traceback
        traceback.print_exc()
        return False


