#!/bin/bash
# Save as: verify_files.sh
# Run: chmod +x verify_files.sh && ./verify_files.sh

echo "🔍 DealHunt Backend - File Verification"
echo "========================================"

# Define all required files
FILES=(
    "main.py"
    "requirements.txt"
    ".env"
    "app/__init__.py"
    "app/models.py"
    "app/schemas.py"
    "app/core/__init__.py"
    "app/core/config.py"
    "app/core/database.py"
    "app/core/redis_client.py"
    "app/core/security.py"
    "app/api/__init__.py"
    "app/api/deps.py"
    "app/api/v1/__init__.py"
    "app/api/v1/auth.py"
    "app/api/v1/search.py"
    "app/api/v1/products.py"
    "app/api/v1/watchlist.py"
    "app/api/v1/streak.py"
    "app/api/v1/subscription.py"
    "app/api/v1/admin.py"
    "app/services/__init__.py"
    "app/services/analytics.py"
    "app/services/ai/__init__.py"
    "app/services/ai/groq_client.py"
    "app/services/ai/product_matcher.py"
    "app/services/payments/__init__.py"
    "app/services/payments/razorpay.py"
    "app/services/scraper/__init__.py"
    "app/services/scraper/base.py"
    "app/services/scraper/factory.py"
    "app/services/scraper/self_healing.py"
    "app/services/scraper/rate_limiter.py"
    "app/services/scraper/browser.py"
    "app/services/scraper/url_detector.py"
    "app/services/scraper/generic_scraper.py"
    "app/services/scraper/cross_platform_matcher.py"
    "app/services/scraper/search_queue.py"
    "platforms/__init__.py"
    "platforms/amazon.py"
    "platforms/flipkart.py"
    "platforms/meesho.py"
    "platforms/myntra.py"
)

MISSING=0
FOUND=0

for file in "${FILES[@]}"; do
    if [ -f "$file" ]; then
        echo "✅ $file"
        ((FOUND++))
    else
        echo "❌ MISSING: $file"
        ((MISSING++))
    fi
done

echo ""
echo "========================================"
echo "📊 Results: $FOUND found, $MISSING missing"

if [ $MISSING -eq 0 ]; then
    echo "🎉 All files present!"
else
    echo "⚠️  Please create missing files before continuing"
fi