import requests
import re
from bs4 import BeautifulSoup
from datetime import datetime
import time
import random
from models import Product, PriceHistory, PriceAlert
from database import db
import urllib.parse
import os

class AmazonScraper:
    def __init__(self):
        # ScrapingBee is the most reliable solution for production
        self.scrapingbee_api_key = os.getenv('SCRAPINGBEE_API_KEY')
        
        # Fallback user agents for direct requests (backup only)
        self.user_agents = [
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
            'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36'
        ]
    
    def is_valid_amazon_url(self, url):
        """Validate if URL is an Amazon product URL"""
        pattern = r'^https?://(www\.)?amazon\.(com|in|co\.uk|ca|de|fr|es|it|co\.jp)/.*/dp/[A-Z0-9]{10}'
        return bool(re.match(pattern, url))
    
    def extract_asin(self, url):
        """Extract ASIN from Amazon URL"""
        asin_match = re.search(r'/dp/([A-Z0-9]{10})', url)
        if asin_match:
            return asin_match.group(1)
        return None
    
    def normalize_url(self, url):
        """Normalize Amazon URL to standard format"""
        asin = self.extract_asin(url)
        if asin:
            if 'amazon.in' in url:
                return f"https://www.amazon.in/dp/{asin}"
            elif 'amazon.com' in url:
                return f"https://www.amazon.com/dp/{asin}"
        return url
    
    def scrape_with_scrapingbee(self, url):
        """Scrape using ScrapingBee API - Most reliable method"""
        if not self.scrapingbee_api_key:
            return None
            
        api_url = "https://app.scrapingbee.com/api/v1/"
        params = {
            'api_key': self.scrapingbee_api_key,
            'url': url,
            'render_js': 'false',  # Faster without JS rendering
            'premium_proxy': 'true',  # Use premium proxies
            'country_code': 'US',  # Use US proxies
            'wait': 2000,  # Wait 2 seconds for page load
            'wait_for': 'networkidle'  # Wait for network to be idle
        }
        
        try:
            print(f"Making ScrapingBee request to: {url}")
            response = requests.get(api_url, params=params, timeout=45)
            
            if response.status_code == 200:
                print("ScrapingBee request successful")
                return response.text
            elif response.status_code == 422:
                return {'error': 'Invalid URL or blocked by Amazon'}
            elif response.status_code == 401:
                return {'error': 'Invalid ScrapingBee API key'}
            elif response.status_code == 403:
                return {'error': 'ScrapingBee quota exceeded'}
            else:
                print(f"ScrapingBee error: HTTP {response.status_code}")
                return None
                
        except requests.exceptions.Timeout:
            return {'error': 'ScrapingBee request timed out'}
        except Exception as e:
            print(f"ScrapingBee error: {str(e)}")
            return None
    
    def scrape_product(self, url):
        """Main scraping method using ScrapingBee"""
        if not self.is_valid_amazon_url(url):
            return {'error': 'Invalid Amazon URL. Please provide a valid Amazon product URL.'}
        
        normalized_url = self.normalize_url(url)
        
        # Check if ScrapingBee API key is available
        if not self.scrapingbee_api_key:
            return {
                'error': 'ScrapingBee API key not configured. Please add SCRAPINGBEE_API_KEY to your environment variables. Sign up at scrapingbee.com for reliable Amazon scraping.'
            }
        
        # Get HTML content using ScrapingBee
        html_content = self.scrape_with_scrapingbee(normalized_url)
        
        if isinstance(html_content, dict) and 'error' in html_content:
            return html_content
        
        if not html_content:
            return {
                'error': 'Failed to fetch product page. This could be due to network issues or Amazon blocking the request.'
            }
        
        # Parse the HTML content
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # Check for blocking indicators
        content_lower = html_content.lower()
        if 'robot' in content_lower or 'captcha' in content_lower:
            return {'error': 'Amazon is requesting CAPTCHA verification. Please try again in a few minutes.'}
        
        # Extract product details
        product_data = {
            'url': normalized_url,
            'name': self._extract_name(soup),
            'image': self._extract_image(soup),
            'current_price': self._extract_current_price(soup),
            'original_price': self._extract_original_price(soup),
            'description': self._extract_description(soup),
            'rating': self._extract_rating(soup),
            'in_stock': self._check_in_stock(soup),
            'currency': self._extract_currency(soup) or "₹",
            'last_updated': datetime.utcnow()
        }
        
        # Validate that we got essential data
        if not product_data['name']:
            return {'error': 'Could not extract product information. The page structure may have changed or the product is unavailable.'}
        
        print(f"Successfully extracted product: {product_data['name']}")
        return product_data
    
    def _extract_name(self, soup):
        """Extract product name with multiple selectors"""
        selectors = [
            '#productTitle',
            'span#productTitle',
            'h1.a-size-large.a-spacing-none.a-color-base',
            'h1[data-automation-id="product-title"]',
            '.product-title',
            'h1.it-ttl',
            'h1 span',
            '.a-size-large.product-title-word-break'
        ]
        
        for selector in selectors:
            name_elem = soup.select_one(selector)
            if name_elem:
                name = name_elem.get_text().strip()
                if name and len(name) > 5:
                    return name
        
        return None
    
    def _extract_image(self, soup):
        """Extract product image URL"""
        selectors = [
            '#landingImage',
            '#imgBlkFront',
            '#main-image-container img',
            '.a-dynamic-image',
            'img[data-old-hires]',
            '.imgTagWrapper img',
            '#imageBlock img'
        ]
        
        for selector in selectors:
            image = soup.select_one(selector)
            if image:
                for attr in ['data-old-hires', 'src', 'data-src']:
                    img_url = image.get(attr)
                    if img_url and img_url.startswith('http'):
                        return img_url
        
        return None
    
    def _extract_current_price(self, soup):
        """Extract current price"""
        # Method 1: Standard price structure
        price_whole = soup.select_one('.a-price-whole')
        price_fraction = soup.select_one('.a-price-fraction')
        
        if price_whole:
            try:
                whole = price_whole.get_text().replace(',', '').replace('.', '').strip()
                fraction = price_fraction.get_text().strip() if price_fraction else '00'
                return float(f"{whole}.{fraction}")
            except (ValueError, AttributeError):
                pass
        
        # Method 2: Various price selectors
        price_selectors = [
            '.a-price .a-offscreen',
            '#priceblock_ourprice',
            '#priceblock_dealprice',
            '.a-price-current .a-offscreen',
            '.a-text-price .a-offscreen',
            '.a-price.a-text-price.a-size-medium.apexPriceToPay .a-offscreen',
            '.a-price-range .a-offscreen'
        ]
        
        for selector in price_selectors:
            price_elem = soup.select_one(selector)
            if price_elem:
                try:
                    price_text = price_elem.get_text().strip()
                    price_match = re.search(r'[\d,]+\.?\d*', price_text.replace(',', ''))
                    if price_match:
                        price = float(price_match.group().replace(',', ''))
                        if price > 0:
                            return price
                except (ValueError, AttributeError):
                    continue
        
        return None
    
    def _extract_original_price(self, soup):
        """Extract original/list price if available"""
        list_price_selectors = [
            '.a-text-price .a-offscreen',
            '.priceBlockStrikePriceString .a-offscreen',
            '.a-text-strike .a-offscreen',
            '.a-price.a-text-price.a-size-base .a-offscreen',
            '.a-price-was .a-offscreen'
        ]
        
        for selector in list_price_selectors:
            list_price = soup.select_one(selector)
            if list_price:
                try:
                    price_text = list_price.get_text().strip()
                    price_match = re.search(r'[\d,]+\.?\d*', price_text.replace(',', ''))
                    if price_match:
                        return float(price_match.group().replace(',', ''))
                except (ValueError, AttributeError):
                    continue
        
        return None
    
    def _extract_description(self, soup):
        """Extract product description"""
        feature_bullets = soup.select('#feature-bullets ul li')
        if feature_bullets:
            bullets = []
            for bullet in feature_bullets:
                text = bullet.get_text().strip()
                if text and len(text) > 10 and not text.startswith('Make sure'):
                    bullets.append(text)
            if bullets:
                return '\n'.join(bullets[:3])
        
        desc_selectors = [
            '#productDescription p',
            '#aplus_feature_div',
            '#feature-bullets'
        ]
        
        for selector in desc_selectors:
            description = soup.select_one(selector)
            if description:
                desc_text = description.get_text().strip()
                if desc_text and len(desc_text) > 20:
                    return desc_text[:300]
        
        return None
    
    def _extract_rating(self, soup):
        """Extract product rating"""
        rating_selectors = [
            'span[data-hook="rating-out-of-text"]',
            '#acrPopover .a-icon-alt',
            '.a-icon-star .a-icon-alt',
            'i[data-hook="average-star-rating"] .a-icon-alt'
        ]
        
        for selector in rating_selectors:
            rating_elem = soup.select_one(selector)
            if rating_elem:
                try:
                    rating_text = rating_elem.get_text() or rating_elem.get('title', '')
                    rating_match = re.search(r'(\d+(?:\.\d+)?)', rating_text)
                    if rating_match:
                        rating = float(rating_match.group(1))
                        if 0 <= rating <= 5:
                            return rating
                except (ValueError, AttributeError):
                    continue
        
        return None
    
    def _check_in_stock(self, soup):
        """Check if product is in stock"""
        availability_selectors = [
            '#availability span',
            '#availabilityInsideBuyBox_feature_div span',
            '.a-color-success'
        ]
        
        for selector in availability_selectors:
            availability = soup.select_one(selector)
            if availability:
                text = availability.get_text().strip().lower()
                if any(phrase in text for phrase in ['in stock', 'available', 'ships from']):
                    return True
                elif any(phrase in text for phrase in ['out of stock', 'unavailable']):
                    return False
        
        # Check for add to cart button
        if soup.select_one('#add-to-cart-button, input[name="submit.add-to-cart"]'):
            return True
        
        return False
    
    def _extract_currency(self, soup):
        """Extract currency symbol"""
        currency_selectors = [
            '.a-price-symbol',
            '.a-price .a-offscreen'
        ]
        
        for selector in currency_selectors:
            currency_elem = soup.select_one(selector)
            if currency_elem:
                text = currency_elem.get_text().strip()
                currency_match = re.search(r'([₹$£€¥])', text)
                if currency_match:
                    return currency_match.group(1)
        
        return "₹"


