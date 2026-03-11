# 📋 Jobs System Architecture Overview

## 🎯 **Job Scripts Directory Structure & Connections**

### **🗂️ Core Job Files**
```
jobs/
├── daily_scrape.py              # Main price update job
├── daily_scrape_trending.py     # Trending products scraper  
├── load_trending_redis.py       # Redis cache loader
├── scheduler.py                 # Central scheduler (APScheduler)
├── check_price_alerts.py        # Price drop notifications
├── send_streak_reminders.py     # Gamification reminders
├── sync_subscriptions.py        # Google Play subscription sync
├── monthly_archive.py           # Data archival
└── seed_products.py             # Database seeder
```

---

## 🔗 **Connected Files & Dependencies**

### **📦 Core System Files**
| **File** | **Path** | **Role in Jobs** |
|----------|----------|------------------|
| **Database Models** | `app/models.py` | Defines all tables: Product, ProductListing, Platform, User, UserWatchlist, SystemLog, PriceHistory, Transaction, etc. |
| **Database Connection** | `app/core/database.py` | Provides `async_session_maker` for all DB operations |
| **Configuration** | `app/core/config.py` | Environment variables, API keys, database URLs |
| **Redis Client** | `app/core/redis_client.py` | Caching, session storage, trending products cache |

### **🤖 AI & Scraping Services**
| **File** | **Path** | **Role in Jobs** |
|----------|----------|------------------|
| **Groq AI Client** | `app/services/ai/groq_client.py` | Product enrichment, essence generation, tag creation, selector healing |
| **Scraper Factory** | `app/services/scraper/factory.py` | Auto-discovers and manages all platform scrapers |
| **Platform Handlers** | `platforms/*.py` | Individual scrapers: amazon.py, flipkart.py, myntra.py, nykaa.py, croma.py, meesho.py |
| **Self-Healing Engine** | `app/services/scraper/self_healing.py` | Auto-fixes broken selectors using AI |
| **URL Detector** | `app/services/scraper/url_detector.py` | Detects platform from URLs |

---

## 🕐 **Job Schedule & Dependencies**

### **📅 Daily Schedule (IST)**
```
├─ 2:00 AM  → daily_scrape.py              # Update existing product prices
├─ 2:30 AM  → daily_scrape_trending.py     # Add new trending products  
├─ 3:00 AM  → seed_products.py             # Database seeding (rotation)
├─ 5:00 AM  → load_trending_redis.py       # Cache trending products
├─ 8:00 AM  → check_price_alerts.py        # Price drop notifications
├─ 8:00 PM  → send_streak_reminders.py     # Gamification reminders
├─ Every Hour → sync_subscriptions.py      # Google Play sync
└─ 1st of Month → monthly_archive.py       # Data archival
```

### **🔄 Job Dependencies Flow**
```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│ daily_scrape.py │ →  │ PriceHistory     │ →  │ UserWatchlist   │
│ (Price Updates) │    │ (New Records)    │    │ (Alerts Check) │
└─────────────────┘    └──────────────────┘    └─────────────────┘
         ↓                       ↓                       ↓
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│ ProductListing  │ ←  │ daily_scrape_    │ ←  │ load_trending_  │
│ (Updated Prices)│    │ trending.py      │    │ redis.py        │
└─────────────────┘    │ (New Products)   │    │ (Cache Refresh) │
         ↓               └──────────────────┘    └─────────────────┘
┌─────────────────┐              ↓                       ↓
│ SystemLog       │ ←────────────┘              ┌─────────────────┐
│ (Job Tracking)  │                               │ Redis Cache     │
└─────────────────┘                               │ (Fast Access)   │
                                                  └─────────────────┘
```

---

## 📊 **Detailed Job Information**

### **1. daily_scrape.py** - Price Update Engine
**Purpose**: Update prices for existing products
**Key Dependencies**:
- `app/models.py` → Product, ProductListing, PriceHistory
- `app/core/database.py` → async_session_maker
- `app/services/scraper/factory.py` → get_platform_handler()
**Process**:
1. Get watchlisted products + products needing updates
2. Group by platform for rate limiting
3. Scrape current prices
4. Update ProductListing table
5. Create PriceHistory records
6. Log to SystemLog

### **2. daily_scrape_trending.py** - Trending Products Hunter
**Purpose**: Add new trending products from all platforms
**Key Dependencies**:
- `app/services/ai/groq_client.py` → AI enrichment
- `app/services/scraper/factory.py` → Platform handlers
- `app/core/redis_client.py` → Cache results
- `app/services/scraper/url_detector.py` → URL detection
**Process**:
1. Get trending products from each platform
2. AI enrichment (essence, tags, quality_score)
3. Cross-platform deduplication
4. Save to Product & ProductListing tables
5. Cache in Redis

### **3. load_trending_redis.py** - Cache Preloader
**Purpose**: Pre-cache trending products for fast API access
**Key Dependencies**:
- `app/core/redis_client.py` → Main caching
- `app/models.py` → Product queries
**Process**:
1. Query top 50 trending products
2. Format for API consumption
3. Store in Redis with 24h TTL
4. Create category-specific caches

### **4. scheduler.py** - Central Orchestrator
**Purpose**: Manage all scheduled jobs using APScheduler
**Key Dependencies**:
- `apscheduler` → Job scheduling library
- `pytz` → Timezone handling (IST)
**Jobs Managed**:
- All daily/weekly/monthly jobs
- Manual job triggering
- Health monitoring
- Graceful shutdown

### **5. check_price_alerts.py** - Price Drop Notifications
**Purpose**: Notify users when watched products drop in price
**Key Dependencies**:
- `app/models.py` → UserWatchlist, ProductListing
- `app/core/redis_client.py` → Notification queue
**Process**:
1. Get all active watchlists
2. Check current vs target prices
3. Queue notifications for drops
4. Update alert history

