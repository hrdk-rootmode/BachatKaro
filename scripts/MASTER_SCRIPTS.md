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





### 4A) Dual Catalog Strategy (Recommended)
Use two lanes:
- HOT groups: frequent refresh for user-facing freshness
- DEEP groups: slower background expansion for long-tail coverage

HOT groups (run every 1-2 hours, low noise):
python scripts/seed.py --catalog-group hot_mobiles --catalog-path scripts/master_catalog.json --limit 120 --catalog-per-query 1 --platform-timeout 55 --query-interval 9 --cooldown-buffer 14 --max-errors 8 --max-rate-limit-strikes 3 --max-empty-queries 8 --no-ai --no-cross-match

python scripts/seed.py --catalog-group hot_laptops --catalog-path scripts/master_catalog.json --limit 100 --catalog-per-query 1 --platform-timeout 55 --query-interval 10 --cooldown-buffer 16 --max-errors 8 --max-rate-limit-strikes 3 --max-empty-queries 8 --no-ai --no-cross-match

python scripts/seed.py --catalog-group hot_mobile_accessories --catalog-path scripts/master_catalog.json --limit 110 --catalog-per-query 1 --platform-timeout 50 --query-interval 10 --cooldown-buffer 16 --max-errors 8 --max-rate-limit-strikes 3 --max-empty-queries 8 --no-ai --no-cross-match

python scripts/seed.py --catalog-group hot_fashion --catalog-path scripts/master_catalog.json --limit 120 --catalog-per-query 1 --platform-timeout 55 --query-interval 10 --cooldown-buffer 16 --max-errors 8 --max-rate-limit-strikes 3 --max-empty-queries 8 --no-ai --no-cross-match

python scripts/seed.py --catalog-group hot_home_kitchen --catalog-path scripts/master_catalog.json --limit 100 --catalog-per-query 1 --platform-timeout 50 --query-interval 9 --cooldown-buffer 14 --max-errors 8 --max-rate-limit-strikes 3 --max-empty-queries 8 --no-ai --no-cross-match

python scripts/seed.py --catalog-group hot_books --catalog-path scripts/master_catalog.json --limit 80 --catalog-per-query 1 --platform-timeout 45 --query-interval 8 --cooldown-buffer 12 --max-errors 8 --max-rate-limit-strikes 2 --max-empty-queries 8 --no-ai --no-cross-match




DEEP groups (run in free windows / night):
python scripts/seed.py --catalog-group deep_mobiles --catalog-path scripts/master_catalog.json --limit 180 --catalog-per-query 1 --platform-timeout 60 --query-interval 12 --cooldown-buffer 20 --max-errors 9 --max-rate-limit-strikes 3 --max-empty-queries 8 --no-ai --no-cross-match

python scripts/seed.py --catalog-group deep_laptops --catalog-path scripts/master_catalog.json --limit 150 --catalog-per-query 1 --platform-timeout 60 --query-interval 12 --cooldown-buffer 20 --max-errors 9 --max-rate-limit-strikes 3 --max-empty-queries 8 --no-ai --no-cross-match

python scripts/seed.py --catalog-group deep_mobile_accessories --catalog-path scripts/master_catalog.json --limit 170 --catalog-per-query 1 --platform-timeout 55 --query-interval 12 --cooldown-buffer 20 --max-errors 9 --max-rate-limit-strikes 3 --max-empty-queries 8 --no-ai --no-cross-match

python scripts/seed.py --catalog-group deep_fashion --catalog-path scripts/master_catalog.json --limit 160 --catalog-per-query 1 --platform-timeout 60 --query-interval 12 --cooldown-buffer 20 --max-errors 9 --max-rate-limit-strikes 3 --max-empty-queries 8 --no-ai --no-cross-match

python scripts/seed.py --catalog-group deep_home_kitchen --catalog-path scripts/master_catalog.json --limit 140 --catalog-per-query 1 --platform-timeout 55 --query-interval 11 --cooldown-buffer 18 --max-errors 9 --max-rate-limit-strikes 3 --max-empty-queries 8 --no-ai --no-cross-match

python scripts/seed.py --catalog-group deep_books --catalog-path scripts/master_catalog.json --limit 100 --catalog-per-query 1 --platform-timeout 50 --query-interval 9 --cooldown-buffer 16 --max-errors 9 --max-rate-limit-strikes 2 --max-empty-queries 8 --no-ai --no-cross-match

Suggested 24-hour rotation (simple):
1. Hourly: run one HOT group (round robin)
2. Every 4-6 hours: run cross-platform miner batch
3. Continuous: run daily scrape for freshness
4. Night slots: run one DEEP group per slot


python scripts/seed.py --catalog-group hot_mobile_accessories --catalog-path scripts/master_catalog.json --limit 120 --catalog-per-query 1 --no-ai --no-cross-match




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


1. If you run only `python jobs/daily_scrape.py`:
- It runs one cycle and exits.
- It uses smart due-based selection now.
- It respects configured cap (default from settings, currently 500 unless changed).
- It updates `next_scrape_at` for processed listings.

2. If you want continuous running with no limit:
- Use:
`python jobs/daily_scrape.py --continuous --interval-minutes 20 --max-products 80`
- This loops forever (no max cycle cap).
- It will sleep 20 minutes between cycles and keep refreshing due products with lower burst risk.

3. If you want continuous plus force-all behavior each cycle (usually heavier):
- Use:
`python jobs/daily_scrape.py --continuous --force-all --interval-minutes 10`
- Recommended only for catch-up periods, not normal steady state.

4. For your goal (stable live-ish updates), best command:
`python jobs/daily_scrape.py --continuous --interval-minutes 20 --max-products 80`

5. To stop no-limit mode:
- Press `Ctrl + C` in that terminal.

Mostly yes, with these conditions:

1. Platform coverage:
- It only covers platforms marked active in DB.
- If a platform is paused/disabled, it will be skipped.

2. Product coverage:
- It covers products that are “due” (based on next_scrape_at / policy), not every product every cycle.
- Over multiple cycles, all due listings get picked progressively.

3. Fairness:
- Watchlist and higher-priority items are processed first.
- Normal items still get turns, but may take more cycles depending on max-products and interval.

4. To ensure full sweep regularly:
- Run continuous mode with enough batch size, for example:
python jobs/daily_scrape.py --continuous --interval-minutes 10 --max-products 300
- Optionally run a periodic catch-up:
python jobs/daily_scrape.py --force-all --max-products 500

5. What can still prevent full coverage:
- Platform inactive flag
- Persistent scrape failures/rate limits
- Very low max-products compared to total listing count

If you want, I can add a “coverage report” log per cycle (total listings, due listings, processed, remaining by platform) so you can verify 100% coverage health continuously.



BUILD APK : 
 Push-Location "C:\PROJECT\collage\dealhunt-app\android"; $env:JAVA_HOME='C:\Program Files\Microsoft\jdk-17.0.18.8-hotspot'; $env:PATH="$env:JAVA_HOME\bin;$env:PATH"; $env:NODE_ENV='production'; .\gradlew.bat :app:installRelease -x lintVitalAnalyzeRelease --no-daemon; Pop-Location

Install and Lunch in Device: 
$adb='C:\Users\patel\AppData\Local\Android\Sdk\platform-tools\adb.exe'; & $adb shell am force-stop com.dealhunt.app; & $adb shell monkey -p com.dealhunt.app -c android.intent.category.LAUNCHER 1