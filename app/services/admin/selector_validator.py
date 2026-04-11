"""
Selector Validation & Health Checking Service
Validates CSS selectors against live HTML and provides diagnostic info

Used by admin scraper testing dashboard to verify and fix broken selectors
"""

import logging
import re
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime

logger = logging.getLogger(__name__)



class SelectorValidator:
    """Validates selectors against HTML content"""
    
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
            
            # Try to parse selector (simple regex-based validation)
            if not SelectorValidator._is_valid_css_selector(selector):
                return {
                    "match_count": 0,
                    "is_valid": False,
                    "sample_matches": [],
                    "confidence": 0.0,
                    "error": f"Invalid CSS selector syntax: {selector}"
                }
            
            # Extract matches using regex (simplified CSS selector parsing)
            matches = SelectorValidator._extract_matches(selector, html, max_sample_length)
            
            match_count = len(matches)
            confidence = 1.0 if match_count > 0 else 0.0
            
            return {
                "match_count": match_count,
                "is_valid": True,
                "sample_matches": matches[:3],  # Return up to 3 samples
                "confidence": confidence,
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
            # Handle basic selector types
            if selector.startswith('#'):
                # ID selector
                matches = SelectorValidator._extract_by_id(selector, html, max_sample_length)
            
            elif selector.startswith('.'):
                # Class selector
                matches = SelectorValidator._extract_by_class(selector, html, max_sample_length)
            
            elif '[' in selector and ']' in selector:
                # Attribute selector
                matches = SelectorValidator._extract_by_attribute(selector, html, max_sample_length)
            
            else:
                # Tag selector or combined
                matches = SelectorValidator._extract_by_tag(selector, html, max_sample_length)
            
        except Exception as e:
            logger.debug(f"Error extracting matches for selector '{selector}': {e}")
        
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
