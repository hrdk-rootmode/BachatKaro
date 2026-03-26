"""
Simple DB Inspector - Direct Query
Shows record counts from all tables
"""
import asyncio
import os
import sys
from sqlalchemy import text, create_engine
from dotenv import load_dotenv

# Load environment
load_dotenv()

def inspect_database_sync():
    """Check data availability using synchronous SQLAlchemy"""
    
    DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost/dealhunt")
    # Convert async URL to sync
    DATABASE_URL = DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://")
    
    try:
        engine = create_engine(DATABASE_URL, echo=False)
        
        print("\n" + "="*80)
        print("🔍 DATABASE INSPECTION - DealHunt")
        print("="*80 + "\n")
        
        # List of tables to check
        tables = [
            "platforms",
            "products",
            "product_listings",
            "price_history",
            "users",
            "watchlist",
            "subscriptions",
            "promotions",
            "analytics"
        ]
        
        total_records = 0
        data_summary = {}
        
        for table in tables:
            conn = engine.connect()
            try:
                # Get count
                result = conn.execute(text(f"SELECT COUNT(*) FROM {table}"))
                count = result.scalar()
                total_records += count
                data_summary[table] = count
                
                emoji = "📱" if table == "platforms" else \
                        "📦" if table == "products" else \
                        "💰" if table == "product_listings" else \
                        "📈" if table == "price_history" else \
                        "👥" if table == "users" else \
                        "⭐" if table == "watchlist" else \
                        "💳" if table == "subscriptions" else \
                        "📢" if table == "promotions" else \
                        "📊"
                
                status = "✅" if count > 0 else "⚠️"
                print(f"{emoji} {table.upper():20} | {status} {count:6,d} records")
                
            except Exception as e:
                print(f"⚠️  {table.upper():20} | ⏭️ (Table not created yet)")
            finally:
                conn.close()
        
        print("-" * 80)
        print(f"📊 TOTAL RECORDS ACROSS EXISTING TABLES: {total_records:,d}")
        print("="*80 + "\n")
        
        # =====================================================================
        # SAMPLE DATA FROM KEY TABLES
        # =====================================================================
        
        print("📋 SAMPLE DATA:\n")
        
        conn = engine.connect()
        
        try:
            # Products sample
            products_count = data_summary.get("products", 0)
            if products_count == 0:
                print("❌ PRODUCTS: 0 products")
                print("   → Database is EMPTY - need to seed data!\n")
            else:
                print(f"✅ PRODUCTS: {products_count:,d} total products\n")
                result = conn.execute(text(
                    "SELECT id, title, price_inr, rating FROM products LIMIT 3"
                ))
                print("   First 3 products:")
                for i, row in enumerate(result, 1):
                    title = row[1][:50] + "..." if len(row[1]) > 50 else row[1]
                    print(f"   {i}. {title}")
                    print(f"      Price: ₹{row[2]:,d} | Rating: {row[3]:.1f}⭐\n")
        except Exception as e:
            print(f"Error reading products: {e}\n")
        
        try:
            # Listings sample
            listings_count = data_summary.get("product_listings", 0)
            if listings_count == 0:
                print("❌ LISTINGS: 0 listings (products not linked to platforms)")
            else:
                print(f"✅ LISTINGS: {listings_count:,d} listings (product on multiple platforms)\n")
                result = conn.execute(text("""
                    SELECT p.name, COUNT(*) as count 
                    FROM product_listings pl 
                    JOIN platforms p ON pl.platform_id = p.id 
                    GROUP BY p.name
                    ORDER BY count DESC
                """))
                print("   Breakdown by platform:")
                for row in result:
                    print(f"     • {row[0]:15s} → {row[1]:3,d} listings")
                print()
        except Exception as e:
            print(f"Error reading listings: {e}\n")
        
        try:
            # Price history sample
            history_count = data_summary.get("price_history", 0)
            if history_count == 0:
                print("❌ PRICE_HISTORY: 0 records")
            else:
                print(f"✅ PRICE_HISTORY: {history_count:,d} records (daily pricing tracked!)\n")
                # Get date range
                result = conn.execute(text("""
                    SELECT MIN(recorded_date), MAX(recorded_date) 
                    FROM price_history
                """))
                min_date, max_date = result.first()
                print(f"   Date Range: {min_date} → {max_date}")
                print()
        except Exception as e:
            print(f"Error reading history: {e}\n")
        
        conn.close()
        
        print("="*80)
        print("🎯 ANALYSIS & NEXT STEPS:")
        print("="*80)
        
        products_count = data_summary.get("products", 0)
        
        if products_count == 0:
            print("""
✅ ISSUE: Database is EMPTY!

ACTION REQUIRED:
1. Run seeding script:
   cd backend
    python scripts/seed.py --quick

2. This will:
   • Scrape 4 real products
   • Auto-find them on other platforms
   • Generate price history
   • Populate your database

3. Then restart frontend to see data!
""")
        else:
            listings = data_summary.get("product_listings", 0)
            history = data_summary.get("price_history", 0)
            
            print(f"""
✅ DATABASE HAS DATA!

📊 Summary:
   • {products_count:,d} products loaded
   • {listings} cross-platform listings
   • {history:,d} price history records
   
If products STILL not showing on app:

🔧 TROUBLESHOOTING:

1. Test Backend API directly:
   curl "http://localhost:8000/api/v1/products?limit=5" \\
     -H "Authorization: Bearer test"
   
   Should return JSON with products
   
2. Check Network in Browser Inspector:
   Open app → Right-click → Inspect → Network tab
   Look for API requests - any errors?
   
3. Clear App Cache:
   Android: Settings → Apps → DealHunt → Clear Cache
   iOS: Settings → General → iPhone Storage → DealHunt → Offload
   
4. Restart Everything:
   • Kill backend: Ctrl+C
   • Kill frontend: Ctrl+C
   • Restart: python run_dev.py (backend)
   • Restart: npm expo start (frontend)
   
5. Check Frontend Code:
   ProductDetailScreen.jsx line 50-100
   Is it properly parsing API response?
""")
        
    except Exception as e:
        print(f"❌ Database Connection Error: {e}")
        print(f"   Check DATABASE_URL in your .env file")
        sys.exit(1)

if __name__ == "__main__":
    inspect_database_sync()
