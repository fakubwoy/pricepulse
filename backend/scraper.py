import requests
import re
from datetime import datetime, timedelta
import time
import random
import hashlib
from models import Product, PriceHistory, PriceAlert
from database import db
import os
from urllib.parse import urlparse

class AmazonScraper:
    def __init__(self):
        self.zenrows_api_key = os.getenv('ZENROWS_API_KEY')
        self.rate_limit_cache = {}
        
        # Session for direct requests (fallback)
        self.session = requests.Session()
        self.user_agents = [
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
        ]

    def is_valid_amazon_url(self, url):
        """Validate if URL is an Amazon product URL"""
        pattern = r'^https?://(www\.)?amazon\.(com|in|co\.uk|ca|de|fr|es|it|co\.jp)/.*/dp/[A-Z0-9]{10}'
        return bool(re.match(pattern, url))

    def extract_asin(self, url):
        """Extract ASIN from Amazon URL"""
        asin_match = re.search(r'/dp/([A-Z0-9]{10})', url)
        return asin_match.group(1) if asin_match else None

    def normalize_url(self, url):
        """Normalize Amazon URL to standard format"""
        asin = self.extract_asin(url)
        if not asin:
            return url
            
        domain = urlparse(url).netloc
        return f"https://{domain}/dp/{asin}"

    def scrape_with_zenrows(self, url):
        """Scrape using ZenRows API with product details endpoint"""
        if not self.zenrows_api_key or self.is_rate_limited('zenrows'):
            return None
            
        params = {
            'apikey': self.zenrows_api_key,
            'url': url,
        }
        
        try:
            print(f"Making ZenRows API request for: {url}")
            response = requests.get(
                'https://ecommerce.api.zenrows.com/v1/targets/amazon/products/',
                params=params,
                timeout=30
            )
            
            if response.status_code == 200:
                print("ZenRows request successful")
                return response.json()
            elif response.status_code == 429:
                self.set_rate_limit('zenrows', 60)
                return {'error': 'ZenRows rate limit exceeded'}
            else:
                print(f"ZenRows error: HTTP {response.status_code}")
                return {'error': f'API request failed with status {response.status_code}'}
                
        except Exception as e:
            print(f"ZenRows error: {str(e)}")
            return {'error': str(e)}

    def scrape_product(self, url):
        """Main scraping method using ZenRows API"""
        if not self.is_valid_amazon_url(url):
            return {'error': 'Invalid Amazon URL'}
            
        normalized_url = self.normalize_url(url)
        
        # First try ZenRows API
        api_result = self.scrape_with_zenrows(normalized_url)
        
        if api_result and not isinstance(api_result, dict):
            # Convert API response to our standard format
            return {
                'url': normalized_url,
                'name': api_result.get('product_name'),
                'image': api_result.get('product_images', [None])[0],
                'current_price': self._extract_price_from_api(api_result),
                'original_price': None,  # API doesn't provide original price
                'description': api_result.get('product_description'),
                'rating': api_result.get('rating_score'),
                'in_stock': api_result.get('is_available', False),
                'currency': self._determine_currency(url),
                'last_updated': datetime.utcnow()
            }
        elif isinstance(api_result, dict) and 'error' in api_result:
            return api_result
        
        # Fallback to direct scraping if API fails
        return self._fallback_scrape(normalized_url)

    def _extract_price_from_api(self, api_data):
        """Extract price from API response"""
        # The API response doesn't include price directly in the example,
        # but we can implement this if the actual API returns price data
        return None  # Placeholder - implement based on actual API response

    def _determine_currency(self, url):
        """Determine currency based on Amazon domain"""
        domain = urlparse(url).netloc
        if 'amazon.in' in domain:
            return '₹'
        elif 'amazon.co.uk' in domain:
            return '£'
        elif 'amazon.co.jp' in domain:
            return '¥'
        return '$'  # Default to USD

    def _fallback_scrape(self, url):
        """Fallback scraping method when API fails"""
        # Implement your existing BeautifulSoup scraping logic here
        # This serves as a backup if the API fails
        pass

    def is_rate_limited(self, service_name):
        """Check if we're currently rate limited"""
        return service_name in self.rate_limit_cache and \
               datetime.utcnow() < self.rate_limit_cache[service_name]

    def set_rate_limit(self, service_name, minutes=30):
        """Set rate limit timeout"""
        self.rate_limit_cache[service_name] = datetime.utcnow() + timedelta(minutes=minutes)


def update_all_products():
    """Update all products in the database"""
    scraper = AmazonScraper()
    products = Product.query.all()
    
    for product in products:
        # Skip recently updated products
        if product.last_updated and (datetime.utcnow() - product.last_updated).total_seconds() < 14400:
            continue
            
        print(f"Updating product: {product.name}")
        
        # Add delay between requests
        time.sleep(random.uniform(5, 15))
        
        data = scraper.scrape_product(product.url)
        
        if 'error' not in data:
            # Update product details
            product.name = data.get('name', product.name)
            product.image = data.get('image', product.image)
            product.last_updated = datetime.utcnow()
            
            # Update price if available
            if data.get('current_price') and data['current_price'] != product.current_price:
                product.current_price = data['current_price']
                price_history = PriceHistory(product_id=product.id, price=data['current_price'])
                db.session.add(price_history)
                
            # Update other fields
            for attr in ['original_price', 'currency', 'description', 'rating', 'in_stock']:
                if data.get(attr) is not None:
                    setattr(product, attr, data[attr])
            
            db.session.commit()
            print(f"Updated product: {product.name}")
        else:
            print(f"Error updating {product.name}: {data['error']}")

def check_price_alerts(product):
    """Check price alerts for a product"""
    active_alerts = PriceAlert.query.filter_by(
        product_id=product.id, 
        is_active=True
    ).filter(
        PriceAlert.target_price >= product.current_price
    ).all()
    
    for alert in active_alerts:
        print(f"Price alert triggered for {product.name}")
        
        # Mark alert as inactive
        alert.is_active = False
        db.session.commit()
        
        # Send email notification
        try:
            from email_service import send_price_alert_email
            send_price_alert_email(alert, product)
        except ImportError:
            print("Email service not available")