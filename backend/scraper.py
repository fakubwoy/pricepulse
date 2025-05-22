import random
import time
import re
import os
from datetime import datetime
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright
from fake_useragent import UserAgent
from typing import Optional, Dict, Any

class AmazonScraper:
    def __init__(self):
        self.ua = UserAgent()
        self.viewports = [
            {'width': 1920, 'height': 1080},
            {'width': 1366, 'height': 768},
            {'width': 1536, 'height': 864},
            {'width': 1440, 'height': 900}
        ]
        self.mouse_movements = [
            [(100, 100), (300, 150), (500, 200)],
            [(500, 200), (400, 300), (300, 400)],
            [(200, 200), (200, 400), (400, 400)]
        ]
        self.scraping_attempts = 0

    def is_valid_amazon_url(self, url: str) -> bool:
        """Validate if URL is an Amazon product URL"""
        pattern = r'^https?://(www\.)?amazon\.(com|in|co\.uk|ca|de|fr|es|it|co\.jp)/.*/dp/[A-Z0-9]{10}'
        return bool(re.match(pattern, url))
    
    def extract_asin(self, url: str) -> Optional[str]:
        """Extract ASIN from Amazon URL"""
        asin_match = re.search(r'/dp/([A-Z0-9]{10})', url)
        return asin_match.group(1) if asin_match else None
    
    def normalize_url(self, url: str) -> str:
        """Normalize Amazon URL to standard format"""
        asin = self.extract_asin(url)
        if asin:
            domain = 'amazon.com' if 'amazon.com' in url else 'amazon.in'
            return f"https://www.{domain}/dp/{asin}"
        return url

    def human_like_delay(self):
        """Random delay between actions"""
        time.sleep(random.uniform(0.5, 3.0))
    
    def human_like_scroll(self, page):
        """Realistic scrolling behavior"""
        scroll_steps = random.randint(3, 6)
        for _ in range(scroll_steps):
            scroll_amount = random.randint(200, 800)
            page.mouse.wheel(0, scroll_amount)
            self.human_like_delay()
    
    def human_like_mouse_movement(self, page):
        """Move mouse in realistic patterns"""
        movement = random.choice(self.mouse_movements)
        for x, y in movement:
            page.mouse.move(x, y)
            self.human_like_delay()
    
    def block_resources(self, route):
        """Block unnecessary resources to speed up scraping"""
        if any(ext in route.request.url for ext in ['.png', '.jpg', '.jpeg', '.gif', '.css', '.woff', '.ttf']):
            route.abort()
        else:
            route.continue_()

    def scrape_product(self, url: str) -> Dict[str, Any]:
        """Main scraping method with Playwright and stealth techniques"""
        if not self.is_valid_amazon_url(url):
            return {'error': 'Invalid Amazon URL. Please provide a valid Amazon product URL.'}
        
        normalized_url = self.normalize_url(url)
        
        # Implement scraping cooldown
        if self.scraping_attempts > 0:
            cooldown = min(30, 5 * self.scraping_attempts)  # Exponential backoff
            time.sleep(cooldown)
        
        self.scraping_attempts += 1
        
        try:
            with sync_playwright() as p:
                # Launch Firefox with various stealth options
                browser = p.firefox.launch(
                    headless=True,
                    proxy=None,  # Add proxy here if needed
                    firefox_user_prefs={
                        'javascript.enabled': True,
                        'network.cookie.cookieBehavior': 0,
                        'privacy.trackingprotection.enabled': False
                    }
                )
                
                context = browser.new_context(
                    user_agent=self.ua.firefox,
                    viewport=random.choice(self.viewports),
                    locale='en-US',
                    timezone_id='America/New_York',
                    geolocation={'latitude': random.uniform(20, 50), 'longitude': random.uniform(-120, -70)},
                    permissions=['geolocation']
                )
                
                # Block unnecessary resources
                context.route("**/*", self.block_resources)
                
                page = context.new_page()
                
                try:
                    # Initial random delay
                    self.human_like_delay()
                    
                    # Navigate to page
                    page.goto(
                        normalized_url,
                        timeout=60000,
                        wait_until='domcontentloaded',
                        referer='https://www.google.com/'
                    )
                    
                    # Human-like interactions
                    self.human_like_scroll(page)
                    self.human_like_mouse_movement(page)
                    
                    # Wait for critical elements
                    try:
                        page.wait_for_selector('#productTitle', timeout=15000)
                        page.wait_for_selector('.a-price', timeout=15000)
                    except:
                        pass  # Continue even if these aren't found
                    
                    # Get final page content
                    content = page.content()
                    
                    # Parse the content
                    product_data = self.parse_product_page(content, normalized_url)
                    
                    # Reset attempt counter on success
                    self.scraping_attempts = 0
                    return product_data
                    
                except Exception as e:
                    return {'error': f'Page interaction failed: {str(e)}'}
                finally:
                    browser.close()
                    
        except Exception as e:
            return {'error': f'Browser launch failed: {str(e)}'}

    def parse_product_page(self, html: str, url: str) -> Dict[str, Any]:
        """Parse product details from HTML"""
        soup = BeautifulSoup(html, 'html.parser')
        
        # Check for blocking
        if any(text in html.lower() for text in ['captcha', 'robot check', 'enter the characters']):
            return {'error': 'Amazon is showing CAPTCHA. Try again later or use a VPN.'}
        
        product_data = {
            'url': url,
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
        
        if not product_data['name']:
            return {'error': 'Could not extract product information. The page structure may have changed.'}
        
        return product_data
    
    def _extract_name(self, soup) -> Optional[str]:
        """Extract product name"""
        selectors = [
            '#productTitle',
            'h1.a-size-large',
            'h1[data-automation-id="product-title"]',
            '.product-title-word-break'
        ]
        for selector in selectors:
            elem = soup.select_one(selector)
            if elem and (name := elem.get_text().strip()):
                return name[:500]
        return None
    
    def _extract_image(self, soup) -> Optional[str]:
        """Extract product image"""
        selectors = [
            '#landingImage',
            '#imgBlkFront',
            '.a-dynamic-image',
            'img[data-old-hires]'
        ]
        for selector in selectors:
            img = soup.select_one(selector)
            if img:
                for attr in ['src', 'data-src', 'data-old-hires']:
                    if url := img.get(attr):
                        if url.startswith('http'):
                            return url.split('._')[0] + '._SL1500_'  # Get higher quality image
        return None
    
    def _extract_current_price(self, soup) -> Optional[float]:
        """Extract current price"""
        # Try price whole/fraction first
        whole = soup.select_one('.a-price-whole')
        fraction = soup.select_one('.a-price-fraction')
        if whole and fraction:
            try:
                return float(f"{whole.get_text().replace(',', '')}.{fraction.get_text()}")
            except:
                pass
        
        # Try other price selectors
        price_selectors = [
            '.a-price .a-offscreen',
            '#priceblock_ourprice',
            '#priceblock_dealprice',
            '.apexPriceToPay .a-offscreen'
        ]
        for selector in price_selectors:
            elem = soup.select_one(selector)
            if elem and (price_text := elem.get_text()):
                if match := re.search(r'[\d,]+\.?\d{0,2}', price_text.replace(',', '')):
                    try:
                        return float(match.group())
                    except:
                        continue
        return None
    
    def _extract_original_price(self, soup) -> Optional[float]:
        """Extract original price if on sale"""
        selectors = [
            '.a-text-price .a-offscreen',
            '.priceBlockStrikePriceString',
            '.a-price.a-text-price .a-offscreen'
        ]
        for selector in selectors:
            elem = soup.select_one(selector)
            if elem and (price_text := elem.get_text()):
                if match := re.search(r'[\d,]+\.?\d{0,2}', price_text.replace(',', '')):
                    try:
                        return float(match.group())
                    except:
                        continue
        return None
    
    def _extract_description(self, soup) -> Optional[str]:
        """Extract product description"""
        # Try feature bullets first
        bullets = soup.select('#feature-bullets li')
        if bullets:
            desc = ' '.join([b.get_text().strip() for b in bullets[:5] if b.get_text().strip()])
            if desc:
                return desc[:1000]
        
        # Try product description
        desc_elem = soup.select_one('#productDescription')
        if desc_elem and (desc := desc_elem.get_text().strip()):
            return desc[:1000]
        
        return None
    
    def _extract_rating(self, soup) -> Optional[float]:
        """Extract product rating"""
        rating_elem = soup.select_one('i[data-hook="average-star-rating"]')
        if not rating_elem:
            rating_elem = soup.select_one('.a-icon-star .a-icon-alt')
        
        if rating_elem and (rating_text := rating_elem.get_text()):
            if match := re.search(r'(\d\.?\d?) out', rating_text):
                try:
                    return float(match.group(1))
                except:
                    pass
        return None
    
    def _check_in_stock(self, soup) -> bool:
        """Check if product is in stock"""
        stock_text = soup.select_one('#availability').get_text().lower() if soup.select_one('#availability') else ''
        if any(s in stock_text for s in ['in stock', 'available']):
            return True
        if any(s in stock_text for s in ['out of stock', 'unavailable']):
            return False
        return bool(soup.select_one('#add-to-cart-button'))  # If add to cart button exists
    
    def _extract_currency(self, soup) -> Optional[str]:
        """Extract currency symbol"""
        elem = soup.select_one('.a-price-symbol')
        if elem and (symbol := elem.get_text().strip()):
            return symbol
        return None