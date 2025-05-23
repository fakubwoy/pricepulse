import requests
import json
import re
from typing import Dict, List, Optional
import os
from dotenv import load_dotenv

load_dotenv()

class LLMService:
    def __init__(self):
        # Using Hugging Face Inference API (free tier)
        self.hf_api_key = os.getenv('HUGGINGFACE_API_KEY')
        self.hf_model = "microsoft/DialoGPT-medium"  # Free model for text generation
        self.headers = {
            "Authorization": f"Bearer {self.hf_api_key}",
            "Content-Type": "application/json"
        }
    
    def extract_product_metadata(self, product_name: str, product_description: str = "") -> Dict:
        """
        Extract structured metadata from product name and description using LLM
        """
        try:
            # Create a structured prompt for metadata extraction
            prompt = f"""
            Extract the following information from this product:
            Product: {product_name}
            Description: {product_description[:200]}...
            
            Return JSON format with:
            - brand: brand name
            - model: model/variant
            - category: product category
            - key_features: list of 3 main features
            - search_terms: list of alternative search terms
            
            JSON:
            """
            
            # For free tier, use a simpler approach with regex patterns
            metadata = self._extract_metadata_with_patterns(product_name, product_description)
            
            # Fallback to API if patterns don't work well
            if not metadata.get('brand') and self.hf_api_key:
                try:
                    api_metadata = self._call_hf_api(prompt)
                    if api_metadata:
                        metadata.update(api_metadata)
                except Exception as e:
                    print(f"LLM API call failed: {e}")
            
            return metadata
            
        except Exception as e:
            print(f"Metadata extraction error: {e}")
            return self._fallback_metadata(product_name)
    
    def _extract_metadata_with_patterns(self, name: str, description: str = "") -> Dict:
        """
        Extract metadata using regex patterns (fallback method)
        """
        text = f"{name} {description}".lower()
        
        # Common brand patterns
        brands = [
            'samsung', 'apple', 'xiaomi', 'oneplus', 'oppo', 'vivo', 'realme',
            'nokia', 'motorola', 'lg', 'sony', 'huawei', 'honor', 'asus',
            'lenovo', 'dell', 'hp', 'acer', 'msi', 'corsair', 'logitech',
            'boat', 'jbl', 'sony', 'bose', 'sennheiser', 'nike', 'adidas',
            'puma', 'reebok', 'himalaya', 'patanjali', 'dabur', 'mamaearth'
        ]
        
        # Category patterns
        categories = {
            'smartphone': ['phone', 'mobile', 'smartphone', 'android', 'ios'],
            'laptop': ['laptop', 'notebook', 'ultrabook'],
            'headphones': ['headphones', 'earphones', 'earbuds', 'headset'],
            'clothing': ['shirt', 'tshirt', 't-shirt', 'jeans', 'dress', 'shoes'],
            'beauty': ['cream', 'serum', 'moisturizer', 'shampoo', 'soap'],
            'electronics': ['charger', 'cable', 'adapter', 'speaker', 'watch']
        }
        
        # Extract brand
        brand = None
        for b in brands:
            if b in text:
                brand = b.title()
                break
        
        # Extract category
        category = 'general'
        for cat, keywords in categories.items():
            if any(keyword in text for keyword in keywords):
                category = cat
                break
        
        # Extract model/variant (simplified)
        model_patterns = [
            r'(\w+\s*\d+\w*)',  # Like "Galaxy M14", "iPhone 14"
            r'(pro|plus|max|mini|lite|ultra)',  # Variants
        ]
        
        model = None
        for pattern in model_patterns:
            match = re.search(pattern, name, re.IGNORECASE)
            if match:
                model = match.group(1)
                break
        
        # Generate search terms
        search_terms = [name]
        if brand:
            search_terms.append(f"{brand} {model or ''}")
        if model:
            search_terms.append(model)
        
        return {
            'brand': brand,
            'model': model,
            'category': category,
            'key_features': self._extract_features(text),
            'search_terms': list(set(search_terms))
        }
    
    def _extract_features(self, text: str) -> List[str]:
        """Extract key features from text"""
        feature_keywords = [
            'gb', 'tb', 'mp', 'mah', 'inch', 'core', 'ghz', 'hz',
            'waterproof', 'wireless', 'bluetooth', 'wifi', 'usb',
            'fast charging', 'quick charge', 'amoled', 'oled'
        ]
        
        features = []
        for keyword in feature_keywords:
            if keyword in text:
                # Extract surrounding context
                idx = text.find(keyword)
                context = text[max(0, idx-10):idx+len(keyword)+10]
                features.append(context.strip())
        
        return features[:3]  # Return top 3 features
    
    def _call_hf_api(self, prompt: str) -> Optional[Dict]:
        """Call Hugging Face API for LLM inference"""
        try:
            url = f"https://api-inference.huggingface.co/models/{self.hf_model}"
            
            payload = {
                "inputs": prompt,
                "parameters": {
                    "max_new_tokens": 200,
                    "temperature": 0.3,
                    "return_full_text": False
                }
            }
            
            response = requests.post(url, headers=self.headers, json=payload, timeout=10)
            
            if response.status_code == 200:
                result = response.json()
                if isinstance(result, list) and len(result) > 0:
                    generated_text = result[0].get('generated_text', '')
                    return self._parse_json_from_text(generated_text)
            
            return None
            
        except Exception as e:
            print(f"Hugging Face API error: {e}")
            return None
    
    def _parse_json_from_text(self, text: str) -> Optional[Dict]:
        """Extract JSON from generated text"""
        try:
            # Find JSON-like structure in text
            json_match = re.search(r'\{.*\}', text, re.DOTALL)
            if json_match:
                json_str = json_match.group(0)
                return json.loads(json_str)
        except Exception as e:
            print(f"JSON parsing error: {e}")
        
        return None
    
    def _fallback_metadata(self, name: str) -> Dict:
        """Fallback metadata when extraction fails"""
        return {
            'brand': None,
            'model': None,
            'category': 'general',
            'key_features': [],
            'search_terms': [name]
        }

