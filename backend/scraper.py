import requests
import re
from bs4 import BeautifulSoup
from datetime import datetime
import time
import random
from models import Product, PriceHistory, PriceAlert
from database import db
import urllib.parse

class AmazonScraper:
    def __init__(self):
        # Rotate between multiple user agents
        self.user_agents = [
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:122.0) Gecko/20100101 Firefox/122.0',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:122.0) Gecko/20100101 Firefox/122.0',
            'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36'
        ]
        
        # List of proxy services (you'd need to implement actual proxy rotation)
        self.proxies = []  # Add your proxy list here if available
        
    def get_headers(self):
        """Get randomized headers to avoid detection"""
        return {
            'User-Agent': random.choice(self.user_agents),
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate, br',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'none',
            'Sec-Fetch-User': '?1',
            'Cache-Control': 'max-age=0',
            'DNT': '1',
            'Sec-GPC': '1'
        }
    
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
    
    def make_request_with_retry(self, url, max_retries=3):
        """Make request with retry logic and anti-detection measures"""
        session = requests.Session()
        
        for attempt in range(max_retries):
            try:
                # Random delay between requests
                if attempt > 0:
                    delay = random.uniform(5, 15) * (attempt + 1)
                    print(f"Retrying in {delay:.1f} seconds...")
                    time.sleep(delay)
                else:
                    time.sleep(random.uniform(2, 5))
                
                # Get fresh headers for each attempt
                headers = self.get_headers()
                session.headers.update(headers)
                
                # Make request with timeout
                response = session.get(url, timeout=20)
                
                # Check response
                if response.status_code == 200:
                    # Check if we got blocked
                    content_lower = response.text.lower()
                    if any(keyword in content_lower for keyword in ['robot', 'captcha', 'blocked', 'access denied']):
                        print(f"Attempt {attempt + 1}: Detected blocking, retrying...")
                        continue
                    return response
                elif response.status_code == 503:
                    print(f"Attempt {attempt + 1}: Service unavailable (503)")
                    continue
                elif response.status_code == 429:
                    print(f"Attempt {attempt + 1}: Rate limited (429)")
                    continue
                else:
                    print(f"Attempt {attempt + 1}: HTTP {response.status_code}")
                    if attempt == max_retries - 1:
                        return response
                        
            except requests.exceptions.Timeout:
                print(f"Attempt {attempt + 1}: Request timed out")
            except requests.exceptions.ConnectionError:
                print(f"Attempt {attempt + 1}: Connection error")
            except Exception as e:
                print(f"Attempt {attempt + 1}: Unexpected error: {str(e)}")
        
        return None
    
    def scrape_product(self, url):
        """Scrape product details from Amazon URL with enhanced anti-detection"""
        if not self.is_valid_amazon_url(url):
            return {'error': 'Invalid Amazon URL. Please provide a valid Amazon product URL.'}
        
        normalized_url = self.normalize_url(url)
        
        # Make request with retry logic
        response = self.make_request_with_retry(normalized_url)
        
        if not response:
            return {'error': 'Failed to fetch product page after multiple attempts. Amazon may be blocking requests.'}
        
        if response.status_code == 404:
            return {'error': 'Product not found. Please check the URL.'}
        elif response.status_code != 200:
            return {'error': f'Failed to fetch product page: HTTP {response.status_code}'}
        
        # Check for blocking indicators
        content_lower = response.text.lower()
        if 'robot' in content_lower or 'captcha' in content_lower:
            return {'error': 'Amazon is requesting CAPTCHA verification. This may be due to too many requests. Please try again later or consider using a VPN.'}
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
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
            return {'error': 'Could not extract product information. The page structure may have changed or access was restricted.'}
        
        # If no price found, try alternative methods
        if not product_data['current_price']:
            product_data['current_price'] = self._extract_price_alternative(soup)
        
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
                if name and len(name) > 5:  # Ensure it's a meaningful title
                    return name
        
        return None
    
    def _extract_image(self, soup):
        """Extract product image URL with multiple selectors"""
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
                for attr in ['data-old-hires', 'src', 'data-src', 'data-a-dynamic-image']:
                    img_url = image.get(attr)
                    if img_url and img_url.startswith('http'):
                        return img_url
        
        return None
    
    def _extract_current_price(self, soup):
        """Extract current price with improved selectors"""
        # Method 1: Try the standard price structure
        price_whole = soup.select_one('.a-price-whole')
        price_fraction = soup.select_one('.a-price-fraction')
        
        if price_whole:
            try:
                whole = price_whole.get_text().replace(',', '').replace('.', '').strip()
                fraction = price_fraction.get_text().strip() if price_fraction else '00'
                return float(f"{whole}.{fraction}")
            except (ValueError, AttributeError):
                pass
        
        # Method 2: Try various price selectors
        price_selectors = [
            '.a-price .a-offscreen',
            '#priceblock_ourprice',
            '#priceblock_dealprice',
            '.a-price-current .a-offscreen',
            '.a-text-price .a-offscreen',
            '.a-price.a-text-price.a-size-medium.apexPriceToPay .a-offscreen',
            '.a-price-range .a-offscreen',
            'span.a-price-symbol + span.a-price-whole',
            '.a-color-price'
        ]
        
        for selector in price_selectors:
            price_elem = soup.select_one(selector)
            if price_elem:
                try:
                    price_text = price_elem.get_text().strip()
                    price_match = re.search(r'[\d,]+\.?\d*', price_text.replace(',', ''))
                    if price_match:
                        price = float(price_match.group().replace(',', ''))
                        if price > 0:  # Ensure valid price
                            return price
                except (ValueError, AttributeError):
                    continue
        
        return None
    
    def _extract_price_alternative(self, soup):
        """Alternative price extraction method"""
        # Look for price in script tags or data attributes
        scripts = soup.find_all('script')
        for script in scripts:
            if script.string:
                # Look for price in JSON data
                price_matches = re.findall(r'"price"[:\s]*"?([0-9,]+\.?[0-9]*)"?', script.string)
                if price_matches:
                    try:
                        return float(price_matches[0].replace(',', ''))
                    except ValueError:
                        continue
        
        # Look in meta tags
        price_meta = soup.find('meta', {'property': 'product:price:amount'})
        if price_meta and price_meta.get('content'):
            try:
                return float(price_meta['content'])
            except ValueError:
                pass
        
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
        # Try feature bullets first
        feature_bullets = soup.select('#feature-bullets ul li')
        if feature_bullets:
            bullets = []
            for bullet in feature_bullets:
                text = bullet.get_text().strip()
                if text and len(text) > 10 and not text.startswith('Make sure'):
                    bullets.append(text)
            if bullets:
                return '\n'.join(bullets[:3])  # Limit to first 3 bullets
        
        desc_selectors = [
            '#productDescription p',
            '#aplus_feature_div',
            '#feature-bullets',
            '.a-unordered-list.a-nostyle.a-vertical.a-spacing-none'
        ]
        
        for selector in desc_selectors:
            description = soup.select_one(selector)
            if description:
                desc_text = description.get_text().strip()
                if desc_text and len(desc_text) > 20:
                    return desc_text[:300]  # Limit length
        
        return None
    
    def _extract_rating(self, soup):
        """Extract product rating"""
        rating_selectors = [
            'span[data-hook="rating-out-of-text"]',
            '#acrPopover .a-icon-alt',
            '.a-icon-star .a-icon-alt',
            'i[data-hook="average-star-rating"] .a-icon-alt',
            '.a-icon-star-small .a-icon-alt'
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
            '.a-color-success',
            '.a-color-price'
        ]
        
        for selector in availability_selectors:
            availability = soup.select_one(selector)
            if availability:
                text = availability.get_text().strip().lower()
                if any(phrase in text for phrase in ['in stock', 'available', 'ships from']):
                    return True
                elif any(phrase in text for phrase in ['out of stock', 'unavailable', 'currently unavailable']):
                    return False
        
        # Check for add to cart button
        if soup.select_one('#add-to-cart-button, input[name="submit.add-to-cart"], #buy-now-button'):
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
        
        return "₹"  # Default


