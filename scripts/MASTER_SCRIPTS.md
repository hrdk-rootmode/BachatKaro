# DealHunt Master Runbook (Hardened)

## 1) Quick smoke runs
python scripts/seed.py --quick
python jobs/daily_scrape.py --force-all

## 2) Scraper diagnostics
All platforms:
python scripts/test_scrapers.py --platform all --query "smartphone" --standalone

Individual platforms:
python scripts/test_scrapers.py --platform amazon --query "iphone 15" --standalone
python scripts/test_scrapers.py --platform flipkart --query "gaming laptop" --standalone
python scripts/test_scrapers.py --platform nykaa --query "lipstick" --standalone
python scripts/test_scrapers.py --platform meesho --query "saree" --standalone

## 3) Selector healing workflow (when extraction fails)
Use this when logs show:
- "All healing tiers failed for product_title/product_price/product_url"
- repeated "No products found" for a platform/category

python scripts/fix_platforms.py --diagnose --platform amazon
python scripts/fix_platforms.py --heal --platform amazon
python scripts/fix_platforms.py --apply --platform amazon

Re-test after healing:
python scripts/test_scrapers.py --platform amazon --query "men tshirt" --standalone

## 4) Recommended catalog seeding flow (429-proof bulk mode)
Safeguards included:
- --max-errors 9
- --max-rate-limit-strikes 3
- --max-empty-queries 8
- query pacing and cooldown
- --no-ai (disables Groq enrichment)
- --no-cross-match (disables in-seed cross-platform AI/matcher calls)

PowerShell (Windows) encoding guard before long runs:
$env:PYTHONIOENCODING='utf-8'; $env:PYTHONUTF8='1'

Mobiles:
python scripts/seed.py --catalog-group mobiles --catalog-path scripts/master_catalog.json --limit 180 --catalog-per-query 1 --platform-timeout 60 --query-interval 12 --cooldown-buffer 20 --max-errors 9 --max-rate-limit-strikes 3 --max-empty-queries 8 --no-ai --no-cross-match

Tablets:
python scripts/seed.py --catalog-group tablets --catalog-path scripts/master_catalog.json --limit 140 --catalog-per-query 1 --platform-timeout 60 --query-interval 11 --cooldown-buffer 18 --max-errors 9 --max-rate-limit-strikes 3 --max-empty-queries 8 --no-ai --no-cross-match

Laptops:
python scripts/seed.py --catalog-group laptops --catalog-path scripts/master_catalog.json --limit 160 --catalog-per-query 1 --platform-timeout 60 --query-interval 12 --cooldown-buffer 20 --max-errors 9 --max-rate-limit-strikes 3 --max-empty-queries 8 --no-ai --no-cross-match

Mobile accessories:
python scripts/seed.py --catalog-group mobile_accessories --catalog-path scripts/master_catalog.json --limit 180 --catalog-per-query 1 --platform-timeout 55 --query-interval 12 --cooldown-buffer 20 --max-errors 9 --max-rate-limit-strikes 3 --max-empty-queries 8 --no-ai --no-cross-match

Laptop accessories:
python scripts/seed.py --catalog-group laptop_accessories --catalog-path scripts/master_catalog.json --limit 120 --catalog-per-query 1 --platform-timeout 55 --query-interval 12 --cooldown-buffer 20 --max-errors 9 --max-rate-limit-strikes 3 --max-empty-queries 8 --no-ai --no-cross-match

Fashion:
python scripts/seed.py --catalog-group fashion --catalog-path scripts/master_catalog.json --limit 180 --catalog-per-query 1 --platform-timeout 60 --query-interval 12 --cooldown-buffer 20 --max-errors 9 --max-rate-limit-strikes 3 --max-empty-queries 8 --no-ai --no-cross-match

Home & Kitchen:
python scripts/seed.py --catalog-group home_kitchen --catalog-path scripts/master_catalog.json --limit 180 --catalog-per-query 1 --platform-timeout 55 --query-interval 10 --cooldown-buffer 18 --max-errors 9 --max-rate-limit-strikes 3 --max-empty-queries 8 --no-ai --no-cross-match

Books:
python scripts/seed.py --catalog-group books --catalog-path scripts/master_catalog.json --limit 120 --catalog-per-query 1 --platform-timeout 50 --query-interval 9 --cooldown-buffer 16 --max-errors 9 --max-rate-limit-strikes 2 --max-empty-queries 8 --no-ai --no-cross-match

After bulk ingest finishes, do matching in a separate pass:
python scripts/match_existing_products.py --limit 200 --no-ai

## 5) Post-seed quality and backfill
python scripts/check_quality.py --detailed
python scripts/fix_data.py --fix-subcategories --limit 2000
python scripts/fix_data.py --fix-images --limit 2000

## 6) Match existing products in larger batches
python scripts/match_existing_products.py --limit 200 --no-ai

## 7) Notes on common log patterns
"Rejected by quality gate: Title too short":
- Usually means broken extraction from that platform/query page.
- With current seed guards, repeated empty/unsaved queries auto-skip the platform.
- Run selector healing workflow for that platform and retry.

"No eligible cross-platform matches":
- Not always an error; means no safe same-variant match passed filters.
- Keep seeding source products and run matching separately later if needed.