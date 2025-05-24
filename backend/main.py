from flask import Flask, jsonify, request, make_response
from flask_cors import CORS
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from apscheduler.schedulers.background import BackgroundScheduler
import os
from datetime import datetime, timedelta, timezone
import jwt
from functools import wraps
from dotenv import load_dotenv
import logging
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.executors.pool import ThreadPoolExecutor
import threading
import time
import atexit
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
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL', 'sqlite:///pricepulse.db').replace('postgres://', 'postgresql://', 1)
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY')

# Define IST timezone (UTC+5:30)
IST = timezone(timedelta(hours=5, minutes=30))

# Initialize Flask-Login
login_manager = LoginManager()
login_manager.init_app(app)
logging.basicConfig(level=logging.INFO)
scheduler_logger = logging.getLogger('apscheduler')
scheduler_logger.setLevel(logging.INFO)
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
with app.app_context():
    db.create_all()
# Import db after initialization
from database import db
def continuous_hourly_refresh():
    """Standalone function that runs continuously and refreshes all products every hour"""
    print("[HOURLY_REFRESH] Starting continuous hourly refresh service...")
    
    while True:
        try:
            # Wait for 1 hour (3600 seconds)
            time.sleep(3600)
            
            with app.app_context():
                print("[HOURLY_REFRESH] Starting hourly refresh cycle...")
                
                from scraper import AmazonScraper
                
                # Get all products from database
                all_products = Product.query.all()
                
                if not all_products:
                    print("[HOURLY_REFRESH] No products found in database")
                    continue
                    
                print(f"[HOURLY_REFRESH] Found {len(all_products)} products to refresh")
                scraper = AmazonScraper()
                
                success_count = 0
                error_count = 0
                
                for product in all_products:
                    try:
                        print(f"[HOURLY_REFRESH] Refreshing: {product.name[:50]}...")
                        
                        # Scrape current product data
                        product_data = scraper.scrape_product(product.url)
                        
                        if 'error' not in product_data:
                            # Update product data
                            if product_data.get('current_price') is not None:
                                old_price = product.current_price
                                product.current_price = product_data['current_price']
                                
                                # Update other fields if available
                                if product_data.get('name'):
                                    product.name = product_data['name']
                                if product_data.get('image'):
                                    product.image = product_data['image']
                                if product_data.get('in_stock') is not None:
                                    product.in_stock = product_data['in_stock']
                                if product_data.get('rating'):
                                    product.rating = product_data['rating']
                                    
                                product.last_updated = get_ist_time()
                                
                                # Always create a history entry, regardless of price change
                                price_history = PriceHistory(
                                    product_id=product.id,
                                    price=product_data['current_price']
                                )
                                db.session.add(price_history)
                                
                                success_count += 1
                                print(f"[HOURLY_REFRESH] ✅ Updated {product.name[:30]} - Price: {product_data['current_price']}")
                                
                                # Check alerts if price decreased
                                if old_price and product_data['current_price'] < old_price:
                                    print(f"[HOURLY_REFRESH] 📉 Price drop detected for {product.name[:30]}")
                                    # Trigger alert check in background
                                    try:
                                        check_price_alerts()
                                    except Exception as alert_error:
                                        print(f"[HOURLY_REFRESH] Alert check error: {alert_error}")
                            else:
                                print(f"[HOURLY_REFRESH] ⚠️ No price data for {product.name[:30]}")
                                error_count += 1
                        else:
                            print(f"[HOURLY_REFRESH] ❌ Error for {product.name[:30]}: {product_data['error']}")
                            error_count += 1
                            
                    except Exception as e:
                        print(f"[HOURLY_REFRESH] ❌ Exception for {product.name[:30]}: {str(e)}")
                        error_count += 1
                        
                    # Add delay between requests to avoid rate limiting
                    time.sleep(3)  # 3 second delay between each product
                
                # Commit all changes at once
                try:
                    db.session.commit()
                    print(f"[HOURLY_REFRESH] ✅ Cycle completed - Success: {success_count}, Errors: {error_count}")
                except Exception as commit_error:
                    print(f"[HOURLY_REFRESH] ❌ Database commit error: {commit_error}")
                    db.session.rollback()
                    
        except Exception as e:
            print(f"[HOURLY_REFRESH] ❌ Critical error in refresh cycle: {str(e)}")
            # Continue the loop even if there's an error
            continue

