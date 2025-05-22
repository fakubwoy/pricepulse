from flask import Flask, jsonify, request, make_response
from flask_cors import CORS
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from apscheduler.schedulers.background import BackgroundScheduler
import os
from datetime import datetime, timedelta, timezone
import jwt
from functools import wraps
from dotenv import load_dotenv
load_dotenv()

# Import our modules
from database import init_db
from models import User, Product, PriceHistory, PriceAlert
from scraper import AmazonScraper, update_all_products
from email_service import check_price_alerts, send_email_alert

# Initialize Flask app
app = Flask(__name__)
CORS(app, origins=[     # Enable CORS for all routes
    "http://localhost:3000",  # Development
    "https://your-frontend-url.onrender.com"  # Production (update this after frontend deployment)
])
  
DATABASE_URL = os.getenv('DATABASE_URL')
if DATABASE_URL and DATABASE_URL.startswith('postgres://'):
    DATABASE_URL = DATABASE_URL.replace('postgres://', 'postgresql://', 1)
    
# Configure database
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///pricepulse.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY')

# Initialize Flask-Login
login_manager = LoginManager()
login_manager.init_app(app)
def get_ist_time():
    """Get current time in IST timezone"""
    return datetime.now(IST)

# Also, make sure you have these imports at the top of your main.py:
from datetime import datetime, timedelta, timezone
# Define IST timezone (UTC+5:30)
IST = timezone(timedelta(hours=5, minutes=30))

# Initialize the database
init_db(app)

# Import db after initialization
from database import db

# Create a scheduler for updating prices and checking alerts
if os.getenv('RENDER'):  # Only run scheduler on Render
    scheduler = BackgroundScheduler()
    scheduler.add_job(func=update_all_products, trigger="interval", minutes=60)
    scheduler.add_job(func=check_price_alerts, trigger="interval", minutes=15)
    scheduler.start()

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = None
        
        if 'Authorization' in request.headers:
            token = request.headers['Authorization'].split(" ")[1]
            
        if not token:
            return jsonify({'error': 'Token is missing'}), 401
            
        try:
            data = jwt.decode(token, app.config['SECRET_KEY'], algorithms=["HS256"])
            current_user = User.query.get(data['user_id'])
        except:
            return jsonify({'error': 'Token is invalid'}), 401
            
        return f(current_user, *args, **kwargs)
        
    return decorated

@app.route('/api/health', methods=['GET'])
def health_check():
    """API health check endpoint"""
    return jsonify({
        'status': 'ok',
        'timestamp': get_ist_time().isoformat()
    })

@app.route('/api/auth/register', methods=['POST'])
def register():
    """Register a new user"""
    data = request.json
    
    if not data or 'email' not in data or 'password' not in data:
        return jsonify({'error': 'Email and password are required'}), 400
        
    # Check if user already exists
    if User.query.filter_by(email=data['email']).first():
        return jsonify({'error': 'Email already registered'}), 400
        
    # Create new user
    user = User(
        email=data['email'],
        name=data.get('name', '')
    )
    user.set_password(data['password'])
    
    db.session.add(user)
    db.session.commit()
    
    # Generate token
    token = jwt.encode({
        'user_id': user.id,
        'exp': datetime.utcnow() + timedelta(days=30)
    }, app.config['SECRET_KEY'])
    
    return jsonify({
        'token': token,
        'user': user.to_dict()
    }), 201

@app.route('/api/auth/login', methods=['POST'])
def login():
    """Login a user"""
    data = request.json
    
    if not data or 'email' not in data or 'password' not in data:
        return jsonify({'error': 'Email and password are required'}), 400
        
    user = User.query.filter_by(email=data['email']).first()
    
    if not user or not user.check_password(data['password']):
        return jsonify({'error': 'Invalid email or password'}), 401
        
    # Update last login
    user.last_login = datetime.utcnow()
    db.session.commit()
    
    # Generate token
    token = jwt.encode({
        'user_id': user.id,
        'exp': datetime.utcnow() + timedelta(days=30)
    }, app.config['SECRET_KEY'])
    
    return jsonify({
        'token': token,
        'user': user.to_dict()
    })

