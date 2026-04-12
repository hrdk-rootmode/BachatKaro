"""
Selector Validation & Health Checking Service
Validates CSS selectors against live HTML and provides diagnostic info

Used by admin scraper testing dashboard to verify and fix broken selectors
"""

import logging
import re
import json
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)



class SelectorValidator:
    """Validates selectors against HTML content"""

    @staticmethod
    def _parse_selector_mode(selector: str) -> Tuple[str, str]:
        """Parse selector mode from prefix. Examples: css:.card, regex:₹([0-9,]+), json:props.pageProps.products"""
        raw = (selector or "").strip()
        if not raw:
            return "css", ""

        mode_match = re.match(r"^(css|regex|json|js)\s*:(.*)$", raw, flags=re.IGNORECASE | re.DOTALL)
        if not mode_match:
            return "css", raw

        mode = mode_match.group(1).lower()
        body = (mode_match.group(2) or "").strip()
        return mode, body

    @staticmethod
    def _extract_embedded_json_blobs(html: str) -> List[Any]:
        """Extract likely JSON blobs from script tags and return parsed objects."""
        blobs: List[Any] = []
        if not html:
            return blobs

        # Explicit Next.js data node first.
        next_data_match = re.search(r'<script[^>]*id=["\']__NEXT_DATA__["\'][^>]*>(.*?)</script>', html, flags=re.IGNORECASE | re.DOTALL)
        if next_data_match:
            try:
                blobs.append(json.loads(next_data_match.group(1).strip()))
            except Exception:
                pass

        script_blocks = re.findall(r'<script[^>]*>(.*?)</script>', html, flags=re.IGNORECASE | re.DOTALL)
        for block in script_blocks[:120]:
            text = (block or "").strip()
            if not text:
                continue

            # Raw object/array JSON.
            if text.startswith("{") or text.startswith("["):
                try:
                    blobs.append(json.loads(text))
                    continue
                except Exception:
                    pass

            # JS assignment style e.g. window.__INITIAL_STATE__ = {...};
            assign_match = re.search(r'([A-Za-z0-9_.$]+)\s*=\s*([\[{].*)\s*;?\s*$', text, flags=re.DOTALL)
            if assign_match:
                candidate = (assign_match.group(2) or "").strip().rstrip(";")
                try:
                    blobs.append(json.loads(candidate))
                except Exception:
                    continue

        return blobs

    @staticmethod
    def _walk_path(obj: Any, path: str) -> List[Any]:
        """Walk a simple dot/bracket path: props.pageProps.products[0].name"""
        if obj is None or not path:
            return []

        tokens: List[str] = []
        for part in re.split(r"\.", path.strip()):
            if not part:
                continue
            idx_parts = re.split(r"\[", part)
            if idx_parts[0]:
                tokens.append(idx_parts[0])
            for idx_part in idx_parts[1:]:
                idx = idx_part.rstrip("]").strip()
                if idx:
                    tokens.append(idx)

        nodes = [obj]
        for token in tokens:
            next_nodes: List[Any] = []
            is_index = token.isdigit()
            for node in nodes:
                try:
                    if is_index and isinstance(node, list):
                        i = int(token)
                        if 0 <= i < len(node):
                            next_nodes.append(node[i])
                    elif isinstance(node, dict) and token in node:
                        next_nodes.append(node[token])
                except Exception:
                    continue
            nodes = next_nodes
            if not nodes:
                break

        flattened: List[Any] = []
        for node in nodes:
            if isinstance(node, list):
                flattened.extend(node[:20])
            else:
                flattened.append(node)
        return flattened[:50]
    
    @staticmethod
    def validate_selector_against_html(
        selector: str,
        html: str,
        max_sample_length: int = 200
    ) -> Dict[str, Any]:
        """
        Validate a CSS selector against HTML content
        
        Args:
            selector: CSS selector string to validate
            html: HTML content to validate against
            max_sample_length: Maximum length of sample text to extract
            
        Returns:
            Dict with:
            - match_count: Number of matches found
            - is_valid: Whether selector is valid
            - sample_matches: List of sample matched text (up to 3)
            - confidence: Confidence score 0-1
            - error: Error message if invalid
        """
        try:
            # Basic selector syntax validation
            if not selector or len(selector) == 0:
                return {
                    "match_count": 0,
                    "is_valid": False,
                    "sample_matches": [],
                    "confidence": 0.0,
                    "error": "Empty selector"
                }

            mode, body = SelectorValidator._parse_selector_mode(selector)
            if not body:
                return {
                    "match_count": 0,
                    "is_valid": False,
                    "sample_matches": [],
                    "confidence": 0.0,
                    "error": "Selector body is empty"
                }

            if mode == "css":
                if not SelectorValidator._is_valid_css_selector(body):
                    return {
                        "match_count": 0,
                        "is_valid": False,
                        "sample_matches": [],
                        "confidence": 0.0,
                        "error": f"Invalid CSS selector syntax: {body}"
                    }
                matches = SelectorValidator._extract_matches(body, html, max_sample_length)
            elif mode == "regex":
                matches = SelectorValidator._extract_by_regex(body, html, max_sample_length)
            elif mode == "json":
                matches = SelectorValidator._extract_by_json_path(body, html, max_sample_length)
            elif mode == "js":
                # "js:" is treated as data-path extraction from embedded JS/JSON blobs.
                matches = SelectorValidator._extract_by_json_path(body, html, max_sample_length)
            else:
                return {
                    "match_count": 0,
                    "is_valid": False,
                    "sample_matches": [],
                    "confidence": 0.0,
                    "error": f"Unsupported selector mode: {mode}"
                }
            
            match_count = len(matches)
            confidence = 1.0 if match_count > 0 else 0.0
            
            return {
                "match_count": match_count,
                "is_valid": True,
                "sample_matches": matches[:3],  # Return up to 3 samples
                "confidence": confidence,
                "selector_mode": mode,
                "error": None
            }
            
        except Exception as e:
            logger.warning(f"Selector validation error: {e}")
            return {
                "match_count": 0,
                "is_valid": False,
                "sample_matches": [],
                "confidence": 0.0,
                "error": str(e)
            }
    
    @staticmethod
    def _is_valid_css_selector(selector: str) -> bool:
        """Check if CSS selector has valid basic syntax"""
        # Reject obviously invalid selectors
        invalid_patterns = [
            r'^\s*$',  # Empty
            r'[<>]',  # HTML tags
            r'[;:{}]$',  # CSS syntax chars at end
            r'\$\{',  # Template literals
        ]
        
        for pattern in invalid_patterns:
            if re.search(pattern, selector):
                return False
        
        # Must have at least valid selector-like character
        valid_start = re.match(r'^[.#\w\[\*]', selector.lstrip())
        if not valid_start:
            return False
        
        return True
    
    @staticmethod
    def _extract_matches(
        selector: str,
        html: str,
        max_sample_length: int = 200
    ) -> List[str]:
        """
        Extract matches from HTML using simplified CSS selector parsing
        
        Since we're using regex not a full CSS parser, this handles common selectors:
        - Tag names: div, p, span, etc.
        - Classes: .classname, .class1.class2
        - IDs: #id
        - Attributes: [attr], [attr='value'], [attr*='value']
        - Descendants and children (limited support)
        """
        matches = []
        
        try:
            soup = BeautifulSoup(html or "", "lxml")
            selected = soup.select(selector)
            for node in selected[:10]:
                sample = node.get_text(" ", strip=True) or str(node.get("content") or "") or str(node.get("href") or "")
                sample = (sample or "").strip()
                if sample:
                    matches.append(sample[:max_sample_length])
        except Exception as e:
            logger.debug(f"Error extracting matches for selector '{selector}': {e}")
        
        return matches

    @staticmethod
    def _extract_by_regex(pattern: str, html: str, max_length: int) -> List[str]:
        matches: List[str] = []
        try:
            compiled = re.compile(pattern, re.IGNORECASE | re.DOTALL)
            found = compiled.findall(html or "")
            for item in found[:20]:
                if isinstance(item, tuple):
                    sample = " ".join(str(x) for x in item if x is not None)
                else:
                    sample = str(item)
                sample = sample.strip()
                if sample:
                    matches.append(sample[:max_length])
        except Exception as e:
            logger.debug(f"Regex extraction failed: {e}")
        return matches

    @staticmethod
    def _extract_by_json_path(path: str, html: str, max_length: int) -> List[str]:
        matches: List[str] = []
        clean_path = (path or "").strip()
        if not clean_path:
            return matches

        # Remove common JS roots so admins can paste simple paths.
        clean_path = re.sub(r"^(window\.)?(__NEXT_DATA__|__INITIAL_STATE__|__APOLLO_STATE__|__NUXT__|state|data)\.?", "", clean_path)
        clean_path = clean_path.lstrip(".$")

        for blob in SelectorValidator._extract_embedded_json_blobs(html):
            values = SelectorValidator._walk_path(blob, clean_path)
            for value in values:
                if isinstance(value, (dict, list)):
                    sample = json.dumps(value, ensure_ascii=False)[:max_length]
                else:
                    sample = str(value).strip()[:max_length]
                if sample:
                    matches.append(sample)
                if len(matches) >= 10:
                    return matches

        return matches
    
    @staticmethod
    def _extract_by_id(selector: str, html: str, max_length: int) -> List[str]:
        """Extract by ID selector"""
        id_match = re.search(r'#([a-zA-Z0-9_\-]+)', selector)
        if not id_match:
            return []
        
        id_value = id_match.group(1)
        pattern = rf'id=["\']?{re.escape(id_value)}["\']?[^>]*>([^<]*)'
        
        matches = re.findall(pattern, html, re.IGNORECASE)
        return [m.strip()[:max_length] for m in matches if m.strip()]
    
    @staticmethod
    def _extract_by_class(selector: str, html: str, max_length: int) -> List[str]:
        """Extract by class selector"""
        classes = re.findall(r'\.([a-zA-Z0-9_\-]+)', selector)
        if not classes:
            return []
        
        # For simplicity, search for elements containing all classes
        class_pattern = ''.join([rf'(?=.*class=["\']?[^"\']*{re.escape(c)}[^"\']*["\']?)' for c in classes])
        pattern = rf'{class_pattern}[^>]*>([^<]*)'
        
        matches = re.findall(pattern, html, re.IGNORECASE)
        return [m.strip()[:max_length] for m in matches if m.strip()]
    
    @staticmethod
    def _extract_by_attribute(selector: str, html: str, max_length: int) -> List[str]:
        """Extract by attribute selector"""
        # Handle [attr='value'], [attr*='value'], [attr], etc.
        attr_pattern = r'\[([a-zA-Z0-9_\-\*]+)(?:[*^$]?=)?["\']?([^"\']*)["\']?\]'
        attr_matches = re.findall(attr_pattern, selector)
        
        matches = []
        for attr_name, attr_value in attr_matches:
            if not attr_value:
                # Just check for attribute existence
                pattern = rf'{re.escape(attr_name)}(?:\s|=|>)'
            else:
                # Check for attribute value
                pattern = rf'{re.escape(attr_name)}=["\']?{re.escape(attr_value)}["\']?'
            
            elem_pattern = rf'{pattern}[^>]*>([^<]*)'
            found = re.findall(elem_pattern, html, re.IGNORECASE)
            matches.extend([m.strip()[:max_length] for m in found if m.strip()])
        
        return matches[:10]  # Limit to 10 matches
    
    @staticmethod
    def _extract_by_tag(selector: str, html: str, max_length: int) -> List[str]:
        """Extract by tag selector"""
        # Simple tag extraction - not handling complex selectors
        tag_match = re.match(r'^([a-zA-Z0-9_\-]+)', selector)
        if not tag_match:
            return []
        
        tag = tag_match.group(1)
        pattern = rf'<{tag}\b[^>]*>([^<]*?)</{tag}>'
        
        matches = re.findall(pattern, html, re.IGNORECASE | re.DOTALL)
        return [m.strip()[:max_length] for m in matches if m.strip()]
    
    @staticmethod
    async def validate_selectors_batch(
        selectors: Dict[str, str],
        html: str
    ) -> Dict[str, Dict[str, Any]]:
        """
        Validate multiple selectors against HTML
        
        Args:
            selectors: Dict of {field_name: selector_string}
            html: HTML content to validate against
            
        Returns:
            Dict of {field_name: validation_result}
        """
        results = {}
        
        for field_name, selector in selectors.items():
            results[field_name] = SelectorValidator.validate_selector_against_html(
                selector,
                html
            )
        
        return results
    
    @staticmethod
    def get_selector_health(validation_result: Dict[str, Any]) -> str:
        """
        Determine selector health status from validation result
        
        Returns:
            "working" - matches found, high confidence
            "broken" - no matches
            "untested" - no validation result
        """
        if not validation_result:
            return "untested"
        
        match_count = validation_result.get("match_count", 0)
        confidence = validation_result.get("confidence", 0.0)
        
        if match_count > 0 and confidence >= 0.5:
            return "working"
        elif match_count == 0:
            return "broken"
        else:
            return "uncertain"


