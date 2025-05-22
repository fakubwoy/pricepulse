import requests
import re
from bs4 import BeautifulSoup
from datetime import datetime
import time
import random
from models import Product, PriceHistory, PriceAlert
from database import db

class AmazonScraper:
    def __init__(self):
        # Updated headers to mimic a real browser more closely
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept-Language': 'en-US,en;q=0.9,hi;q=0.8',
            'Accept-Encoding': 'gzip, deflate, br',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
            'Cache-Control': 'max-age=0',
            'Sec-Ch-Ua': '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
            'Sec-Ch-Ua-Mobile': '?0',
            'Sec-Ch-Ua-Platform': '"Windows"',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'none',
            'Sec-Fetch-User': '?1',
            'Upgrade-Insecure-Requests': '1',
            'Connection': 'keep-alive'
        }
    
    def is_valid_amazon_url(self, url):
        """Validate if URL is an Amazon product URL"""
        # Updated pattern to be more specific for product URLs
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
            # Create clean URL with ASIN
            if 'amazon.in' in url:
                return f"https://www.amazon.in/dp/{asin}"
            elif 'amazon.com' in url:
                return f"https://www.amazon.com/dp/{asin}"
            # Add more domains as needed
        return url
    
    def scrape_product(self, url):
        """Scrape product details from Amazon URL"""
        if not self.is_valid_amazon_url(url):
            return {'error': 'Invalid Amazon URL. Please provide a valid Amazon product URL (e.g., https://www.amazon.in/dp/XXXXXXXXXX)'}
        
        # Normalize URL
        normalized_url = self.normalize_url(url)
        
        try:
            # Add a random delay to avoid being blocked
            time.sleep(random.uniform(2, 5))
            
            # Create a session to maintain cookies
            session = requests.Session()
            session.headers.update(self.headers)
            
            response = session.get(normalized_url, timeout=15)
            
            if response.status_code == 503:
                return {'error': 'Amazon is blocking requests. Please try again later or use a VPN.'}
            elif response.status_code == 404:
                return {'error': 'Product not found. Please check the URL.'}
            elif response.status_code != 200:
                return {'error': f'Failed to fetch product page: HTTP {response.status_code}'}
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Debug: Check if we got the actual product page
            if "robot" in response.text.lower() or "captcha" in response.text.lower():
                return {'error': 'Amazon is requesting CAPTCHA verification. Please try again later.'}
            
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
                return {'error': 'Could not extract product name. The page structure might have changed or access was blocked.'}
            
            return product_data
            
        except requests.exceptions.Timeout:
            return {'error': 'Request timed out. Please try again.'}
        except requests.exceptions.ConnectionError:
            return {'error': 'Connection error. Please check your internet connection.'}
        except Exception as e:
            print(f"Error scraping product: {str(e)}")
            return {'error': f'Error scraping product: {str(e)}'}
    
    def _extract_name(self, soup):
        """Extract product name with multiple selectors"""
        # Try multiple selectors for product title
        selectors = [
            '#productTitle',
            'span#productTitle',
            'h1.a-size-large.a-spacing-none.a-color-base',
            'h1[data-automation-id="product-title"]',
            '.product-title',
            'h1.it-ttl'
        ]
        
        for selector in selectors:
            name_elem = soup.select_one(selector)
            if name_elem:
                name = name_elem.get_text().strip()
                if name:
                    return name
        
        return None
    
    def _extract_image(self, soup):
        """Extract product image URL with multiple selectors"""
        # Try multiple image selectors
        selectors = [
            '#landingImage',
            '#imgBlkFront',
            '#main-image-container img',
            '.a-dynamic-image',
            'img[data-old-hires]',
            '.imgTagWrapper img'
        ]
        
        for selector in selectors:
            image = soup.select_one(selector)
            if image:
                # Try multiple attributes for image URL
                for attr in ['data-old-hires', 'src', 'data-src']:
                    img_url = image.get(attr)
                    if img_url and img_url.startswith('http'):
                        return img_url
                        
        return None
    
    def _extract_current_price(self, soup):
        """Extract current price with improved selectors"""
        # Method 1: Try the new Amazon price structure
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
            '#apex_desktop span.a-price.a-text-price.a-size-medium.apexPriceToPay .a-offscreen',
            '.a-price.a-text-price.a-size-medium.apexPriceToPay .a-offscreen'
        ]
        
        for selector in price_selectors:
            price_elem = soup.select_one(selector)
            if price_elem:
                try:
                    price_text = price_elem.get_text().strip()
                    # Extract numeric value
                    price_match = re.search(r'[\d,]+\.?\d*', price_text.replace(',', ''))
                    if price_match:
                        return float(price_match.group().replace(',', ''))
                except (ValueError, AttributeError):
                    continue
                    
        return None
    
    def _extract_original_price(self, soup):
        """Extract original/list price if available"""
        list_price_selectors = [
            '.a-text-price .a-offscreen',
            '.priceBlockStrikePriceString .a-offscreen',
            '.a-text-strike .a-offscreen',
            '.a-price.a-text-price.a-size-base .a-offscreen'
        ]
        
        for selector in list_price_selectors:
            list_price = soup.select_one(selector)
            if list_price:
                try:
                    price_text = list_price.get_text().strip()
                    price_match = re.search(r'[\d,]+\.?\d*', price_text.replace(',', ''))
                    if price_match:
                        original_price = float(price_match.group().replace(',', ''))
                        # Only return if it's higher than current price (makes sense as original price)
                        return original_price
                except (ValueError, AttributeError):
                    continue
                    
        return None
    
    def _extract_description(self, soup):
        """Extract product description with multiple methods"""
        # Try feature bullets first
        feature_bullets = soup.select('#feature-bullets ul li')
        if feature_bullets:
            bullets = []
            for bullet in feature_bullets:
                text = bullet.get_text().strip()
                if text and len(text) > 10 and not text.startswith('Make sure'):
                    bullets.append(text)
            if bullets:
                return '\n'.join(bullets[:5])  # Limit to first 5 bullets
        
        # Try product description
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
                    return desc_text[:500]  # Limit length
                    
        return None
    
    def _extract_rating(self, soup):
        """Extract product rating with multiple selectors"""
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
                        if 0 <= rating <= 5:  # Valid rating range
                            return rating
                except (ValueError, AttributeError):
                    continue
                    
        return None
    
    def _check_in_stock(self, soup):
        """Check if product is in stock"""
        # Check availability text
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
        add_to_cart_selectors = [
            '#add-to-cart-button',
            'input[name="submit.add-to-cart"]',
            '#buy-now-button'
        ]
        
        for selector in add_to_cart_selectors:
            if soup.select_one(selector):
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
                # Look for common currency symbols
                currency_match = re.search(r'([₹$£€¥])', text)
                if currency_match:
                    return currency_match.group(1)
                    
        # Default based on domain
        return "₹"  # Default for amazon.in


def update_all_products():
    """Update all products in the database"""
    scraper = AmazonScraper()
    products = Product.query.all()
    
    for product in products:
        # Skip products updated in the last hour to avoid unnecessary requests
        if product.last_updated and (datetime.utcnow() - product.last_updated).total_seconds() < 3600:
            continue
            
        print(f"Updating product: {product.name}")
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
                
            # Update additional attributes if available
            if data['original_price']:
                product.original_price = data['original_price']
            if data['currency']:
                product.currency = data['currency']
            if data['description']:
                product.description = data['description']
            if data['rating']:
                product.rating = data['rating']
            if data['in_stock'] is not None:
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