class MultiPlatformSearcher:
    def __init__(self):
        self.platforms = {
            'flipkart': {
                'base_url': 'https://www.flipkart.com/search?q=',
                'search_selector': '.s1Q9rs',
                'price_selector': '._30jeq3',
                'title_selector': '._4rR01T'
            },
            'meesho': {
                'base_url': 'https://www.meesho.com/search?q=',
                'search_selector': '.ProductCard__ProductCard',
                'price_selector': '.ProductCard__price',
                'title_selector': '.ProductCard__title'
            }
        }
    
    def search_across_platforms(self, metadata: Dict, primary_product_name: str) -> List[Dict]:
        """
        Search for product across multiple platforms
        """
        results = []
        
        # Generate search queries
        search_queries = self._generate_search_queries(metadata, primary_product_name)
        
        for platform, config in self.platforms.items():
            try:
                platform_results = self._search_platform(platform, search_queries, config)
                results.extend(platform_results)
            except Exception as e:
                print(f"Error searching {platform}: {e}")
        
        return results
    
    def _generate_search_queries(self, metadata: Dict, primary_name: str) -> List[str]:
        """Generate search queries based on metadata"""
        queries = []
        
        # Primary query
        queries.append(primary_name)
        
        # Brand + model query
        if metadata.get('brand') and metadata.get('model'):
            queries.append(f"{metadata['brand']} {metadata['model']}")
        
        # Search terms from LLM
        if metadata.get('search_terms'):
            queries.extend(metadata['search_terms'][:2])
        
        return list(set(queries))  # Remove duplicates
    
    def _search_platform(self, platform: str, queries: List[str], config: Dict) -> List[Dict]:
        """
        Search a specific platform using Google site search
        """
        results = []
        
        for query in queries[:2]:  # Limit to 2 queries per platform
            try:
                # Use Google site search
                google_query = f"{query} site:{platform}.com"
                
                # This is a simplified approach - in production, you'd want to use
                # proper web scraping with requests/BeautifulSoup
                search_results = self._google_site_search(google_query, platform)
                results.extend(search_results)
                
            except Exception as e:
                print(f"Platform search error for {platform}: {e}")
        
        return results[:5]  # Return top 5 results per platform
    
    def _google_site_search(self, query: str, platform: str) -> List[Dict]:
        """
        Perform Google site search and extract results
        Note: This is a simplified version. In production, use proper APIs
        """
        # This is a placeholder implementation
        # In reality, you'd use Google Custom Search API or scrape search results
        
        # Mock results for demonstration
        mock_results = [
            {
                'platform': platform,
                'title': f"Sample Product from {platform.title()}",
                'price': 15999.0,
                'currency': '₹',
                'url': f"https://{platform}.com/sample-product",
                'availability': 'In Stock'
            }
        ]
        
        return mock_results