def start_hourly_refresh_service():
    """Start the hourly refresh service in a background daemon thread"""
    print("[HOURLY_REFRESH] Initializing hourly refresh service...")
    
    # Create and start the background thread
    refresh_thread = threading.Thread(
        target=continuous_hourly_refresh,
        daemon=True,  # Dies when main process dies
        name="HourlyRefreshThread"
    )
    
    try:
        refresh_thread.start()
        print("[HOURLY_REFRESH] ✅ Hourly refresh service started successfully")
        return True
    except Exception as e:
        print(f"[HOURLY_REFRESH] ❌ Failed to start hourly refresh service: {str(e)}")
        return False
# Create a scheduler for updating prices and checking alerts
# Replace the scheduler section in main.py with this:
scheduler = None

# Create a scheduler for updating prices and checking alerts
def run_with_context(func):
    """Wrapper to run scheduled jobs within Flask app context"""
    try:
        with app.app_context():
            print(f"[SCHEDULER] Running scheduled job: {func.__name__}")
            func()
            print(f"[SCHEDULER] Completed scheduled job: {func.__name__}")
    except Exception as e:
        print(f"[SCHEDULER] Error in scheduled job {func.__name__}: {str(e)}")
        import traceback
        traceback.print_exc()


def scheduled_update():
    print("[SCHEDULER] Scheduled update started...")
    try:
        update_all_products()
        print("[SCHEDULER] Scheduled update completed.")
    except Exception as e:
        print(f"[SCHEDULER] Update error: {e}")

def scheduled_alerts():
    print("[SCHEDULER] Scheduled alert check started...")
    try:
        check_price_alerts()
        print("[SCHEDULER] Scheduled alert check completed.")
    except Exception as e:
        print(f"[SCHEDULER] Alert check error: {e}")

def scheduled_daily_prices():
    print("[SCHEDULER] Scheduled daily price storage started...")
    try:
        store_daily_prices()
        print("[SCHEDULER] Scheduled daily price storage completed.")
    except Exception as e:
        print(f"[SCHEDULER] Daily prices error: {e}")

def initialize_scheduler():
    """Initialize and start the background scheduler"""
    global scheduler
    try:
        print("[SCHEDULER] Initializing scheduler...")
        
        # Configure executors
        executors = {
            'default': ThreadPoolExecutor(max_workers=3)
        }
        
        # Create scheduler with proper timezone
        scheduler = BackgroundScheduler(
            executors=executors,
            timezone='Asia/Kolkata'
        )
        
        print("[SCHEDULER] Adding jobs...")
        
        # Add jobs with lambda wrapper for Flask context
        scheduler.add_job(
            func=lambda: run_with_context(scheduled_update), 
            trigger="interval", 
            minutes=30,  
            id='update_products',
            replace_existing=True,
            max_instances=1
        )
        
        scheduler.add_job(
            func=lambda: run_with_context(scheduled_alerts), 
            trigger="interval", 
            minutes=15,
            id='check_alerts',
            replace_existing=True,
            max_instances=1
        )

        scheduler.add_job(
            func=lambda: run_with_context(scheduled_daily_prices), 
            trigger="cron", 
            hour=0, 
            minute=30,
            id='daily_prices',
            replace_existing=True,
            max_instances=1
        )
        
        # Start the scheduler
        scheduler.start()
        print("[SCHEDULER] ✅ Scheduler started successfully!")
        print(f"[SCHEDULER] Active jobs: {[job.id for job in scheduler.get_jobs()]}")
        
        # Register cleanup function
        atexit.register(lambda: scheduler.shutdown() if scheduler else None)
        
        return True
        
    except Exception as e:
        print(f"[SCHEDULER] ❌ Failed to initialize scheduler: {str(e)}")
        import traceback
        traceback.print_exc()
        return False

# Initialize the scheduler after Flask app is ready
def setup_scheduler_after_init():
    """Setup scheduler after all imports are complete"""
    try:
        # Ensure all required modules are available
        print("[SCHEDULER] Checking required modules...")
        
        # Test if functions exist
        if 'update_all_products' not in globals():
            print("[SCHEDULER] Warning: update_all_products not found")
        if 'check_price_alerts' not in globals():
            print("[SCHEDULER] Warning: check_price_alerts not found")
        if 'store_daily_prices' not in globals():
            print("[SCHEDULER] Warning: store_daily_prices not found")
            
        # Initialize scheduler
        return initialize_scheduler()
        
    except Exception as e:
        print(f"[SCHEDULER] Error in setup: {str(e)}")
        import traceback
        traceback.print_exc()
        return None

