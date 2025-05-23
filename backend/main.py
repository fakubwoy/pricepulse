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
from llm_service import LLMService, MultiPlatformSearcher
from database import init_db
from models import User, Product, PriceHistory, PriceAlert
from scraper import AmazonScraper, update_all_products,store_daily_prices
from email_service import check_price_alerts, send_email_alert

# Initialize Flask app
app = Flask(__name__)
CORS(app, origins=[
    "http://localhost:3000",  # Development 
    "https://pricepulse-frontend.onrender.com"  # If this is your URL
], supports_credentials=True)
  
DATABASE_URL = os.getenv('DATABASE_URL')
if DATABASE_URL and DATABASE_URL.startswith('postgres://'):
    DATABASE_URL = DATABASE_URL.replace('postgres://', 'postgresql://', 1)
    
# Configure database
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///pricepulse.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY')

# Define IST timezone (UTC+5:30)
IST = timezone(timedelta(hours=5, minutes=30))

# Initialize Flask-Login
login_manager = LoginManager()
login_manager.init_app(app)

def get_ist_time():
    """Get current time in IST timezone"""
    return datetime.now(IST)

def make_timezone_aware(dt, tz=IST):
    """Convert a naive datetime to timezone-aware datetime"""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=tz)
    return dt

def safe_datetime_subtract(dt1, dt2):
    """Safely subtract two datetimes, handling timezone awareness"""
    if dt1 is None or dt2 is None:
        return None
    
    # Make both datetimes timezone-aware if they aren't already
    if dt1.tzinfo is None:
        dt1 = make_timezone_aware(dt1)
    if dt2.tzinfo is None:
        dt2 = make_timezone_aware(dt2)
    
    return dt1 - dt2

# Initialize the database
init_db(app)

# Import db after initialization
from database import db

