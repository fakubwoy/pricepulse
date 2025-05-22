import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from database import db
from models import PriceAlert, Product, User

# Email configuration
import os

EMAIL_CONFIG = {
    'SENDER_EMAIL': os.getenv('SENDER_EMAIL'),
    'SENDER_PASSWORD': os.getenv('SENDER_PASSWORD'),
    'SMTP_SERVER': os.getenv('SMTP_SERVER'),
    'SMTP_PORT': int(os.getenv('SMTP_PORT', 587))
}


def send_email_alert(recipient, subject, message):
    """Send an email alert using the configured email settings"""
    try:
        # Create message
        msg = MIMEMultipart()
        msg['From'] = EMAIL_CONFIG['SENDER_EMAIL']
        msg['To'] = recipient
        msg['Subject'] = subject
        
        # Attach message body
        msg.attach(MIMEText(message, 'html'))
        
        # Connect to SMTP server
        server = smtplib.SMTP(EMAIL_CONFIG['SMTP_SERVER'], EMAIL_CONFIG['SMTP_PORT'])
        server.starttls()  # Secure the connection
        server.login(EMAIL_CONFIG['SENDER_EMAIL'], EMAIL_CONFIG['SENDER_PASSWORD'])
        
        # Send email
        server.send_message(msg)
        server.quit()
        
        return True
    except Exception as e:
        print(f"Failed to send email: {str(e)}")
        return False

def check_price_alerts():
    """Check all price alerts against current prices and send notifications if needed"""
    # Get all active alerts
    alerts = PriceAlert.query.filter_by(is_active=True).all()
    
    for alert in alerts:
        product = Product.query.get(alert.product_id)
        user = User.query.get(alert.user_id)
        
        # Skip if product or user doesn't exist
        if not product or not user:
            continue
            
        # Check if current price meets or is below target price
        if product.current_price <= alert.target_price:
            # Format prices with currency
            current_price = f"{product.currency}{product.current_price:.2f}"
            target_price = f"{product.currency}{alert.target_price:.2f}"
            
            # Create email subject and body
            subject = f"Price Alert: {product.name} is now {current_price}"
            
            message = f"""
            <html>
            <body>
            <h2>PricePulse Price Alert</h2>
            <p>Good news! A product you're tracking has reached your target price.</p>
            
            <h3>{product.name}</h3>
            <p><img src="{product.image}" alt="{product.name}" style="max-width: 200px;"></p>
            <p>Current price: <strong>{current_price}</strong></p>
            <p>Your target price: {target_price}</p>
            
            <p><a href="{product.url}">View product on Amazon</a></p>
            
            <p>Thank you for using PricePulse!</p>
            </body>
            </html>
            """
            
            # Send the email
            if send_email_alert(user.email, subject, message):
                # Deactivate alert
                alert.is_active = False
                db.session.commit()