# Call this after all imports are complete
scheduler = setup_scheduler_after_init()

# Keep scheduler reference to prevent garbage collection
if scheduler:
    app.scheduler = scheduler
else:
    print("[SCHEDULER] ❌ Scheduler initialization failed - app will run without background tasks")

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = None
        
        # Check Authorization header
        if 'Authorization' in request.headers:
            auth_header = request.headers['Authorization']
            try:
                if auth_header.startswith('Bearer '):
                    token = auth_header.split(" ")[1]
                else:
                    token = auth_header  # Handle cases without "Bearer " prefix
            except IndexError:
                return jsonify({'error': 'Invalid authorization header format'}), 401
        
        # Also check for token in request body (for some frontend implementations)
        elif request.is_json and request.json and 'token' in request.json:
            token = request.json['token']
            
        if not token:
            print(f"[AUTH] No token found in request to {request.endpoint}")
            return jsonify({'error': 'Token is missing'}), 401
            
        try:
            data = jwt.decode(token, app.config['SECRET_KEY'], algorithms=["HS256"])
            current_user = User.query.get(data['user_id'])
            
            if not current_user:
                print(f"[AUTH] User not found for token: {data.get('user_id')}")
                return jsonify({'error': 'User not found'}), 401
                
        except jwt.ExpiredSignatureError:
            print("[AUTH] Token has expired")
            return jsonify({'error': 'Token has expired'}), 401
        except jwt.InvalidTokenError as e:
            print(f"[AUTH] Invalid token: {str(e)}")
            return jsonify({'error': 'Token is invalid'}), 401
        except Exception as e:
            print(f"[AUTH] Token validation error: {str(e)}")
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
@app.route('/api/scheduler/status', methods=['GET'])
@token_required
def scheduler_status(current_user):
    """Check scheduler status"""
    global scheduler
    
    if scheduler and scheduler.running:
        jobs = []
        try:
            for job in scheduler.get_jobs():
                jobs.append({
                    'id': job.id,
                    'name': job.name or job.id,
                    'next_run': job.next_run_time.isoformat() if job.next_run_time else None,
                    'trigger': str(job.trigger)
                })
        except Exception as e:
            print(f"[SCHEDULER] Error getting job info: {e}")
        
        return jsonify({
            'status': 'running',
            'jobs': jobs,
            'total_jobs': len(jobs),
            'scheduler_running': scheduler.running
        })
    else:
        return jsonify({
            'status': 'not_running',
            'jobs': [],
            'total_jobs': 0,
            'scheduler_running': False,
            'message': 'Scheduler is not running or not initialized'
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
@app.route('/api/hourly-refresh/status', methods=['GET'])
@token_required
def hourly_refresh_status(current_user):
    """Check if the hourly refresh service is running"""
    active_threads = threading.active_count()
    refresh_thread_active = any(
        thread.name == "HourlyRefreshThread" 
        for thread in threading.enumerate()
    )
    
    return jsonify({
        'service_running': refresh_thread_active,
        'active_threads': active_threads,
        'thread_names': [thread.name for thread in threading.enumerate()],
        'status': 'running' if refresh_thread_active else 'stopped'
    })
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
def start_scheduler():
    """Start scheduler in a separate thread to avoid blocking"""
    def init_in_thread():
        # Give Flask app time to fully initialize
        import time
        time.sleep(2)
        
        with app.app_context():
            success = initialize_scheduler()
            if success:
                app.scheduler = scheduler
                print("[SCHEDULER] ✅ Scheduler attached to Flask app")
            else:
                print("[SCHEDULER] ❌ Scheduler failed to start")
    
    # Start scheduler in background thread
    scheduler_thread = threading.Thread(target=init_in_thread, daemon=True)
    scheduler_thread.start()

# Start the scheduler
start_scheduler()
start_hourly_refresh_service()
if __name__ == '__main__':
    port = int(os.getenv('PORT', 5000))
    print(f"[APP] Starting Flask app on port {port}")
    print(f"[APP] Environment: {'Production' if not os.getenv('FLASK_DEBUG') else 'Development'}")
    app.run(debug=False, host='0.0.0.0', port=port, threaded=True)