# Create a scheduler for updating prices and checking alerts
# Replace the scheduler section in main.py with this:
if os.getenv('RENDER'):  # Only run scheduler on Render
    def run_with_context(func):
        """Wrapper to run scheduled jobs within Flask app context"""
        with app.app_context():
            func()
    
    scheduler = BackgroundScheduler()
    scheduler.add_job(func=lambda: run_with_context(update_all_products), trigger="interval", minutes=2)
    scheduler.add_job(func=lambda: run_with_context(check_price_alerts), trigger="interval", minutes=15)
    scheduler.add_job(
        func=lambda: run_with_context(store_daily_prices), 
        trigger="cron", 
        hour=0, 
        minute=30  # Run at 12:30 AM IST daily
    )
    scheduler.start()

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = None
        
        if 'Authorization' in request.headers:
            auth_header = request.headers['Authorization']
            try:
                token = auth_header.split(" ")[1]  # Bearer <token>
            except IndexError:
                return jsonify({'error': 'Invalid authorization header format'}), 401
            
        if not token:
            return jsonify({'error': 'Token is missing'}), 401
            
        try:
            data = jwt.decode(token, app.config['SECRET_KEY'], algorithms=["HS256"])
            current_user = User.query.get(data['user_id'])
            
            # Check if user exists
            if not current_user:
                return jsonify({'error': 'User not found'}), 401
                
        except jwt.ExpiredSignatureError:
            return jsonify({'error': 'Token has expired'}), 401
        except jwt.InvalidTokenError:
            return jsonify({'error': 'Token is invalid'}), 401
        except Exception as e:
            print(f"Token validation error: {str(e)}")
            return jsonify({'error': 'Token validation failed'}), 401
            
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
    """Add a new product to track with enhanced error handling"""
    data = request.json
    
    if not data or 'url' not in data:
        return jsonify({'error': 'URL is required'}), 400
        
    url = data['url'].strip()
    
    if not url:
        return jsonify({'error': 'URL cannot be empty'}), 400
    
    # Check if product is already being tracked by this user
    existing_product = Product.query.filter_by(url=url, user_id=current_user.id).first()
    if existing_product:
        return jsonify(existing_product.to_dict())
    
    # Scrape product details with enhanced error handling
    scraper = AmazonScraper()
    
    # Validate URL first
    if not scraper.is_valid_amazon_url(url):
        return jsonify({
            'error': 'Invalid Amazon URL. Please provide a valid Amazon product URL (e.g., https://www.amazon.in/dp/XXXXXXXXXX)'
        }), 400
    
    try:
        product_data = scraper.scrape_product(url)
        
        if 'error' in product_data:
            # Log the error for debugging
            print(f"Scraping error for URL {url}: {product_data['error']}")
            
            # Provide specific error messages based on the error type
            error_msg = product_data['error']
            
            if 'captcha' in error_msg.lower() or 'robot' in error_msg.lower():
                return jsonify({
                    'error': 'Amazon is currently blocking automated requests. This can happen due to high traffic or security measures. Please try again in a few minutes, or try using a different network/VPN.'
                }), 429
            elif 'not found' in error_msg.lower():
                return jsonify({
                    'error': 'Product not found. Please check if the URL is correct and the product is still available on Amazon.'
                }), 404
            elif 'timeout' in error_msg.lower():
                return jsonify({
                    'error': 'Request timed out. Please try again in a moment.'
                }), 408
            else:
                return jsonify({
                    'error': f'Unable to fetch product information: {error_msg}'
                }), 400
        
        # Validate essential product data
        if not product_data.get('name'):
            return jsonify({
                'error': 'Could not extract product information. The product page may be unavailable or blocked.'
            }), 400
        
        if not product_data.get('current_price'):
            # Still create the product but warn about missing price
            product_data['current_price'] = 0.0
            print(f"Warning: No price found for product {product_data['name']}")
        
        # Create new product
        product = Product(
            user_id=current_user.id,
            url=product_data['url'],
            name=product_data['name'],
            image=product_data.get('image'),
            current_price=product_data['current_price'],
            original_price=product_data.get('original_price'),
            currency=product_data.get('currency', '₹'),
            description=product_data.get('description'),
            rating=product_data.get('rating'),
            in_stock=product_data.get('in_stock', True),
            last_updated=get_ist_time()
        )
        
        db.session.add(product)
        db.session.commit()
        
        # Add initial price history entry only if we have a valid price
        if product_data['current_price'] > 0:
            price_history = PriceHistory(
                product_id=product.id,
                price=product_data['current_price']
            )
            db.session.add(price_history)
            db.session.commit()
        
        return jsonify(product.to_dict()), 201
        
    except Exception as e:
        # Log the full error for debugging
        print(f"Unexpected error while adding product {url}: {str(e)}")
        db.session.rollback()
        
        return jsonify({
            'error': 'An unexpected error occurred while processing your request. Please try again later.'
        }), 500

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
    """Manually refresh product data with enhanced error handling"""
    product = Product.query.filter_by(id=product_id, user_id=current_user.id).first()
    if not product:
        return jsonify({'error': 'Product not found'}), 404
    
    # Check if product was recently updated to avoid spam
    if product.last_updated:
        # Convert both to timezone-aware datetimes for comparison
        current_time = get_ist_time()
        last_updated = make_timezone_aware(product.last_updated)
        time_diff = current_time - last_updated
        
        # Only block if updated within last 2 minutes (reduced from 5 minutes)
        if time_diff.total_seconds() < 60:  
            return jsonify({
                'error': 'Product was recently updated. Please wait a moment before refreshing again.',
                'last_updated': last_updated.isoformat(),
                'retry_after_seconds': int(60 - time_diff.total_seconds())
            }), 429
    
    scraper = AmazonScraper()
    
    try:
        product_data = scraper.scrape_product(product.url)
        
        if 'error' in product_data:
            # Log the error
            print(f"Refresh error for product {product.name}: {product_data['error']}")
            
            # Update last_updated even if scraping failed to prevent spam
            product.last_updated = get_ist_time()
            db.session.commit()
            
            # Return specific error messages
            error_msg = product_data['error']
            if 'captcha' in error_msg.lower() or 'robot' in error_msg.lower():
                return jsonify({
                    'error': 'Amazon is currently blocking requests. Please try again later or use a VPN.',
                    'details': error_msg
                }), 503  # Service Unavailable instead of 400
            elif 'not found' in error_msg.lower() or '404' in error_msg:
                return jsonify({
                    'error': 'Product page not found. The product may have been removed or the URL is invalid.',
                    'details': error_msg
                }), 404
            elif 'timeout' in error_msg.lower():
                return jsonify({
                    'error': 'Request timed out. Please try again in a moment.',
                    'details': error_msg
                }), 408
            else:
                return jsonify({
                    'error': 'Unable to refresh product data at this time.',
                    'details': error_msg
                }), 503  # Changed from 400 to 503
        
        # Update product with new data
        updated = False
        
        if product_data.get('name') and product_data['name'] != product.name:
            product.name = product_data['name']
            updated = True
            
        if product_data.get('image') and product_data['image'] != product.image:
            product.image = product_data['image']
            updated = True
        
        # Update last_updated timestamp
        product.last_updated = get_ist_time()
        
        # Handle price update
        if product_data.get('current_price') is not None and product_data['current_price'] != product.current_price:
            old_price = product.current_price
            product.current_price = product_data['current_price']
            updated = True
            
            # Check alerts immediately if price decreased
            if old_price and product_data['current_price'] < old_price:
                check_price_alerts()

        # Add price history entry for every refresh if price is valid
        current_price = product_data.get('current_price')
        if current_price is not None and current_price > 0:
            price_history = PriceHistory(
                product_id=product.id,
                price=current_price
            )
            db.session.add(price_history)
            print(f"Added price entry for refresh: {current_price}")

        
        # Update additional attributes if available
        if product_data.get('original_price'):
            product.original_price = product_data['original_price']
            updated = True
            
        if product_data.get('currency'):
            product.currency = product_data['currency']
            updated = True
            
        if product_data.get('description'):
            product.description = product_data['description']
            updated = True
            
        if product_data.get('rating'):
            product.rating = product_data['rating']
            updated = True
            
        if product_data.get('in_stock') is not None:
            product.in_stock = product_data['in_stock']
            updated = True
        
        db.session.commit()
        
        response_data = product.to_dict()
        if updated:
            response_data['message'] = 'Product updated successfully'
        else:
            response_data['message'] = 'Product is already up to date'
            
        return jsonify(response_data)
        
    except Exception as e:
        print(f"Unexpected error refreshing product {product.name}: {str(e)}")
        db.session.rollback()
        
        # Still update the timestamp to prevent spam
        try:
            product.last_updated = get_ist_time()
            db.session.commit()
        except:
            pass
            
        return jsonify({
            'error': 'An unexpected error occurred while refreshing the product. Please try again later.',
            'details': str(e)
        }), 500