def update_all_products():
    """Update all products in the database"""
    scraper = AmazonScraper()
    products = Product.query.all()
    
    for product in products:
        # Skip products updated in the last 2 hours
        if product.last_updated and (datetime.utcnow() - product.last_updated).total_seconds() < 7200:
            continue
        
        print(f"Updating product: {product.name}")
        
        # Add delay between products to respect rate limits
        time.sleep(random.uniform(5, 10))
        
        data = scraper.scrape_product(product.url)
        
        if 'error' not in data:
            # Update product details
            if data['name']:
                product.name = data['name']
            if data['image']:
                product.image = data['image']
            product.last_updated = datetime.utcnow()
            
            # Update price if changed
            if data['current_price'] and data['current_price'] != product.current_price:
                old_price = product.current_price
                product.current_price = data['current_price']
                
                # Add to price history
                price_history = PriceHistory(product_id=product.id, price=data['current_price'])
                db.session.add(price_history)
                
                print(f"Price updated: {old_price} -> {data['current_price']}")
                
                # Check price alerts
                check_price_alerts(product)
            
            # Update other attributes
            for attr in ['original_price', 'currency', 'description', 'rating', 'in_stock']:
                if data.get(attr) is not None:
                    setattr(product, attr, data[attr])
        else:
            print(f"Error updating product {product.name}: {data['error']}")
    
    db.session.commit()


def check_price_alerts(product):
    """Check if any price alerts should be triggered for a product"""
    active_alerts = PriceAlert.query.filter_by(
        product_id=product.id, 
        is_active=True
    ).filter(
        PriceAlert.target_price >= product.current_price
    ).all()
    
    for alert in active_alerts:
        print(f"ALERT: Product {product.name} price dropped to {product.current_price}")
        
        # Import here to avoid circular imports
        from email_service import send_price_alert_email
        
        # Send email alert
        send_price_alert_email(alert, product)
        
        # Mark alert as inactive after triggering
        alert.is_active = False
    
    db.session.commit()