class LastScrapedValueFinder:
    """Helper to find last scraped values from database"""
    
    @staticmethod
    async def get_last_scraped_values(
        db_session,
        platform_name: str,
        limit: int = 5
    ) -> List[Dict[str, Any]]:
        """
        Get last scraped values for a platform
        
        Args:
            db_session: Database session
            platform_name: Platform to query
            limit: Number of recent listings to check
            
        Returns:
            List of last scraped values by field
        """
        from app.models import ProductListing, Platform
        from sqlalchemy import desc, select
        from sqlalchemy.orm import selectinload
        
        try:
            # Get platform
            result = await db_session.execute(
                select(Platform).where(Platform.name == platform_name)
            )
            platform = result.scalar_one_or_none()
            
            if not platform:
                return []
            
            # Get recent listings for this platform
            result = await db_session.execute(
                select(ProductListing)
                .options(selectinload(ProductListing.product))
                .where(ProductListing.platform_id == platform.id)
                .where(ProductListing.last_scraped.isnot(None))
                .order_by(desc(ProductListing.last_scraped))
                .limit(limit)
            )
            listings = result.scalars().all()
            
            # Extract values from listings
            last_values = []
            for listing in listings:
                last_values.append({
                    "field_name": "title",
                    "value": listing.product.title if listing.product else None,
                    "extraction_method": listing.extraction_method,
                    "confidence": listing.extraction_confidence,
                    "last_scraped_at": listing.last_scraped,
                    "source": "db"
                })
                
                last_values.append({
                    "field_name": "current_price",
                    "value": str(listing.current_price) if listing.current_price else None,
                    "extraction_method": listing.extraction_method,
                    "confidence": listing.extraction_confidence,
                    "last_scraped_at": listing.last_scraped,
                    "source": "db"
                })
                
                last_values.append({
                    "field_name": "image_url",
                    "value": listing.product.image_url if listing.product else None,
                    "extraction_method": listing.extraction_method,
                    "confidence": listing.extraction_confidence,
                    "last_scraped_at": listing.last_scraped,
                    "source": "db"
                })
                
                if last_values:
                    break  # Just get from most recent
            
            return last_values
            
        except Exception as e:
            logger.error(f"Error getting last scraped values: {e}")
            return []