# Add these endpoints to main.py

@app.route('/api/products/<int:product_id>/alternatives', methods=['GET'])
@token_required
def get_product_alternatives(current_user, product_id):
    """Get alternative products from other platforms using LLM"""
    # Check if product exists and belongs to user
    product = Product.query.filter_by(id=product_id, user_id=current_user.id).first()
    if not product:
        return jsonify({'error': 'Product not found'}), 404
    
    try:
        # Initialize LLM service
        llm_service = LLMService()
        
        # Extract metadata from product
        metadata = llm_service.extract_product_metadata(
            product.name, 
            product.description or ""
        )
        
        # Search across platforms
        searcher = MultiPlatformSearcher()
        alternatives = searcher.search_across_platforms(metadata, product.name)
        
        return jsonify({
            'metadata': metadata,
            'alternatives': alternatives,
            'total_found': len(alternatives)
        })
        
    except Exception as e:
        print(f"Error finding alternatives: {e}")
        return jsonify({'error': 'Failed to find alternatives'}), 500

@app.route('/api/products/<int:product_id>/compare', methods=['GET'])
@token_required
def compare_product_prices(current_user, product_id):
    """Compare product prices across platforms"""
    # Check if product exists and belongs to user
    product = Product.query.filter_by(id=product_id, user_id=current_user.id).first()
    if not product:
        return jsonify({'error': 'Product not found'}), 404
    
    try:
        # Get alternatives
        llm_service = LLMService()
        metadata = llm_service.extract_product_metadata(product.name, product.description or "")
        
        searcher = MultiPlatformSearcher()
        alternatives = searcher.search_across_platforms(metadata, product.name)
        
        # Create comparison data
        comparison = {
            'primary_product': {
                'platform': 'Amazon',
                'name': product.name,
                'price': product.current_price,
                'currency': product.currency,
                'url': product.url,
                'image': product.image
            },
            'alternatives': alternatives,
            'cheapest': None,
            'savings': 0
        }
        
        # Find cheapest alternative
        if alternatives:
            cheapest = min(alternatives, key=lambda x: x.get('price', float('inf')))
            if cheapest['price'] < product.current_price:
                comparison['cheapest'] = cheapest
                comparison['savings'] = product.current_price - cheapest['price']
        
        return jsonify(comparison)
        
    except Exception as e:
        print(f"Error comparing prices: {e}")
        return jsonify({'error': 'Failed to compare prices'}), 500

