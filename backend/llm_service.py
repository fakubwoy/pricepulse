import requests
import json
import re
from typing import Dict, List, Optional
import os
from dotenv import load_dotenv
from urllib.parse import quote_plus

load_dotenv()

class LLMService:
    def __init__(self):
        self.hf_api_key = os.getenv('HUGGINGFACE_API_KEY')
        self.hf_model = "microsoft/DialoGPT-medium"
        self.headers = {
            "Authorization": f"Bearer {self.hf_api_key}",
            "Content-Type": "application/json"
        }
    
    def extract_product_metadata(self, product_name: str, product_description: str = "") -> Dict:
        try:
            metadata = self._extract_metadata_with_patterns(product_name, product_description)
            
            if not metadata.get('brand') and self.hf_api_key:
                try:
                    prompt = f"""
                    Extract brand from product name: {product_name}.
                    Respond ONLY with the brand name or 'unknown' if not found.
                    Brand: """
                    
                    api_metadata = self._call_hf_api(prompt)
                    if api_metadata and 'generated_text' in api_metadata:
                        brand = api_metadata['generated_text'].strip()
                        if brand.lower() != 'unknown':
                            metadata['brand'] = brand.title()
                except Exception as e:
                    print(f"LLM API call failed: {e}")
            
            return metadata
            
        except Exception as e:
            print(f"Metadata extraction error: {e}")
            return self._fallback_metadata(product_name)
    
    def _extract_metadata_with_patterns(self, name: str, description: str = "") -> Dict:
        text = f"{name} {description}".lower()
        
        brands = [
            'samsung', 'apple', 'xiaomi', 'oneplus', 'oppo', 'vivo', 'realme',
            'nokia', 'motorola', 'lg', 'sony', 'huawei', 'honor', 'asus',
            'lenovo', 'dell', 'hp', 'acer', 'msi', 'corsair', 'logitech',
            'boat', 'jbl', 'sony', 'bose', 'sennheiser', 'nike', 'adidas',
            'puma', 'reebok', 'himalaya', 'patanjali', 'dabur', 'mamaearth'
        ]
        
        category = 'general'
        category_keywords = {
            'smartphone': ['phone', 'mobile', 'smartphone', 'android', 'ios'],
            'laptop': ['laptop', 'notebook', 'ultrabook'],
            'headphones': ['headphones', 'earphones', 'earbuds', 'headset'],
            'clothing': ['shirt', 'tshirt', 't-shirt', 'jeans', 'dress', 'shoes'],
            'beauty': ['cream', 'serum', 'moisturizer', 'shampoo', 'soap'],
            'electronics': ['charger', 'cable', 'adapter', 'speaker', 'watch']
        }
        
        brand = next((b.title() for b in brands if b in text), None)
        category = next(
            (cat for cat, keywords in category_keywords.items() 
             if any(kw in text for kw in keywords)),
            'general'
        )
        
        model = None
        model_patterns = [
            r'(\w+\s*\d+\w*)',  # Matches "Galaxy M14", "iPhone 14"
            r'(pro|plus|max|mini|lite|ultra)',
        ]
        for pattern in model_patterns:
            if match := re.search(pattern, name, re.IGNORECASE):
                model = match.group(1)
                break
        
        search_terms = list(set([
            name,
            f"{brand} {model}" if brand and model else None,
            *([model] if model else [])
        ])) if any([brand, model]) else [name]

        return {
            'brand': brand,
            'model': model,
            'category': category,
            'key_features': self._extract_features(text),
            'search_terms': [st for st in search_terms if st]
        }

    def _extract_features(self, text: str) -> List[str]:
        feature_keywords = [
            'gb', 'tb', 'mp', 'mah', 'inch', 'core', 'ghz', 'hz',
            'waterproof', 'wireless', 'bluetooth', 'wifi', 'usb',
            'fast charging', 'quick charge', 'amoled', 'oled'
        ]
        return [
            f"{kw}: {re.search(rf'\d+{kw}', text, re.I).group(0)}"
            if re.search(rf'\d+{kw}', text, re.I) else kw
            for kw in feature_keywords if kw in text
        ][:3]

    def _call_hf_api(self, prompt: str) -> Optional[Dict]:
        try:
            response = requests.post(
                f"https://api-inference.huggingface.co/models/{self.hf_model}",
                headers=self.headers,
                json={"inputs": prompt},
                timeout=10
            )
            return response.json() if response.status_code == 200 else None
        except Exception as e:
            print(f"Hugging Face API error: {e}")
            return None

    def _fallback_metadata(self, name: str) -> Dict:
        return {
            'brand': None,
            'model': None,
            'category': 'general',
            'key_features': [],
            'search_terms': [name]
        }