### **6. send_streak_reminders.py** - Gamification
**Purpose**: Remind users to maintain daily check-in streaks
**Key Dependencies**:
- `app/models.py` → User, streak_data
- Notification system (email/push)
**Process**:
1. Find users who haven't checked in today
2. Calculate streak risk level
3. Send personalized reminders
4. Track reminder effectiveness

### **7. sync_subscriptions.py** - Payment Integration
**Purpose**: Sync Google Play subscription status
**Key Dependencies**:
- `app/models.py` → Transaction, User
- Google Play API (mock/real)
**Process**:
1. Get active subscriptions
2. Verify with Google Play
3. Update subscription status
4. Handle renewals/expirations

### **8. monthly_archive.py** - Data Management
**Purpose**: Archive old data to maintain performance
**Key Dependencies**:
- `app/models.py` → All tables
- File system for archives
**Process**:
1. Export old data to CSV/GZIP
2. Delete from database
3. Create archive manifest
4. Update statistics

### **9. seed_products.py** - Database Population
**Purpose**: Intelligent product seeding with rotation
**Key Dependencies**:
- `app/services/ai/groq_client.py` → Product enrichment
- `app/services/scraper/factory.py` → Scraping
- `app/models.py` → Product storage
**Process**:
1. Rotate through categories/platforms
2. Scrape trending products
3. AI enrich new products only
4. Dynamic scoring based on real signals
5. Update rotation state

---

## 🔧 **Service Layer Dependencies**

### **🤖 AI Services**
```python
# app/services/ai/groq_client.py
├── generate_essence()          # Product description generation
├── generate_tags()             # Product tag creation  
├── process_product()           # Full AI enrichment
├── suggest_selector_fix()      # Healing broken selectors
└── extract_product_category()  # Category classification
```

### **🕷️ Scraping Services**
```python
# app/services/scraper/factory.py
├── get_platform_handler()      # Get scraper by platform name
├── get_all_platforms()         # Get all registered scrapers
└── health_check()              # Verify scraper health

# platforms/*.py (Individual Scrapers)
├── amazon.py                   # Amazon product scraping
├── flipkart.py                 # Flipkart product scraping
├── myntra.py                   # Myntra fashion scraping
├── nykaa.py                    # Nykaa beauty scraping
├── croma.py                    # Croma electronics scraping
└── meesho.py                   # Meesho value products scraping
```

### **💾 Data Layer**
```python
# app/models.py (Database Tables)
├── Platform                    # Platform configurations
├── Product                     # Master product catalog
├── ProductListing              # Platform-specific listings
├── User                        # User accounts
├── UserWatchlist               # Product watchlists
├── PriceHistory                # Historical price data
├── SystemLog                   # Job execution logs
├── Transaction                 # Payments/affiliate tracking
├── AppConfig                   # Runtime configuration
└── StreakMilestone             # Gamification rewards

# app/core/database.py
├── engine                      # SQLAlchemy async engine
├── async_session_maker         # Database session factory
└── db                          # Legacy export (for compatibility)
```

### **🗄️ Cache Layer**
```python
# app/core/redis_client.py
├── get/set/delete              # Basic operations
├── info()                      # Server information
├── ping()                      # Health check
├── connect()                   # Auto-connection
└── increment()                 # Counter operations
```

---

## 🚀 **How to Modify Jobs System**

### **Adding New Jobs**
1. Create job file in `jobs/` directory
2. Add sys.path setup (already done for existing jobs)
3. Import required dependencies
4. Add to `scheduler.py` job registry
5. Test with: `python jobs/your_job.py`

### **Modifying Existing Jobs**
1. Edit the specific job file
2. Dependencies are auto-imported
3. Test with: `python jobs/job_name.py`
4. Check logs in SystemLog table

### **Key Files to Modify**
| **Purpose** | **File to Modify** |
|------------|-------------------|
| Change job schedule | `jobs/scheduler.py` |
| Add new platform | `platforms/new_platform.py` |
| Modify AI behavior | `app/services/ai/groq_client.py` |
| Change database schema | `app/models.py` + migrations |
| Update caching strategy | `app/core/redis_client.py` |
| Modify scraping logic | `app/services/scraper/factory.py` |

---

## 🎯 **Production Considerations**

### **Environment Variables Needed**
```bash
# Database
DATABASE_URL=postgresql+asyncpg://user:pass@localhost/dbname

# Redis  
REDIS_URL=redis://username:password@host:port

# AI Services
GROQ_API_KEY_MAIN=your_groq_key
GROQ_API_KEY_SEARCH=your_groq_key
GROQ_API_KEY_HEALING=your_groq_key

# Payments
RAZORPAY_KEY_ID=your_razorpay_key
RAZORPAY_KEY_SECRET=your_razorpay_secret
GOOGLE_PLAY_PUBLIC_KEY=your_google_key
```

### **Monitoring & Logging**
- All jobs log to `SystemLog` table
- Redis monitoring via `redis_client.info()`
- Database health via connection checks
- Error tracking with full stack traces

### **Performance Optimizations**
- Connection pooling (database & Redis)
- Rate limiting per platform
- Batch operations for bulk updates
- Caching strategies for frequently accessed data

---

## 🏆 **System Status: Production Ready**

✅ **All job scripts working**  
✅ **Dependencies resolved**  
✅ **Error handling implemented**  
✅ **Logging & monitoring active**  
✅ **Scheduler configured**  
✅ **AI integration functional**  
✅ **Database operations stable**  
✅ **Redis caching operational**  

**The entire jobs system is now fully functional and ready for production deployment!** 🎉