@app.route('/api/auth/logout', methods=['POST'])
@token_required
def logout(current_user):
    """Logout a user"""
    return jsonify({'message': 'Logged out successfully'})

@app.route('/api/auth/me', methods=['GET'])
@token_required
def get_current_user(current_user):
    """Get current user info"""
    return jsonify(current_user.to_dict())

@app.route('/api/products', methods=['GET'])
@token_required
def get_products(current_user):
    """Get all tracked products for current user"""
    products = Product.query.filter_by(user_id=current_user.id).all()
    return jsonify([product.to_dict() for product in products])

@app.route('/api/products/<int:product_id>', methods=['GET'])
@token_required
def get_product(current_user, product_id):
    """Get a specific product by ID"""
    product = Product.query.filter_by(id=product_id, user_id=current_user.id).first()
    if not product:
        return jsonify({'error': 'Product not found'}), 404
        
    return jsonify(product.to_dict())

@app.route('/api/products', methods=['POST'])
@token_required
def add_product(current_user):
    """Add a new product to track"""
    data = request.json
    
    if not data or 'url' not in data:
        return jsonify({'error': 'URL is required'}), 400
        
    url = data['url']
    
    # Check if product is already being tracked by this user
    existing_product = Product.query.filter_by(url=url, user_id=current_user.id).first()
    if existing_product:
        return jsonify(existing_product.to_dict())
    
    # Scrape product details
    scraper = AmazonScraper()
    if not scraper.is_valid_amazon_url(url):
        return jsonify({'error': 'Invalid Amazon URL'}), 400
        
    product_data = scraper.scrape_product(url)
    
    if 'error' in product_data:
        return jsonify({'error': product_data['error']}), 400
        
    # Create new product
    product = Product(
        user_id=current_user.id,
        url=product_data['url'],
        name=product_data['name'],
        image=product_data['image'],
        current_price=product_data['current_price'],
        original_price=product_data['original_price'],
        currency=product_data['currency'],
        description=product_data['description'],
        rating=product_data['rating'],
        in_stock=product_data['in_stock'],
        last_updated=get_ist_time()
    )
    
    db.session.add(product)
    db.session.commit()
    
    # Add initial price history entry
    price_history = PriceHistory(
        product_id=product.id,
        price=product_data['current_price']
    )
    
    db.session.add(price_history)
    db.session.commit()
    
    return jsonify(product.to_dict()), 201

@app.route('/api/products/<int:product_id>', methods=['DELETE'])
@token_required
def delete_product(current_user, product_id):
    """Delete a product and its related data"""
    product = Product.query.filter_by(id=product_id, user_id=current_user.id).first()
    if not product:
        return jsonify({'error': 'Product not found'}), 404
        
    # Delete related price history
    PriceHistory.query.filter_by(product_id=product_id).delete()
    
    # Delete related price alerts
    PriceAlert.query.filter_by(product_id=product_id).delete()
    
    # Delete product
    db.session.delete(product)
    db.session.commit()
    
    return jsonify({'success': True, 'message': 'Product deleted'})

@app.route('/api/products/<int:product_id>/history', methods=['GET'])
@token_required
def get_price_history(current_user, product_id):
    """Get price history for a product"""
    # Check if product exists and belongs to user
    product = Product.query.filter_by(id=product_id, user_id=current_user.id).first()
    if not product:
        return jsonify({'error': 'Product not found'}), 404
    
    # Get time range parameter (default to last 30 days)
    days = request.args.get('days', 30, type=int)
    if days <= 0:
        days = 30
        
    cutoff_date = get_ist_time() - timedelta(days=days)
    
    # Query price history
    history = PriceHistory.query.filter_by(product_id=product_id).filter(
        PriceHistory.timestamp >= cutoff_date
    ).order_by(PriceHistory.timestamp).all()
    
    return jsonify([entry.to_dict() for entry in history])

