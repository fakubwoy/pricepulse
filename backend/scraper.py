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
        # ZenRows E-commerce API - Primary method
        self.zenrows_api_key = os.getenv('ZENROWS_API_KEY')
        
        # Fallback scraping service APIs for redundancy
        self.scrapingbee_api_key = os.getenv('SCRAPINGBEE_API_KEY')
        self.scraperapi_key = os.getenv('SCRAPERAPI_KEY')
        
        # Rate limiting storage (in production, use Redis)
        self.rate_limit_cache = {}
        
        # More diverse user agents for fallback methods
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
        # More flexible pattern that accepts various Amazon URL formats
        patterns = [
            # Standard format: /dp/ASIN
            r'^https?://(www\.)?amazon\.(com|in|co\.uk|ca|de|fr|es|it|co\.jp)/.*/dp/[A-Z0-9]{10}',
            # Direct format: /dp/ASIN (without path)
            r'^https?://(www\.)?amazon\.(com|in|co\.uk|ca|de|fr|es|it|co\.jp)/dp/[A-Z0-9]{10}',
            # gp/product format
            r'^https?://(www\.)?amazon\.(com|in|co\.uk|ca|de|fr|es|it|co\.jp)/gp/product/[A-Z0-9]{10}',
            # exec/obidos format (older URLs)
            r'^https?://(www\.)?amazon\.(com|in|co\.uk|ca|de|fr|es|it|co\.jp)/exec/obidos/ASIN/[A-Z0-9]{10}'
        ]
        
        for pattern in patterns:
            if re.match(pattern, url):
                return True
        
        return False
    
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
            elif 'amazon.co.uk' in url:
                return f"https://www.amazon.co.uk/dp/{asin}"
            elif 'amazon.ca' in url:
                return f"https://www.amazon.ca/dp/{asin}"
            elif 'amazon.de' in url:
                return f"https://www.amazon.de/dp/{asin}"
        return url
    
    def scrape_with_zenrows_ecommerce_api(self, url):
        """Primary method: Scrape using ZenRows E-commerce API specifically for Amazon"""
        if not self.zenrows_api_key or self.is_rate_limited('zenrows_ecommerce'):
            return None
            
        api_url = "https://ecommerce.api.zenrows.com/v1/targets/amazon/products/"
        params = {
            'apikey': self.zenrows_api_key,
            'url': url,
        }
        
        try:
            print(f"Making ZenRows E-commerce API request to: {url}")
            response = requests.get(api_url, params=params, timeout=60)
            
            if response.status_code == 200:
                print("ZenRows E-commerce API request successful")
                data = response.json()
                
                # Transform the API response to our expected format
                return self._transform_zenrows_response(data, url)
                
            elif response.status_code == 404:
                return {'error': 'Product not found or URL is invalid'}
            elif response.status_code == 401:
                return {'error': 'Invalid ZenRows API key'}
            elif response.status_code == 429:
                self.set_rate_limit('zenrows_ecommerce', 60)
                return {'error': 'ZenRows E-commerce API rate limit exceeded'}
            elif response.status_code == 422:
                return {'error': 'Invalid URL format or unsupported Amazon domain'}
            else:
                print(f"ZenRows E-commerce API error: HTTP {response.status_code}")
                try:
                    error_data = response.json()
                    return {'error': f"API Error: {error_data.get('message', 'Unknown error')}"}
                except:
                    return {'error': f'HTTP {response.status_code} error'}
                
        except requests.exceptions.Timeout:
            return {'error': 'ZenRows E-commerce API request timed out'}
        except requests.exceptions.JSONDecodeError:
            return {'error': 'Invalid JSON response from ZenRows E-commerce API'}
        except Exception as e:
            print(f"ZenRows E-commerce API error: {str(e)}")
            return {'error': f'Unexpected API error: {str(e)}'}
    
    def _transform_zenrows_response(self, api_data, original_url):
        """Transform ZenRows E-commerce API response to our product data format"""
        try:
            # Extract currency information
            currency_symbol = api_data.get('price_currency_symbol', '$')
            if 'amazon.in' in original_url:
                currency_symbol = '₹'
            elif 'amazon.co.uk' in original_url:
                currency_symbol = '£'
            elif 'amazon.de' in original_url or 'amazon.fr' in original_url:
                currency_symbol = '€'
            
            # Extract price - handle both current price and discounted price
            current_price = api_data.get('product_price')
            original_price = api_data.get('product_price_before_discount')
            
            # If there's no discount, original_price might be None
            if original_price is None or original_price == current_price:
                original_price = current_price
            
            # Get the first image from the list
            images = api_data.get('product_images', [])
            main_image = images[0] if images else None
            
            # Extract availability
            is_available = api_data.get('is_available', True)
            availability_status = api_data.get('availability_status', '').lower()
            in_stock = is_available and 'in stock' in availability_status
            
            # Build description from available fields
            description_parts = []
            if api_data.get('product_description'):
                description_parts.append(api_data['product_description'])
            if api_data.get('ai_generated_review_summary'):
                description_parts.append(f"Review Summary: {api_data['ai_generated_review_summary']}")
            description = '\n'.join(description_parts) if description_parts else None
            
            product_data = {
                'url': original_url,
                'name': api_data.get('product_name'),
                'image': main_image,
                'current_price': current_price,
                'original_price': original_price,
                'currency': currency_symbol,
                'description': description,
                'rating': api_data.get('rating_score'),
                'in_stock': in_stock,
                'brand': api_data.get('brand'),
                'model_number': api_data.get('product_model_number'),
                'asin': api_data.get('parent_asin') or self.extract_asin(original_url),
                'review_count': api_data.get('review_count'),
                'discount': api_data.get('product_discount'),
                'badge': api_data.get('badge'),
                'amazon_choice': api_data.get('amazon_choice', False),
                'last_updated': datetime.utcnow()
            }
            
            print(f"Successfully transformed product data: {product_data['name']}")
            return product_data
            
        except Exception as e:
            print(f"Error transforming ZenRows response: {str(e)}")
            return {'error': f'Error processing API response: {str(e)}'}
    
    def scrape_with_zenrows_general(self, url):
        """Fallback: Scrape using ZenRows general API with HTML parsing"""
        if not self.zenrows_api_key or self.is_rate_limited('zenrows_general'):
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
            'session_id': hashlib.md5(url.encode()).hexdigest()[:8]
        }
        
        try:
            print(f"Making ZenRows general API request to: {url}")
            response = requests.get(api_url, params=params, timeout=60)
            
            if response.status_code == 200:
                print("ZenRows general API request successful")
                return response.text
            elif response.status_code == 422:
                return {'error': 'Invalid URL or blocked by Amazon'}
            elif response.status_code == 401:
                return {'error': 'Invalid ZenRows API key'}
            elif response.status_code == 429:
                self.set_rate_limit('zenrows_general', 60)
                return {'error': 'ZenRows general API rate limit exceeded'}
            else:
                print(f"ZenRows general API error: HTTP {response.status_code}")
                return None
                
        except requests.exceptions.Timeout:
            return {'error': 'ZenRows general API request timed out'}
        except Exception as e:
            print(f"ZenRows general API error: {str(e)}")
            return None
    
    def scrape_with_scrapingbee(self, url):
        """Fallback: Scrape using ScrapingBee API with improved settings"""
        if not self.scrapingbee_api_key or self.is_rate_limited('scrapingbee'):
            return None
            
        api_url = "https://app.scrapingbee.com/api/v1/"
        params = {
            'api_key': self.scrapingbee_api_key,
            'url': url,
            'render_js': 'true',
            'premium_proxy': 'true',
            'country_code': 'US',
            'wait': 5000,
            'wait_for': 'networkidle',
            'block_ads': 'true',
            'block_resources': 'false',
            'session_id': random.randint(1, 1000)
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
    
    def scrape_with_scraperapi(self, url):
        """Fallback: Scrape using ScraperAPI"""
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
    
    def scrape_with_direct_request(self, url):
        """Last resort: Fallback direct request with advanced anti-detection"""
        if self.is_rate_limited('direct'):
            return None
            
        try:
            headers = {
                'User-Agent': random.choice(self.user_agents),
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.9',
                'Accept-Encoding': 'gzip, deflate, br',
                'DNT': '1',
                'Connection': 'keep-alive',
                'Upgrade-Insecure-Requests': '1',
                'Referer': 'https://www.google.com/',
            }
            
            time.sleep(random.uniform(2, 5))
            
            print(f"Making direct request to: {url}")
            response = self.session.get(url, headers=headers, timeout=30)
            
            if response.status_code == 200:
                print("Direct request successful")
                return response.text
            elif response.status_code == 503:
                self.set_rate_limit('direct', 120)
                return {'error': 'Amazon is blocking direct requests'}
            else:
                print(f"Direct request error: HTTP {response.status_code}")
                return None
                
        except Exception as e:
            print(f"Direct request error: {str(e)}")
            return None
    
    def scrape_product(self, url):
        """Main scraping method - prioritizes ZenRows E-commerce API"""
        if not self.is_valid_amazon_url(url):
            return {'error': 'Invalid Amazon URL. Please provide a valid Amazon product URL.'}
        
        normalized_url = self.normalize_url(url)
        
        # Method 1: Try ZenRows E-commerce API first (most reliable for Amazon)
        if self.zenrows_api_key and not self.is_rate_limited('zenrows_ecommerce'):
            print("Attempting ZenRows E-commerce API...")
            result = self.scrape_with_zenrows_ecommerce_api(normalized_url)
            
            if result and 'error' not in result:
                return result
            elif result and 'error' in result:
                print(f"ZenRows E-commerce API failed: {result['error']}")
                # Don't return error immediately, try fallback methods
        
        # Fallback methods if E-commerce API fails
        scraping_methods = []
        
        # Add available fallback services
        if self.zenrows_api_key and not self.is_rate_limited('zenrows_general'):
            scraping_methods.append(('ZenRows General', self.scrape_with_zenrows_general))
        
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
        
        # Try each fallback method until one succeeds
        for method_name, method_func in scraping_methods:
            print(f"Trying fallback method {method_name} for URL: {normalized_url}")
            
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
        
        # Parse the HTML content using existing parsing logic
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # Check for blocking indicators
        content_lower = html_content.lower()
        if 'robot' in content_lower or 'captcha' in content_lower or 'blocked' in content_lower:
            return {'error': 'Amazon is requesting CAPTCHA verification. Please try again in a few minutes.'}
        
        # Extract product details using existing parsing methods
        product_data = {
            'url': normalized_url,
            'name': self._extract_name(soup),
            'image': self._extract_image(soup),
            'current_price': self._extract_current_price(soup),
            'original_price': self._extract_original_price(soup),
            'description': self._extract_description(soup),
            'rating': self._extract_rating(soup),
            'in_stock': self._check_in_stock(soup),
            'currency': self._extract_currency(soup) or ("₹" if 'amazon.in' in normalized_url else "$"),
            'last_updated': datetime.utcnow()
        }
        
        # Validate that we got essential data
        if not product_data['name']:
            return {'error': 'Could not extract product information. The page structure may have changed or the product is unavailable.'}
        
        print(f"Successfully extracted product: {product_data['name']}")
        return product_data
    
    # Keep all existing HTML parsing methods unchanged
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
    """Update all products in the database with improved rate limiting and daily price storage"""
    scraper = AmazonScraper()
    products = Product.query.all()
    
    # Randomize the order to avoid patterns
    random.shuffle(products)
    
    for i, product in enumerate(products):
        # Check if product needs updating
        needs_update = False
        
        if not product.last_updated:
            needs_update = True
        else:
            # Check if it's been more than 4 hours since last update
            time_since_update = (datetime.utcnow() - product.last_updated).total_seconds()
            if time_since_update >= 14400:  # 4 hours
                needs_update = True
                
        if not needs_update:
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
            
            price_to_store = data.get('current_price', product.current_price)

            if price_to_store and price_to_store > 0:
                # Add new price history entry for every refresh
                price_history = PriceHistory(product_id=product.id, price=price_to_store)
                db.session.add(price_history)
                print(f"Added price entry: {price_to_store} for {product.name}")
                
                # Update current price (even if it's the same)
                if data.get('current_price'):
                    old_price = product.current_price
                    product.current_price = data['current_price']
                    
                    if old_price != data['current_price']:
                        print(f"Price changed: {old_price} -> {data['current_price']}")
                        # Check price alerts only when price actually changes
                        check_price_alerts(product)
                    else:
                        print(f"Price unchanged: {data['current_price']}")
            
            # Update other attributes
            for attr in ['original_price', 'currency', 'description', 'rating', 'in_stock']:
                if data.get(attr) is not None:
                    setattr(product, attr, data[attr])
            
            # Commit after each successful update
            db.session.commit()
            print(f"Successfully updated product: {product.name}")
            
        else:
            print(f"Error updating product {product.name}: {data['error']}")
            
            # Update the last_updated timestamp even if scraping failed
            product.last_updated = datetime.utcnow()
            db.session.commit()
            
            # If we get rate limited, wait longer
            if 'rate limit' in data['error'].lower():
                print("Rate limited detected, waiting 5 minutes...")
                time.sleep(300)  # Wait 5 minutes
    
    print("Finished updating all products")

# Add this new function to scraper.py

def store_daily_prices():
    """Store current prices for all products to maintain daily price history"""
    from models import Product, PriceHistory
    from database import db
    
    products = Product.query.all()
    today = datetime.utcnow().date()
    
    for product in products:
        # Check if we already have a price entry for today
        today_price_entry = PriceHistory.query.filter_by(product_id=product.id).filter(
            db.func.date(PriceHistory.timestamp) == today
        ).first()
        
        if not today_price_entry and product.current_price and product.current_price > 0:
            # Add price history entry for today
            price_history = PriceHistory(product_id=product.id, price=product.current_price)
            db.session.add(price_history)
            print(f"Stored daily price for {product.name}: {product.current_price}")
    
    db.session.commit()
    print(f"Finished storing daily prices for {len(products)} products")
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