@app.route('/api/llm/test', methods=['POST'])
@token_required
def test_llm_service(current_user):
    """Test the LLM service with a sample product"""
    try:
        data = request.json
        product_name = data.get('product_name', 'Samsung Galaxy M14')
        
        llm_service = LLMService()
        metadata = llm_service.extract_product_metadata(product_name)
        
        return jsonify({
            'status': 'success',
            'product_name': product_name,
            'extracted_metadata': metadata
        })
        
    except Exception as e:
        return jsonify({
            'status': 'error',
            'error': str(e)
        }), 500
@app.route('/api/scraper/status', methods=['GET'])
@token_required
def scraper_status(current_user):
    """Check if the scraper is working properly"""
    try:
        scraper = AmazonScraper()
        
        # Test with a known Amazon URL (replace with a real one)
        test_url = "https://www.amazon.in/dp/B08N5WRWNW"  # Example URL - replace with valid one
        
        if scraper.is_valid_amazon_url(test_url):
            return jsonify({
                'status': 'operational',
                'message': 'Scraper is configured properly',
                'timestamp': get_ist_time().isoformat()
            })
        else:
            return jsonify({
                'status': 'error',
                'message': 'URL validation failed',
                'timestamp': get_ist_time().isoformat()
            }), 500
            
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': f'Scraper error: {str(e)}',
            'timestamp': get_ist_time().isoformat()
        }), 500

# Add rate limiting information endpoint
@app.route('/api/rate-limit/info', methods=['GET'])
@token_required
def rate_limit_info(current_user):
    """Get rate limiting information for the user"""
    # Count recent product additions and refreshes
    recent_additions = Product.query.filter_by(user_id=current_user.id).filter(
        Product.created_at >= get_ist_time() - timedelta(hours=1)
    ).count()
    
    recent_updates = Product.query.filter_by(user_id=current_user.id).filter(
        Product.last_updated >= get_ist_time() - timedelta(minutes=30)
    ).count()
    
    return jsonify({
        'user_id': current_user.id,
        'recent_additions_last_hour': recent_additions,
        'recent_updates_last_30min': recent_updates,
        'recommendations': {
            'wait_between_requests': '2-5 minutes',
            'daily_limit_suggestion': '10-20 products',
            'use_vpn_if_blocked': True
        }
    })
    
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