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
        # Default based on environment: localhost for dev, production URL otherwise
        import os
        if os.environ.get('FLASK_ENV') == 'development':
            default_url = 'http://localhost:3000'
        else:
            default_url = 'https://cin7-uploader-1084228140944.us-central1.run.app'
        frontend_url = current_app.config.get('FRONTEND_URL', default_url)
        
        # Create reset link
        reset_link = f"{frontend_url}/reset-password?token={reset_token}"
        
        # Create logo URL
        logo_url = f"{frontend_url}/logo.jpg"
        print(f"Logo URL for email: {logo_url}")
        
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
            text-align: left;
        }}
        .container {{
            max-width: 600px;
            margin: 0;
            margin-left: 0;
            margin-right: auto;
            padding: 15px 20px;
            background-color: #ffffff;
            text-align: left;
        }}
        .header {{
            margin-bottom: 32px;
            text-align: left;
        }}
        .logo {{
            max-width: 200px;
            height: auto;
            margin-bottom: 24px;
            display: block;
        }}
        .title {{
            font-size: 18px;
            font-weight: 600;
            color: #09090b;
            margin: 0 0 8px 0;
            letter-spacing: -0.025em;
            text-align: left;
        }}
        .subtitle {{
            font-size: 14px;
            color: #71717a;
            margin: 0;
            text-align: left;
        }}
        .content {{
            margin-bottom: 32px;
            text-align: left;
        }}
        .text {{
            font-size: 14px;
            color: #27272a;
            margin: 0 0 16px 0;
            text-align: left;
        }}
        .button-container {{
            margin: 32px 0;
            text-align: left;
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
            text-align: left;
        }}
        .caption {{
            font-size: 11px;
            color: #71717a;
            font-style: italic;
            margin: 8px 0 0 0;
            text-align: left;
        }}
    </style>
</head>
<body>
    <div class="container" style="text-align: left;">
        <div class="header" style="text-align: left;">
            <img src="{logo_url}" alt="Cin7 Uploader" class="logo" style="max-width: 200px; width: 200px; height: auto; margin-bottom: 24px; display: block; border: 0; outline: none; text-decoration: none;" />
            <h1 class="title" style="text-align: left;">Password Reset Request</h1>
            <p class="subtitle" style="text-align: left;">Cin7 Uploader</p>
        </div>
        
        <div class="content" style="text-align: left;">
            <p class="text" style="text-align: left;">You requested to reset your password. Click the button below to reset it:</p>
            
            <div class="button-container" style="text-align: left;">
                <a href="{reset_link}" class="button" style="text-align: left;">Reset Password</a>
            </div>
            
            <p class="text" style="text-align: left;">Or copy and paste this link into your browser:</p>
            <div class="link-text" style="text-align: left;">{reset_link}</div>
            
            <p class="caption" style="font-size: 11px; color: #71717a; font-style: italic; margin: 8px 0 0 0; text-align: left;">This link will expire in 1 hour.</p>
        </div>
        
        <div class="footer" style="text-align: left;">
        </div>
    </div>
</body>
</html>
"""
        
        # Plain text fallback
        text_body = f"""Password Reset Request - Cin7 Uploader

You requested to reset your password. Click the link below to reset it:

{reset_link}

This link will expire in 1 hour.
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
        error_msg = str(e)
        print(f"Error sending password reset email to {email}: {error_msg}")
        # Don't print full traceback if it's a broken pipe (common SMTP issue)
        # This prevents cascading broken pipe errors
        if 'Broken pipe' not in error_msg and 'BrokenPipeError' not in error_msg:
            try:
                import traceback
                traceback.print_exc()
            except:
                pass  # Even traceback printing can fail
        return False


