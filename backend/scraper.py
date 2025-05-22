import requests
import re
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
import time
import random
import json
import hashlib
from models import Product, PriceHistory, PriceAlert
from database import db
import urllib.parse
import os
from urllib.parse import urlencode
import base64

class AmazonScraper:
    def __init__(self):
        # Multiple scraping service APIs for redundancy
        self.scrapingbee_api_key = os.getenv('SCRAPINGBEE_API_KEY')
        self.scraperapi_key = os.getenv('SCRAPERAPI_KEY')  # Alternative service
        self.zenrows_api_key = os.getenv('ZENROWS_API_KEY')  # Another alternative
        
        # Rate limiting storage (in production, use Redis)
        self.rate_limit_cache = {}
        
        # More diverse user agents
        self.user_agents = [
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
            'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:122.0) Gecko/20100101 Firefox/122.0',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:122.0) Gecko/20100101 Firefox/122.0',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36 Edg/121.0.0.0'
        ]
        
        # Session management for better request handling
        self.session = requests.Session()
        self.session.headers.update({
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate',
            'DNT': '1',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'none',
            'Cache-Control': 'max-age=0'
        })
    
    def is_rate_limited(self, service_name):
        """Check if we're currently rate limited for a service"""
        if service_name in self.rate_limit_cache:
            return datetime.utcnow() < self.rate_limit_cache[service_name]
        return False
    
    def set_rate_limit(self, service_name, minutes=30):
        """Set rate limit timeout for a service"""
        self.rate_limit_cache[service_name] = datetime.utcnow() + timedelta(minutes=minutes)
    
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
    
    def scrape_with_zenrows(self, url):
        """Scrape using ZenRows API - Good alternative to ScrapingBee"""
        if not self.zenrows_api_key or self.is_rate_limited('zenrows'):
            return None
            
        api_url = "https://api.zenrows.com/v1/"
        params = {
            'api_key': self.zenrows_api_key,
            'url': url,
            'js_render': 'true',
            'antibot': 'true',
            'premium_proxy': 'true',
            'proxy_country': 'US',
            'wait': 3000,
            'session_id': hashlib.md5(url.encode()).hexdigest()[:8]  # Consistent session
        }
        
        try:
            print(f"Making ZenRows request to: {url}")
            response = requests.get(api_url, params=params, timeout=60)
            
            if response.status_code == 200:
                print("ZenRows request successful")
                return response.text
            elif response.status_code == 422:
                return {'error': 'Invalid URL or blocked by Amazon'}
            elif response.status_code == 401:
                return {'error': 'Invalid ZenRows API key'}
            elif response.status_code == 429:
                self.set_rate_limit('zenrows', 60)
                return {'error': 'ZenRows rate limit exceeded'}
            else:
                print(f"ZenRows error: HTTP {response.status_code}")
                return None
                
        except requests.exceptions.Timeout:
            return {'error': 'ZenRows request timed out'}
        except Exception as e:
            print(f"ZenRows error: {str(e)}")
            return None
    
    def scrape_with_scraperapi(self, url):
        """Scrape using ScraperAPI - Another reliable alternative"""
        if not self.scraperapi_key or self.is_rate_limited('scraperapi'):
            return None
            
        api_url = "http://api.scraperapi.com"
        params = {
            'api_key': self.scraperapi_key,
            'url': url,
            'render': 'true',
            'country_code': 'us',
            'premium': 'true',
            'session_number': random.randint(1, 100)
        }
        
        try:
            print(f"Making ScraperAPI request to: {url}")
            response = requests.get(api_url, params=params, timeout=60)
            
            if response.status_code == 200:
                print("ScraperAPI request successful")
                return response.text
            elif response.status_code == 422:
                return {'error': 'Invalid URL or blocked by Amazon'}
            elif response.status_code == 401:
                return {'error': 'Invalid ScraperAPI key'}
            elif response.status_code == 429:
                self.set_rate_limit('scraperapi', 60)
                return {'error': 'ScraperAPI rate limit exceeded'}
            else:
                print(f"ScraperAPI error: HTTP {response.status_code}")
                return None
                
        except requests.exceptions.Timeout:
            return {'error': 'ScraperAPI request timed out'}
        except Exception as e:
            print(f"ScraperAPI error: {str(e)}")
            return None
    
    def scrape_with_scrapingbee(self, url):
        """Scrape using ScrapingBee API with improved settings"""
        if not self.scrapingbee_api_key or self.is_rate_limited('scrapingbee'):
            return None
            
        api_url = "https://app.scrapingbee.com/api/v1/"
        params = {
            'api_key': self.scrapingbee_api_key,
            'url': url,
            'render_js': 'true',  # Enable JS rendering for better results
            'premium_proxy': 'true',
            'country_code': 'US',
            'wait': 5000,  # Increased wait time
            'wait_for': 'networkidle',
            'block_ads': 'true',
            'block_resources': 'false',  # Don't block resources that might be needed
            'session_id': random.randint(1, 1000)  # Random session ID
        }
        
        try:
            print(f"Making ScrapingBee request to: {url}")
            response = requests.get(api_url, params=params, timeout=60)
            
            if response.status_code == 200:
                print("ScrapingBee request successful")
                return response.text
            elif response.status_code == 422:
                return {'error': 'Invalid URL or blocked by Amazon'}
            elif response.status_code == 401:
                return {'error': 'Invalid ScrapingBee API key'}
            elif response.status_code == 403:
                self.set_rate_limit('scrapingbee', 60)
                return {'error': 'ScrapingBee quota exceeded'}
            else:
                print(f"ScrapingBee error: HTTP {response.status_code}")
                return None
                
        except requests.exceptions.Timeout:
            return {'error': 'ScrapingBee request timed out'}
        except Exception as e:
            print(f"ScrapingBee error: {str(e)}")
            return None
    
    def scrape_with_direct_request(self, url):
        """Fallback direct request with advanced anti-detection"""
        if self.is_rate_limited('direct'):
            return None
            
        try:
            # Randomize user agent and headers
            headers = {
                'User-Agent': random.choice(self.user_agents),
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.9',
                'Accept-Encoding': 'gzip, deflate, br',
                'DNT': '1',
                'Connection': 'keep-alive',
                'Upgrade-Insecure-Requests': '1',
                'Sec-Fetch-Dest': 'document',
                'Sec-Fetch-Mode': 'navigate',
                'Sec-Fetch-Site': 'none',
                'Cache-Control': 'max-age=0',
                'Referer': 'https://www.google.com/',
                'sec-ch-ua': '"Not A(Brand";v="99", "Google Chrome";v="121", "Chromium";v="121"',
                'sec-ch-ua-mobile': '?0',
                'sec-ch-ua-platform': '"Windows"'
            }
            
            # Add random delay
            time.sleep(random.uniform(2, 5))
            
            print(f"Making direct request to: {url}")
            response = self.session.get(url, headers=headers, timeout=30)
            
            if response.status_code == 200:
                print("Direct request successful")
                return response.text
            elif response.status_code == 503:
                self.set_rate_limit('direct', 120)  # 2 hour timeout for direct requests
                return {'error': 'Amazon is blocking direct requests'}
            else:
                print(f"Direct request error: HTTP {response.status_code}")
                return None
                
        except Exception as e:
            print(f"Direct request error: {str(e)}")
            return None
    
    def scrape_product(self, url):
        """Main scraping method with multiple fallback strategies"""
        if not self.is_valid_amazon_url(url):
            return {'error': 'Invalid Amazon URL. Please provide a valid Amazon product URL.'}
        
        normalized_url = self.normalize_url(url)
        
        # Try multiple scraping services in order of preference
        scraping_methods = []
        
        # Add available services
        if self.zenrows_api_key and not self.is_rate_limited('zenrows'):
            scraping_methods.append(('ZenRows', self.scrape_with_zenrows))
        
        if self.scrapingbee_api_key and not self.is_rate_limited('scrapingbee'):
            scraping_methods.append(('ScrapingBee', self.scrape_with_scrapingbee))
        
        if self.scraperapi_key and not self.is_rate_limited('scraperapi'):
            scraping_methods.append(('ScraperAPI', self.scrape_with_scraperapi))
        
        # Add direct request as last resort
        if not self.is_rate_limited('direct'):
            scraping_methods.append(('Direct', self.scrape_with_direct_request))
        
        if not scraping_methods:
            return {
                'error': 'All scraping services are currently rate limited or unavailable. Please try again later.'
            }
        
        html_content = None
        last_error = None
        
        # Try each method until one succeeds
        for method_name, method_func in scraping_methods:
            print(f"Trying {method_name} for URL: {normalized_url}")
            
            result = method_func(normalized_url)
            
            if isinstance(result, dict) and 'error' in result:
                last_error = result
                print(f"{method_name} failed: {result['error']}")
                continue
            
            if result:
                html_content = result
                print(f"Successfully scraped using {method_name}")
                break
            
            # Add delay between attempts
            time.sleep(random.uniform(1, 3))
        
        if not html_content:
            return last_error or {
                'error': 'Failed to fetch product page using all available methods. Please try again later.'
            }
        
        # Parse the HTML content
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # Check for blocking indicators
        content_lower = html_content.lower()
        if 'robot' in content_lower or 'captcha' in content_lower or 'blocked' in content_lower:
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
            '.a-size-large.product-title-word-break',
            '[data-testid="product-title"]',
            '.pdp-product-name',
            '#title'
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
            '#imageBlock img',
            '[data-testid="product-image"]',
            '.pdp-image img'
        ]
        
        for selector in selectors:
            image = soup.select_one(selector)
            if image:
                for attr in ['data-old-hires', 'src', 'data-src', 'data-original']:
                    img_url = image.get(attr)
                    if img_url and img_url.startswith('http'):
                        return img_url
        
        return None
    
    def _extract_current_price(self, soup):
        """Extract current price with enhanced selectors"""
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
            '.a-price-range .a-offscreen',
            '[data-testid="price-current"]',
            '.pdp-price',
            '#apex_desktop .a-price .a-offscreen',
            '.a-price[data-a-color="price"] .a-offscreen'
        ]
        
        for selector in price_selectors:
            price_elem = soup.select_one(selector)
            if price_elem:
                try:
                    price_text = price_elem.get_text().strip()
                    # Enhanced price extraction regex
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
            '.a-price-was .a-offscreen',
            '[data-testid="price-original"]',
            '.pdp-price-original'
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
            '#feature-bullets',
            '[data-testid="product-description"]',
            '.pdp-description'
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
            'i[data-hook="average-star-rating"] .a-icon-alt',
            '[data-testid="product-rating"]',
            '.pdp-rating'
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
            '[data-testid="availability"]',
            '.pdp-availability'
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
        if soup.select_one('#add-to-cart-button, input[name="submit.add-to-cart"], [data-testid="add-to-cart"]'):
            return True
        
        return False
    
    def _extract_currency(self, soup):
        """Extract currency symbol"""
        currency_selectors = [
            '.a-price-symbol',
            '.a-price .a-offscreen',
            '[data-testid="currency"]'
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
    """Update all products in the database with improved rate limiting"""
    scraper = AmazonScraper()
    products = Product.query.all()
    
    # Randomize the order to avoid patterns
    random.shuffle(products)
    
    for i, product in enumerate(products):
        # Skip products updated in the last 4 hours
        if product.last_updated and (datetime.utcnow() - product.last_updated).total_seconds() < 14400:
            continue
        
        print(f"Updating product {i+1}/{len(products)}: {product.name}")
        
        # Progressive delay - longer delays for more products updated
        delay = random.uniform(10, 30) + (i * 2)  # Increase delay over time
        print(f"Waiting {delay:.1f} seconds before next request...")
        time.sleep(delay)
        
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
            
            # Commit after each successful update
            db.session.commit()
            print(f"Successfully updated product: {product.name}")
            
        else:
            print(f"Error updating product {product.name}: {data['error']}")
            
            # If we get rate limited, wait longer
            if 'rate limit' in data['error'].lower():
                print("Rate limited detected, waiting 5 minutes...")
                time.sleep(300)  # Wait 5 minutes
    
    print("Finished updating all products")


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
        try:
            from email_service import send_price_alert_email
            send_price_alert_email(alert, product)
        except ImportError:
            print("Email service not available")
        
        # Mark alert as inactive after triggering
        alert.is_active = False
    
    db.session.commit()