@app.route('/api/products/<int:product_id>/refresh', methods=['POST'])
@token_required
def refresh_product(current_user, product_id):
    """Manually refresh product data"""
    product = Product.query.filter_by(id=product_id, user_id=current_user.id).first()
    if not product:
        return jsonify({'error': 'Product not found'}), 404
        
    scraper = AmazonScraper()
    product_data = scraper.scrape_product(product.url)
    
    if 'error' in product_data:
        return jsonify({'error': product_data['error']}), 400
        
    # Update product
    product.name = product_data['name'] or product.name
    product.image = product_data['image'] or product.image
    product.last_updated = get_ist_time()
    
    # Only add price history if price has changed
    if product_data['current_price'] and product_data['current_price'] != product.current_price:
        old_price = product.current_price
        product.current_price = product_data['current_price']
        
        # Add to price history
        price_history = PriceHistory(product_id=product.id, price=product_data['current_price'])
        db.session.add(price_history)
        
        # Check alerts immediately if price decreased
        if product_data['current_price'] < old_price:
            check_price_alerts()
    
    # Update additional attributes if available
    if product_data['original_price']:
        product.original_price = product_data['original_price']
    if product_data['currency']:
        product.currency = product_data['currency']
    if product_data['description']:
        product.description = product_data['description']
    if product_data['rating']:
        product.rating = product_data['rating']
    if product_data['in_stock'] is not None:
        product.in_stock = product_data['in_stock']
        
    db.session.commit()
    
    return jsonify(product.to_dict())

@app.route('/api/alerts', methods=['POST'])
@token_required
def create_alert(current_user):
    """Create a price alert for a product"""
    data = request.json
    
    required_fields = ['product_id', 'target_price']
    for field in required_fields:
        if field not in data:
            return jsonify({'error': f'Missing required field: {field}'}), 400
    
    # Check if product exists and belongs to user
    product = Product.query.filter_by(id=data['product_id'], user_id=current_user.id).first()
    if not product:
        return jsonify({'error': 'Product not found'}), 404
        
    # Create alert
    alert = PriceAlert(
        user_id=current_user.id,
        product_id=data['product_id'],
        target_price=data['target_price'],
        is_active=True
    )
    
    db.session.add(alert)
    db.session.commit()
    
    # Check immediately if the alert should be triggered
    if product.current_price <= alert.target_price:
        check_price_alerts()
    
    return jsonify(alert.to_dict()), 201

@app.route('/api/alerts/<int:alert_id>', methods=['DELETE'])
@token_required
def delete_alert(current_user, alert_id):
    """Delete a price alert"""
    alert = PriceAlert.query.filter_by(id=alert_id, user_id=current_user.id).first()
    if not alert:
        return jsonify({'error': 'Alert not found'}), 404
        
    db.session.delete(alert)
    db.session.commit()
    
    return jsonify({'success': True, 'message': 'Alert deleted'})

@app.route('/api/products/<int:product_id>/alerts', methods=['GET'])
@token_required
def get_product_alerts(current_user, product_id):
    """Get all alerts for a specific product"""
    # Check if product exists and belongs to user
    product = Product.query.filter_by(id=product_id, user_id=current_user.id).first()
    if not product:
        return jsonify({'error': 'Product not found'}), 404
        
    alerts = PriceAlert.query.filter_by(product_id=product_id, user_id=current_user.id).all()
    
    return jsonify([alert.to_dict() for alert in alerts])

@app.route('/api/alerts/test', methods=['POST'])
@token_required
def test_email_alert(current_user):
    """Test the email alert functionality"""
    subject = "PricePulse Test Alert"
    message = f"""
    <html>
    <body>
    <h2>PricePulse Test Alert</h2>
    <p>This is a test email to confirm that the PricePulse email alert system is working correctly.</p>
    <p>If you received this email, you're all set to receive price alerts!</p>
    </body>
    </html>
    """
    
    # Send the test email
    if send_email_alert(current_user.email, subject, message):
        return jsonify({'success': True, 'message': 'Test email sent successfully'})
    else:
        return jsonify({'error': 'Failed to send test email'}), 500

if __name__ == '__main__':
    port = int(os.getenv('PORT', 5000))
    app.run(debug=False, host='0.0.0.0', port=port)