def update_all_products():
    """Update all products in the database with enhanced error handling"""
    scraper = AmazonScraper()
    products = Product.query.all()
    
    for product in products:
        # Skip products updated in the last 2 hours to reduce requests
        if product.last_updated and (datetime.utcnow() - product.last_updated).total_seconds() < 7200:
            continue
        
        print(f"Updating product: {product.name}")
        
        # Add delay between products to avoid rate limiting
        time.sleep(random.uniform(3, 8))
        
        data = scraper.scrape_product(product.url)
        
        if 'error' not in data:
            # Update product details
            if data['name']:
                product.name = data['name']
            if data['image']:
                product.image = data['image']
            product.last_updated = datetime.utcnow()
            
            # Only add price history if price has changed
            if data['current_price'] and data['current_price'] != product.current_price:
                old_price = product.current_price
                product.current_price = data['current_price']
                
                # Add to price history
                price_history = PriceHistory(product_id=product.id, price=data['current_price'])
                db.session.add(price_history)
                
                print(f"Price updated: {old_price} -> {data['current_price']}")
                
                # Check if any price alerts should be triggered
                check_price_alerts(product)
            
            # Update additional attributes
            if data.get('original_price'):
                product.original_price = data['original_price']
            if data.get('currency'):
                product.currency = data['currency']
            if data.get('description'):
                product.description = data['description']
            if data.get('rating'):
                product.rating = data['rating']
            if data.get('in_stock') is not None:
                product.in_stock = data['in_stock']
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
        print(f"ALERT: Product {product.name} price dropped to {product.current_price}, "
              f"below target of {alert.target_price}")
        
        # Import here to avoid circular imports
        from email_service import send_price_alert_email
        
        # Send email alert
        send_price_alert_email(alert, product)
        
        # Mark alert as inactive after triggering
        alert.is_active = False
    
    db.session.commit()