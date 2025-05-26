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
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/90.0.4430.212 Safari/537.36',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate, br',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8'
        }
    
    def is_valid_amazon_url(self, url):
        """Validate if URL is an Amazon product URL"""
        pattern = r'^https?://(www\.)?amazon\.(com|in|co\.uk|ca|de|fr|es|it|co\.jp)/.*'
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
            return {'error': 'Invalid Amazon URL'}
        
        # Normalize URL
        normalized_url = self.normalize_url(url)
        
        try:
            # Add a random delay to avoid being blocked
            time.sleep(random.uniform(1, 3))
            
            response = requests.get(normalized_url, headers=self.headers, timeout=10)
            if response.status_code != 200:
                return {'error': f'Failed to fetch product page: {response.status_code}'}
            
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
            
            return product_data
            
        except Exception as e:
            print(f"Error scraping product: {str(e)}")
            return {'error': f'Error scraping product: {str(e)}'}
    
    def _extract_name(self, soup):
        """Extract product name"""
        name_elem = soup.find('span', {'id': 'productTitle'})
        return name_elem.get_text().strip() if name_elem else None
    
    def _extract_image(self, soup):
        """Extract product image URL"""
        # Try multiple image selectors as Amazon's structure can vary
        image = soup.find('img', {'id': 'landingImage'})
        if not image:
            image = soup.find('img', {'id': 'imgBlkFront'})
        if not image:
            image = soup.select_one('#main-image-container img')
            
        return image.get('src') or image.get('data-old-hires') if image else None
    
    def _extract_current_price(self, soup):
        """Extract current price"""
        # Check multiple price selectors
        price_whole = soup.find('span', {'class': 'a-price-whole'})
        price_fraction = soup.find('span', {'class': 'a-price-fraction'})
        
        if price_whole and price_fraction:
            try:
                whole = price_whole.get_text().replace(',', '').strip()
                fraction = price_fraction.get_text().strip()
                return float(f"{whole}.{fraction}")
            except ValueError:
                pass
        
        # Try alternative price selectors
        price_elem = soup.find('span', {'id': 'priceblock_ourprice'})
        if not price_elem:
            price_elem = soup.find('span', {'id': 'priceblock_dealprice'})
        if not price_elem:
            price_elem = soup.select_one('.a-price .a-offscreen')
            
        if price_elem:
            try:
                price_text = price_elem.get_text().strip()
                # Remove currency symbol and commas
                price_text = re.sub(r'[^\d.]', '', price_text)
                return float(price_text)
            except ValueError:
                pass
                
        return None
    
    def _extract_original_price(self, soup):
        """Extract original/list price if available"""
        list_price = soup.find('span', {'class': 'priceBlockStrikePriceString'})
        if not list_price:
            list_price = soup.find('span', {'class': 'a-text-strike'})
        if not list_price:
            list_price = soup.select_one('.a-text-price .a-offscreen')
            
        if list_price:
            try:
                price_text = list_price.get_text().strip()
                # Remove currency symbol and commas
                price_text = re.sub(r'[^\d.]', '', price_text)
                return float(price_text)
            except ValueError:
                pass
                
        return None
    
    def _extract_description(self, soup):
        """Extract product description"""
        description = soup.find('div', {'id': 'productDescription'})
        if description:
            return description.get_text().strip()
        
        # Try feature bullets
        feature_bullets = soup.find('div', {'id': 'feature-bullets'})
        if feature_bullets:
            bullet_points = feature_bullets.find_all('li')
            return '\n'.join([bullet.get_text().strip() for bullet in bullet_points])
            
        return None
    
    def _extract_rating(self, soup):
        """Extract product rating"""
        rating = soup.find('span', {'id': 'acrPopover'})
        if not rating:
            rating = soup.find('i', {'class': 'a-icon-star'})
        if not rating:
            rating = soup.select_one('.a-icon-star-small')
            
        if rating:
            try:
                # Rating text is often like "4.5 out of 5 stars"
                rating_text = rating.get_text().strip()
                rating_match = re.search(r'(\d+(\.\d+)?)', rating_text)
                if rating_match:
                    return float(rating_match.group(1))
            except ValueError:
                pass
                
        return None
    
    def _check_in_stock(self, soup):
        """Check if product is in stock"""
        availability = soup.find('span', {'id': 'availability'})
        if availability:
            text = availability.get_text().strip().lower()
            return 'in stock' in text
            
        # Check add to cart button
        add_to_cart = soup.find('input', {'id': 'add-to-cart-button'})
        if add_to_cart:
            return True
            
        return False
    
    def _extract_currency(self, soup):
        """Extract currency symbol"""
        price_elem = soup.find('span', {'class': 'a-price-symbol'})
        if price_elem:
            return price_elem.get_text().strip()
            
        # Try to infer from any price element
        any_price = soup.select_one('.a-price')
        if any_price:
            price_text = any_price.get_text().strip()
            currency_match = re.search(r'([^\d\s.,]+)', price_text)
            if currency_match:
                return currency_match.group(1)
                
        return None


def update_all_products():
    """Update all products in the database"""
    scraper = AmazonScraper()
    products = Product.query.all()
    
    for product in products:
        data = scraper.scrape_product(product.url)
        if 'error' not in data:
            # Always update these fields
            product.name = data['name'] or product.name
            product.image = data['image'] or product.image
            product.last_updated = datetime.utcnow()
            
            # Always store price history even if price didn't change
            if data['current_price']:
                old_price = product.current_price
                product.current_price = data['current_price']
                
                # Add to price history regardless of change
                price_history = PriceHistory(product_id=product.id, price=data['current_price'])
                db.session.add(price_history)
                
                # Only check alerts if price actually decreased
                if old_price and data['current_price'] < old_price:
                    check_price_alerts(product)
            
            # Update additional attributes
            product.original_price = data['original_price'] or product.original_price
            product.currency = data['currency'] or product.currency
            product.description = data['description'] or product.description
            product.rating = data['rating'] or product.rating
            product.in_stock = data['in_stock'] if data['in_stock'] is not None else product.in_stock
                
    db.session.commit()


def check_price_alerts(product):
    """Check if any price alerts should be triggered for a product"""
    # This is where you would implement logic to send email notifications
    # when current_price falls below target_price for active alerts
    active_alerts = PriceAlert.query.filter_by(
        product_id=product.id, 
        is_active=True
    ).filter(
        PriceAlert.target_price >= product.current_price
    ).all()
    
    for alert in active_alerts:
        # In a real implementation, you would send an email here
        print(f"ALERT: Product {product.name} price dropped to {product.current_price}, "
              f"below target of {alert.target_price}. Notifying {alert.email}")
        
        # Mark alert as inactive after triggering
        alert.is_active = False
        
    db.session.commit()