class MultiPlatformSearcher:
    def __init__(self):
        self.google_api_key = os.getenv('GOOGLE_API_KEY')
        self.google_cse_id = os.getenv('GOOGLE_CSE_ID')
        self.platform_configs = {
            'flipkart': {
                'site': 'flipkart.com',
                'price_pattern': r'₹\s*(\d{1,3}(?:,\d{3})*(?:\.\d{2})?)\b'
            },
            'amazon': {
                'site': 'amazon.in',
                'price_pattern': r'₹\s*(\d{1,3}(?:,\d{3})*(?:\.\d{2})?)\b'
            },
            'meesho': {
                'site': 'meesho.com',
                'price_pattern': r'₹\s*(\d{1,3}(?:,\d{3})*(?:\.\d{2})?)\b'
            }
        }

    def search_across_platforms(self, metadata: Dict, primary_product_name: str) -> List[Dict]:
        results = []
        search_queries = self._generate_search_queries(metadata, primary_product_name)
        
        for platform, config in self.platform_configs.items():
            try:
                platform_results = []
                for query in search_queries[:2]:
                    results = self._search_platform(query, config)
                    platform_results.extend(results)
                
                results.extend(self._deduplicate(platform_results)[:5])
                
            except Exception as e:
                print(f"Error searching {platform}: {e}")
        
        return self._sort_and_filter(results)

    def _generate_search_queries(self, metadata: Dict, primary_name: str) -> List[str]:
        queries = [primary_name]
        if metadata.get('brand') and metadata.get('model'):
            queries.append(f"{metadata['brand']} {metadata['model']}")
        if metadata.get('search_terms'):
            queries.extend(metadata['search_terms'][:2])
        return list(set(queries))

    def _search_platform(self, query: str, config: Dict) -> List[Dict]:
        try:
            encoded_query = quote_plus(f"{query} site:{config['site']}")
            url = f"https://www.googleapis.com/customsearch/v1?q={encoded_query}&key={self.google_api_key}&cx={self.google_cse_id}&num=5"
            
            response = requests.get(url, timeout=15)
            response.raise_for_status()
            
            return self._parse_results(response.json(), config)
        except Exception as e:
            print(f"Search error for {config['site']}: {e}")
            return []

    def _parse_results(self, data: Dict, config: Dict) -> List[Dict]:
        results = []
        for item in data.get('items', []):
            price_str = f"{item.get('title', '')} {item.get('snippet', '')}"
            price_match = re.search(config['price_pattern'], price_str)
            
            if price_match:
                try:
                    price = float(price_match.group(1).replace(',', ''))
                except ValueError:
                    continue
                
                results.append({
                    'platform': config['site'].split('.')[0].title(),
                    'title': item.get('title'),
                    'price': price,
                    'currency': '₹',
                    'url': item.get('link'),
                    'availability': self._check_availability(item.get('snippet', ''))
                })
        
        return results

    def _check_availability(self, snippet: str) -> str:
        snippet_lower = snippet.lower()
        if 'out of stock' in snippet_lower:
            return 'Out of Stock'
        if 'in stock' in snippet_lower:
            return 'In Stock'
        return 'Availability Unknown'

    def _deduplicate(self, items: List[Dict]) -> List[Dict]:
        seen = set()
        unique = []
        for item in items:
            identifier = f"{item['url']}-{item['price']}"
            if identifier not in seen:
                seen.add(identifier)
                unique.append(item)
        return unique

    def _sort_and_filter(self, items: List[Dict]) -> List[Dict]:
        return sorted(
            [item for item in items if item['price']],
            key=lambda x: x['price']
        )[:10]  # Return top 10 cheapest