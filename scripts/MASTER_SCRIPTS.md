database seeding: 
    python scripts/seed.py --quick
    quick, smart-rotate, full

# Increase batch size
python scripts/match_existing_products.py --limit 200 --no-ai
#daily job 
python jobs/daily_scrape.py --force-all

---------------------all platform
testing :
    python scripts/test_scrapers.py --platform all --query "smartphone" --standalone

---------------------individual

Amazon (Captcha & Stealth Check):
    python scripts/test_scrapers.py --platform amazon --query "iphone 15" --standalone

Flipkart (JS Extraction Check):
    python scripts/test_scrapers.py --platform flipkart --query "gaming laptop" --standalone

Nykaa (JSON-LD Check):
    python scripts/test_scrapers.py --platform nykaa --query "lipstick" --standalone

Meesho (Akamai Bypass Check):
    python scripts/test_scrapers.py --platform meesho --query "saree" --standalone





curl -X POST "https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key=YOUR_GEMINI_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "email": "patelhardik1262001@gmail.com",
    "password": "123456",
    "returnSecureToken": true
  }'
