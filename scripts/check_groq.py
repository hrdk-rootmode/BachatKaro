"""
Test Groq API connectivity and functionality
Run: python scripts/check_groq.py
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import asyncio
from decimal import Decimal

async def test_groq_api():
    """Test Groq API connectivity"""
    print("🔍 Testing Groq API...\n")
    
    # Check if API keys are configured
    try:
        from app.core.config import settings
        keys = [
            settings.GROQ_API_KEY_MAIN,
            settings.GROQ_API_KEY_SEARCH,
            settings.GROQ_API_KEY_HEALING,
            settings.GROQ_API_KEY_CHAT
        ]
        valid_keys = [k for k in keys if k and not k.startswith("gsk_your")]
        print(f"✅ Found {len(valid_keys)}/4 GROQ API keys")
        for i, name in enumerate(["MAIN", "SEARCH", "HEALING", "CHAT"]):
            status = "✅" if keys[i] and not keys[i].startswith("gsk_your") else "❌"
            print(f"   {status} GROQ_API_KEY_{name}")
        if len(valid_keys) == 0:
            print("\n❌ No valid Groq API keys configured")
            print("   Set actual keys in .env file (not placeholder values)")
            return False
    except Exception as e:
        print(f"❌ Error loading settings: {e}")
        return False
    
    # Test AI client
    try:
        from app.services.ai.groq_client import groq_client, GroqFeature
        print(f"\n✅ GroqClient imported successfully")
        print(f"   Model: {groq_client.model}")
        print(f"   Daily limit: {groq_client.daily_limit}")
        for feature, key in groq_client.api_keys.items():
            status = "✅" if key else "❌"
            print(f"   {status} {feature.value}: {'Set' if key else 'Missing'}")
    except Exception as e:
        print(f"\n❌ Error importing GroqClient: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    # Test simple product processing
    print("\n📝 Testing product processing...")
    try:
        from app.services.scraper.base import ProductData
        
        # Create sample product data
        product_data = ProductData(
            external_id="test123",
            title="iPhone 15 Pro 256GB Blue Titanium",
            current_price=Decimal("79900"),
            product_url="https://example.com/iphone",
            platform_name="test",
            brand="Apple",
            category="electronics"
        )
        
        # Process with AI
        result = await groq_client.process_product(product_data)
        
        if result and result.get("essence"):
            print(f"✅ AI processing successful!")
            print(f"   Essence: {result.get('essence')}")
            print(f"   Tags: {result.get('tags', [])}")
            print(f"   Quality Score: {result.get('quality_score')}")
            print(f"   Category: {result.get('category')}")
            return True
        else:
            print(f"⚠️  AI returned empty result")
            return False
            
    except Exception as e:
        print(f"❌ Error processing product: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """Run test"""
    print("=" * 60)
    print("🚀 Groq API Test")
    print("=" * 60)
    
    try:
        result = asyncio.run(test_groq_api())
    except Exception as e:
        print(f"❌ Test crashed: {e}")
        import traceback
        traceback.print_exc()
        result = False
    
    print("\n" + "=" * 60)
    if result:
        print("✅ Groq API is working!")
    else:
        print("❌ Groq API test failed")
    print("=" * 60)
    
    return 0 if result else 1

if __name__ == "__main__":
    exit(main())
