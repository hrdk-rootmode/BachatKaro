# 🚀 DEALHUNT - FRONTEND USER SIDE IMPLEMENTATION GUIDE
## React Native + Web (Cross-Platform) | Complete Development Specifications

---

## 📋 TABLE OF CONTENTS
1. [Project Setup](#project-setup)
2. [Architecture Overview](#architecture-overview)
3. [File Structure](#complete-file-structure)
4. [Core Features](#core-features)
5. [Screens & Components](#screens--components)
6. [Redux & State Management](#redux--state-management)
7. [API Integration](#api-integration)
8. [Authentication Flow](#authentication-flow)
9. [Payment Integration](#payment-integration)
10. [Ads & Monetization](#ads--monetization)
11. [Deployment](#deployment)

---

## 🎯 PROJECT SETUP

### 1. Initial Project Creation
```bash
# Using Expo (Recommended for rapid development)
npx create-expo-app dealhunt-app

# OR using React Native CLI
npx @react-native-community/cli@latest init dealhunt-app

# Navigate to project
cd dealhunt-app

# Install core dependencies
npm install react-navigation react-navigation-stack react-navigation-bottom-tabs react-navigation-native
npm install react-native-screens react-native-safe-area-context react-native-gesture-handler react-native-reanimated
npm install @react-native-async-storage/async-storage
npm install redux react-redux @reduxjs/toolkit @reduxjs/toolkit/query
npm install react-native-paper@5.11.0
npm install react-native-vector-icons
npm install victory-native
npm install firebase react-native-firebase
npm install react-native-google-mobile-ads
npm install razorpay-react-native
npm install react-native-iap
npm install react-native-device-info
npm install axios
npm install react-native-fast-image
npm install redux-persist
npm install react-native-confetti-cannon
npm install react-native-linear-gradient
npm install react-native-svg react-native-svg-transformer
```

### 2. TypeScript Setup
```bash
npm install --save-dev typescript @types/react @types/react-native
npx tsc --init
```

### 3. Essential Configuration Files

**tsconfig.json**:
```json
{
  "compilerOptions": {
    "target": "es2020",
    "module": "esnext",
    "lib": ["es2020"],
    "jsx": "react-native",
    "strict": true,
    "esModuleInterop": true,
    "skipLibCheck": true,
    "forceConsistentCasingInFileNames": true,
    "resolveJsonModule": true,
    "moduleResolution": "node",
    "baseUrl": "./src",
    "paths": {
      "@/*": ["./*"],
      "@screens/*": ["./screens/*"],
      "@components/*": ["./components/*"],
      "@store/*": ["./store/*"],
      "@services/*": ["./services/*"],
      "@utils/*": ["./utils/*"],
      "@types/*": ["./types/*"]
    }
  },
  "include": ["src/**/*"],
  "exclude": ["node_modules", "dist"]
}
```

**package.json (key dependencies)**:
```json
{
  "name": "dealhunt-app",
  "version": "1.0.0",
  "main": "index.js",
  "type": "module",
  "scripts": {
    "start": "expo start",
    "android": "expo run:android",
    "ios": "expo run:ios",
    "web": "expo start --web",
    "build:android": "eas build --platform android",
    "test": "jest",
    "lint": "eslint src/**/*.{ts,tsx}"
  },
  "dependencies": {
    "react": "^18.2.0",
    "react-native": "^0.73.0",
    "react-native-paper": "^5.11.0",
    "react-navigation": "^6.1.0",
    "react-navigation-stack": "^5.14.0",
    "react-navigation-bottom-tabs": "^6.4.0",
    "redux": "^4.2.1",
    "react-redux": "^8.1.0",
    "@reduxjs/toolkit": "^1.9.5",
    "@reduxjs/toolkit/query": "^1.9.5",
    "firebase": "^10.0.0",
    "react-native-firebase": "^18.0.0",
    "react-native-google-mobile-ads": "^13.0.0",
    "victory-native": "^37.0.0",
    "axios": "^1.5.0",
    "react-native-device-info": "^10.6.0",
    "redux-persist": "^6.0.0",
    "razorpay-react-native": "^2.2.4",
    "@react-native-community/async-storage": "^1.12.1"
  }
}
```

---

## 🏗️ ARCHITECTURE OVERVIEW

### Device/User Flow
```
App Launch
    ↓
[Check AsyncStorage for Firebase Token]
    ↓
├─ Token Exists → Verify with Firebase → Auto-Login → Navigate to Home
├─ No Token → Show Onboarding (First Launch) → Navigate to Login
└─ Expired Token → Refresh Token Flow → Re-authenticate

Authentication (Firebase + Backend Sync)
    ↓
├─ Email/Password Signup → Firebase Create User → POST /signup → Token Storage
├─ Google Sign-In → Firebase Auth → POST /login → Token Storage
└─ Hardware ID → Generate on First Launch → Send with Auth

API Requests
    ↓
[Express RTK Query Endpoint]
    ↓
├─ Check Redis Cache (TTL 5 mins)
├─ If Miss → Query PostgreSQL
├─ If Miss → Live Platform Scrape
└─ Response → Update Redux Cache → Display to User

Search (3-Tier Caching)
    ↓
├─ Debounce 500ms User Input
├─ RTK Query Cache Check
├─ POST /search {"query": "iPhone 15"}
└─ Receive {results, source: "redis|database|live_scrape"}

Watchlist + Price Alerts
    ↓
├─ User Sets Target Price
├─ POST /watchlist with FCM token
├─ Price Drop → FCM Notification
└─ App Listens → onMessage → Update UI Badge

Payments
    ↓
├─ Android (Google Play Billing): requestPurchase → Verify Token → POST Webhook
└─ Web (Razorpay): Create Order → Open Modal → Verify Signature

Offline Support
    ↓
├─ NetInfo Listener Detects Offline
├─ Show Banner "Offline - Showing Cached Data"
├─ Queue Actions → Redis Persist to AsyncStorage
└─ On Reconnect → Sync Queued Actions → Update UI
```

---

## 📁 COMPLETE FILE STRUCTURE

```
dealhunt-app/
│
├── package.json                         # Dependencies & scripts
├── tsconfig.json                        # TypeScript config
├── babel.config.js                      # Babel config
├── metro.config.js                      # Metro bundler (React Native)
├── app.json                             # Expo config
├── .env                                 # Environment variables (DO NOT COMMIT)
├── .env.example                         # Template (commit this)
├── index.js                             # Entry point
│
├── src/
│   │
│   ├── App.tsx                          # Root component (Providers + Navigation)
│   │
│   ├── navigation/
│   │   ├── AppNavigator.tsx             # Main router (Auth vs Home-based)
│   │   ├── AuthStack.tsx                # Auth screens (Login, Signup, Onboarding)
│   │   ├── MainTabs.tsx                 # Bottom tab navigation (5 tabs)
│   │   ├── StackNavigator.tsx           # Nested stack for each tab
│   │   └── linking.ts                   # Deep linking configuration
│   │
│   ├── screens/
│   │   ├── auth/
│   │   │   ├── OnboardingScreen.tsx     # 3 slides (Welcome, Features, Permissions)
│   │   │   ├── LoginScreen.tsx          # Email/Password + Google Sign-In
│   │   │   ├── SignupScreen.tsx         # Create account + Referral code
│   │   │   ├── ForgotPasswordScreen.tsx # Password reset (Firebase)
│   │   │   └── VerifyEmailScreen.tsx    # Email confirmation (if needed)
│   │   │
│   │   ├── home/
│   │   │   ├── HomeScreen.tsx           # Trending products + Streak widget + Quick search
│   │   │   └── TrendingDetailScreen.tsx # Full trending list
│   │   │
│   │   ├── search/
│   │   │   ├── SearchScreen.tsx         # Main search interface
│   │   │   ├── SearchResultsScreen.tsx  # Grid of product cards
│   │   │   ├── URLSearchScreen.tsx      # Paste link, compare prices
│   │   │   └── FilterSheet.tsx          # Filter modal (price, rating, platform)
│   │   │
│   │   ├── product/
│   │   │   └── ProductDetailScreen.tsx  # Full product page (price table + chart)
│   │   │
│   │   ├── watchlist/
│   │   │   └── WatchlistScreen.tsx      # Tracked products with alerts
│   │   │
│   │   ├── streak/
│   │   │   ├── StreakScreen.tsx         # Check-in widget + Current streak
│   │   │   └── MilestonesScreen.tsx     # Rewards & achievements
│   │   │
│   │   ├── subscription/
│   │   │   ├── PlansScreen.tsx          # Pricing cards (Free/Pro/Premium)
│   │   │   └── CheckoutScreen.tsx       # Payment (Google Play / Razorpay)
│   │   │
│   │   └── profile/
│   │       ├── ProfileScreen.tsx        # User info + Stats
│   │       ├── SettingsScreen.tsx       # Notifications + Theme + Language
│   │       ├── ReferralScreen.tsx       # Share referral code
│   │       └── HelpScreen.tsx           # FAQ + Support
│   │
│   ├── components/
│   │   ├── common/
│   │   │   ├── Button.tsx               # Custom button component
│   │   │   ├── Input.tsx                # Text input with validation
│   │   │   ├── Card.tsx                 # Material card wrapper
│   │   │   ├── Loader.tsx               # Loading spinner
│   │   │   ├── EmptyState.tsx           # Empty list placeholder
│   │   │   ├── ErrorBoundary.tsx        # Crash handler
│   │   │   └── OfflineBanner.tsx        # Offline indicator
│   │   │
│   │   ├── ProductCard.tsx              # Product listing card
│   │   ├── PriceTag.tsx                 # Price display with discount
│   │   ├── PlatformBadge.tsx            # Platform logo (Amazon/Flipkart, etc.)
│   │   ├── PriceChart.tsx               # Victory Native graph (120-day history)
│   │   ├── StreakWidget.tsx             # Fire icon + count (animated)
│   │   ├── ConfettiAnimation.tsx        # Celebration effect (rewards)
│   │   ├── AdBanner.tsx                 # AdMob banner ad
│   │   ├── RewardedAdButton.tsx         # Watch ad for +5 searches
│   │   ├── FilterSheet.tsx              # Swipe-up filter modal
│   │   ├── PricingCard.tsx              # Subscription plan card
│   │   └── NotificationBadge.tsx        # Red dot on watchlist alerts
│   │
│   ├── store/
│   │   ├── index.ts                     # Store configuration
│   │   ├── slices/
│   │   │   ├── authSlice.ts             # Redux: User, token, auth state
│   │   │   ├── searchSlice.ts           # Redux: Results, filters, history
│   │   │   ├── watchlistSlice.ts        # Redux: Watched products
│   │   │   ├── streakSlice.ts           # Redux: Current streak, rewards
│   │   │   ├── subscriptionSlice.ts     # Redux: Plan, quota limits
│   │   │   └── appSlice.ts              # Redux: Theme, notifications, language
│   │   │
│   │   ├── api/
│   │   │   ├── apiSlice.ts              # RTK Query base configuration
│   │   │   ├── authApi.ts               # RTK endpoints: signup, login, refresh
│   │   │   ├── searchApi.ts             # RTK endpoints: search, trending, autocomplete
│   │   │   ├── productsApi.ts           # RTK endpoints: detail, price history
│   │   │   ├── watchlistApi.ts          # RTK endpoints: get, add, delete
│   │   │   ├── streakApi.ts             # RTK endpoints: checkin, status, milestones
│   │   │   └── subscriptionApi.ts       # RTK endpoints: plans, order, verify
│   │   │
│   │   └── middleware/
│   │       └── persistConfig.ts         # Redux Persist configuration
│   │
│   ├── services/
│   │   ├── firebase/
│   │   │   ├── firebaseConfig.ts        # Firebase app initialization
│   │   │   ├── authService.ts           # Firebase Auth (signUp, signIn, signOut)
│   │   │   ├── messagingService.ts      # FCM setup + token handling
│   │   │   └── analyticsService.ts      # Firebase Analytics events
│   │   │
│   │   ├── payments/
│   │   │   ├── googlePlayService.ts     # Google Play Billing (Android)
│   │   │   ├── razorpayService.ts       # Razorpay SDK (Web)
│   │   │   └── paymentHelper.ts         # Payment flow orchestration
│   │   │
│   │   ├── ads/
│   │   │   ├── admobService.ts          # AdMob SDK initialization
│   │   │   ├── bannerAd.ts              # Banner ad display
│   │   │   ├── interstitialAd.ts        # Interstitial ad logic
│   │   │   └── rewardedAd.ts            # Rewarded ad (watch for +5 searches)
│   │   │
│   │   ├── storage/
│   │   │   ├── asyncStorageHelper.ts    # AsyncStorage wrapper (get/set/remove)
│   │   │   └── secureStorageHelper.ts   # Secure token storage (Keychain/Keystore)
│   │   │
│   │   └── notifications/
│   │       ├── fcmSetup.ts              # FCM initialization
│   │       └── notificationHandler.ts   # Handle incoming notifications
│   │
│   ├── hooks/
│   │   ├── useAuth.ts                   # Access auth state + methods
│   │   ├── useSearch.ts                 # Search with debounce + caching
│   │   ├── useWatchlist.ts              # Watchlist operations
│   │   ├── useStreak.ts                 # Streak checkin + rewards
│   │   ├── useSubscription.ts           # Plan limits + quota
│   │   ├── useDebounce.ts               # Debounce any value
│   │   ├── useNetworkStatus.ts          # Online/offline detection
│   │   ├── useTheme.ts                  # Dark mode toggle
│   │   └── usePagination.ts             # Infinite scroll pagination
│   │
│   ├── utils/
│   │   ├── formatters.ts                # formatPrice, formatDate, formatStreak
│   │   ├── validators.ts                # Email, password, URL validation
│   │   ├── constants.ts                 # API_BASE_URL, colors, strings
│   │   ├── deviceInfo.ts                # Get hardware_id, device model, OS
│   │   ├── deepLinking.ts               # Parse deep links (dealhunt://product/{id})
│   │   ├── errorHandler.ts              # Standard error responses
│   │   └── logger.ts                    # Logging utility (future Sentry integration)
│   │
│   ├── theme/
│   │   ├── colors.ts                    # Palette (primary, secondary, error)
│   │   ├── typography.ts                # Font sizes, weights
│   │   ├── spacing.ts                   # Scale (4, 8, 16, 24, 32)
│   │   ├── lightTheme.ts                # React Native Paper light theme
│   │   └── darkTheme.ts                 # React Native Paper dark theme
│   │
│   └── types/
│       ├── api.types.ts                 # API request/response types
│       ├── navigation.types.ts          # React Navigation param types
│       ├── redux.types.ts               # Redux state shape
│       ├── models.types.ts              # Domain models (User, Product, etc.)
│       └── common.types.ts              # Shared types (Error, Success, etc.)
│
├── web/                                 # Web-specific (React Native Web)
│   ├── public/
│   │   ├── index.html                   # HTML template
│   │   ├── favicon.ico                  # Favicon
│   │   ├── robots.txt                   # SEO
│   │   └── sitemap.xml                  # SEO
│   │
│   └── components/
│       ├── LandingPage.tsx              # Hero + Features
│       ├── SearchDemoPage.tsx           # Limited search (max 3 results)
│       ├── HowItWorksPage.tsx           # 3-step guide
│       └── DownloadPage.tsx             # APK download + guide
│
├── android/                             # Android-specific config
│   ├── app/build.gradle                 # Build config
│   ├── app/google-services.json         # Firebase config (download)
│   ├── app/src/main/AndroidManifest.xml # Permissions
│   │   └── res/
│   │       ├── mipmap-*/                # App icons
│   │       └── values/colors.xml        # Splash color
│   └── gradle.properties
│
└── .gitignore
```

---

## 🎨 SCREENS & COMPONENTS

### Authentication Screens (4 screens)

#### 1. **OnboardingScreen.tsx**
```
Slide 1: "Welcome to DealHunt"
  - Logo + App name
  - "Never Overpay Again."
  → [Next] button

Slide 2: "Features"
  - Icons: Price comparison, Streak, Alerts
  - "Save on every purchase"
  → [Next] button

Slide 3: "Permissions"
  - "This app needs your permission to:"
  - Internet, Notifications, Storage
  → [Get Started] button → Navigate to LoginScreen
```

#### 2. **LoginScreen.tsx**
```
- Email input field
- Password input field
- "Forgot Password?" link
- [Sign In] button (primary)
- "Don't have account?" link
- [Sign In with Google] button (secondary)
- Loading spinner (when signing in)
```

#### 3. **SignupScreen.tsx**
```
- Email input (validate not disposable)
- Password input (min 8 chars, uppercase, number)
- Confirm password input
- Referral code input (optional)
  → "Enter code from friend to get bonus searches"
- Terms checkbox
- [Create Account] button
- "Already have account?" link to LoginScreen
```

#### 4. **ForgotPasswordScreen.tsx**
```
- Email input
- [Send Reset Link] button
- Success message: "Check your email for reset link"
```

### Home Screen
```
┌─────────────────────────────────┐
│ DealHunt         [Profile Icon] │  ← Header
├─────────────────────────────────┤
│        🔥 47-Day Streak!         │  ← Streak Widget (animated)
│                                 │     [Check In] button
├─────────────────────────────────┤
│ 📈 Trending Now                 │
│ [Product Card 1] [Product Card 2]... │ ← Scrollable
│ [Product Card 3] [Product Card 4]... │
├─────────────────────────────────┤
│ Search anything...              │  ← Quick search bar
│ [Amazon] [Flipkart] [Meesho]... │  ← Platform shortcuts
│                                 │
│ [Download apk] [Pro limits]     │  ← Info cards
└─────────────────────────────────┘
```

### Search Screens (3 screens)

#### 1. **SearchScreen.tsx**
```
┌─────────────────────────────────┐
│ Search for products...          │  ← SearchBar (debounced)
│ ✕ Recent searches:              │
│ • iPhone 15 pro                 │
│ • Samsung 55" TV               │
│ • Wireless earbuds             │
│ 🔗 Search by URL               │  ← URL search button
└─────────────────────────────────┘
```

#### 2. **SearchResultsScreen.tsx**
```
┌─────────────────────────────────┐
│ [Filters ⚙️] [Sort ⬆️⬇️]         │  ← Filter + Sort buttons
├─────────────────────────────────┤
│ [Product Card Grid 2x2]         │
│ [Product Card]  [Product Card]  │
│ [Product Card]  [Product Card]  │
│ [LoadMore...]                   │  ← Infinite scroll
│                                 │
│ [Ads Banner - Free users only]  │  ← AdMob banner
└─────────────────────────────────┘
```

#### 3. **URLSearchScreen.tsx**
```
┌─────────────────────────────────┐
│ Paste product URL:              │
│ [https://amazon.in/dp/B0...]    │  ← Text input
│ [Search] button                 │
├─────────────────────────────────┤
│ Found on: Amazon, Flipkart      │  ← Result
│ [Price Comparison Table]        │
└─────────────────────────────────┘
```

### Product Detail Screen
```
┌─────────────────────────────────┐
│ [Back]  Product Detail      [❤️]│
├─────────────────────────────────┤
│ [Product Image - Slider]        │
│                                 │
│ iPhone 15 Pro Max 256GB         │  ← Title
│ ⭐⭐⭐⭐⭐ (2345 reviews)         │
│                                 │
│ PRICE HISTORY (Last 120 days)   │
│ [Victory Native Price Chart]    │  ← Line graph
│ Lowest: ₹79,999 (2 weeks ago)   │
│                                 │
│ BEST DEAL:                      │  ← Highlighted
│ Amazon: ₹79,999 [Buy on Amazon] │
│ (Save ₹15,000 vs MRP)           │
│                                 │
│ OTHER PLATFORMS:                │
│ Flipkart: ₹82,000               │
│ Croma: ₹84,999                  │
│ Myntra: ₹85,000                 │
│                                 │
│ [Share 📤] [Add to Watchlist 📌]│
│ [More from this brand]          │
└─────────────────────────────────┘
```

### Watchlist Screen
```
┌─────────────────────────────────┐
│ Watchlist                 (5/20) │
├─────────────────────────────────┤
│ ✓ iPhone 15 Pro (₹79,999)       │  ← Green = Found
│   Target: ₹75,000              │     Red badge = Price dropped
│   Last update: 2 hours ago      │
│   [View] [Edit] [Remove ✕]     │
│                                 │
│ 🔴 Samsung 55" TV (Not found)   │  ← Red = Out of stock
│   Was: ₹45,000                  │
│   [SearchAgain] [Remove]        │
│                                 │
│ [No watched products message]   │  ← Empty state
│ "Add products to track prices"  │
│ [Start searching...]            │
└─────────────────────────────────┘
```

### Streak & Rewards Screen
```
┌──────────────────────────────────┐
│ My Achievements              🏆  │
├──────────────────────────────────┤
│          🔥 47-DAY STREAK        │
│                                  │
│ [Check In Today] button          │  ← Primary action
│                                  │
│ Milestones:                      │
│ ✅ Day 3 → +10 searches (claimed)│
│ ✅ Day 7 → 1 month free Pro      │
│ ⏳ Day 14 → 50 watchlist slots (4/14 days)
│ ⏳ Day 30 → 1 year Premium       │
│                                  │
│ Rewards Earned: ₹2,450           │
│ [Redeem Rewards]                 │
│                                  │
│ [Use Freeze] (2x remaining)      │  ← Premium feature
│ "Protect your streak from breaks"│
└──────────────────────────────────┘
```

### Subscription/Plans Screen
```
┌──────────────────────────────────┐
│ [Back]  Upgrade Your Plan    [?] │
├──────────────────────────────────┤
│ Current Plan: FREE TIER          │
│ Searches today: 3/10             │
│                                  │
│ ┌────────────┐ ┌────────────┐   │
│ │   FREE     │ │    PRO ✨  │   │  ← Cards with features
│ │   (Current)│ │  ₹99/month │   │
│ │ • 10 srch  │ │ • 100 srch │   │
│ │ • 5 watch  │ │ • 50 watch │   │
│ │ • With ads │ │ • No ads   │   │
│ │            │ │[Upgrade]   │   │
│ └────────────┘ └────────────┘   │
│                                  │
│ ┌────────────┐                   │
│ │  PREMIUM   │                   │
│ │ ₹999/year  │                   │
│ │ • Unlimited│                   │
│ │ • 100000 w │                   │
│ │ • No ads   │                   │
│ │[Upgrade]   │                   │
│ └────────────┘                   │
│                                  │
│ [Restore Purchase] for previous  │
└──────────────────────────────────┘
```

### Checkout Screen
```
Android (Google Play Billing):
┌──────────────────────────────────┐
│ [Back]  Payment              [?] │
├──────────────────────────────────┤
│ Upgrading to: PRO                │
│ Amount: ₹99                      │
│ Billing Period: Monthly          │
│                                  │
│ [Google Play Payment Sheet] 🔒   │  ← Native play billing
│                                  │
│ Processing... [Loader]           │
│                                  │
│ ✅ Payment Successful!           │
│ "Welcome to PRO tier"            │
│ [Continue]                       │
└──────────────────────────────────┘

Web (Razorpay):
- Open Razorpay Modal
- Email input
- Phone input
- [Pay ₹99]
- Show success message
```

### Profile & Settings Screens
```
PROFILE SCREEN:
┌──────────────────────────────────┐
│ [Edit]  Profile              [⚙️]│
├──────────────────────────────────┤
│ 👤 Harsh Deshmukh              │ ← Email/notification icon
│ harsh@example.com              │
│                                  │
│ Current Plan: PRO                │
│ Next Billing: Jan 15, 2024       │
│ Searches Today: 45/100           │ ← Progress bar
│                                  │
│ Referral Code: DH4K2P            │
│ [Share Code] [Copy to Clipboard] │
│ Friends Invited: 3/5             │
│ Rewards Earned: ₹2,450           │
│                                  │
│ [Settings] [Logout] [Delete Acct]│
└──────────────────────────────────┘

SETTINGS SCREEN:
┌──────────────────────────────────┐
│ [Back]  Settings             [?] │
├──────────────────────────────────┤
│ NOTIFICATIONS                    │
│ ┌─────────────┐                  │
│ │Price Alerts │ [Toggle: ON] 🔔  │ ← Toggle switches
│ └─────────────┘                  │
│ ┌─────────────┐                  │
│ │Streak Notes │ [Toggle: ON] 🔔  │
│ └─────────────┘                  │
│ ┌─────────────┐                  │
│ │Promotions   │ [Toggle: ON] 📢  │
│ └─────────────┘                  │
│                                  │
│ DISPLAY                          │
│ ┌─────────────┐                  │
│ │Dark Mode    │ [Toggle: OFF] 🌙 │
│ └─────────────┘                  │
│ ┌─────────────┐                  │
│ │Language     │ [English] ▼      │
│ └─────────────┘                  │
│                                  │
│ ABOUT                            │
│ Version: 1.0.5                   │
│ Built with ❤️                    │
│ [Privacy Policy] [Terms]         │
└──────────────────────────────────┘
```

---

## 🎯 CORE FEATURES IN DETAIL

### 1. Authentication Flow

**Step-by-Step Process**:
```typescript
// App.tsx entry point
const App = () => {
  const [initializing, setInitializing] = useState(true);
  const [user, setUser] = useState<FirebaseAuthTypes.User | null>(null);

  useEffect(() => {
    // Listen to Firebase auth state
    const subscriber = auth().onAuthStateChanged(onAuthStateChanged);
    return subscriber;
  }, []);

  const onAuthStateChanged = async (user: FirebaseAuthTypes.User | null) => {
    if (user) {
      // User exists - sync with backend
      const token = await user.getIdToken();
      const hardware_id = await getHardwareId();
      
      // Send to backend: POST /signup or /login
      syncWithBackend(token, hardware_id);
      
      // Store token in secure storage
      await storeSecureToken(token);
      
      // Setup FCM for notifications
      const fcmToken = await getAndSetupFCM(user.uid);
      
      // Navigate to Home
      setUser(user);
    } else {
      // No user - show login
      setUser(null);
    }
    setInitializing(false);
  };

  if (initializing) {
    return <LoadingScreen />;
  }

  return (
    <NavigationContainer>
      {user ? <MainAppNavigator /> : <AuthStackNavigator />}
    </NavigationContainer>
  );
};
```

**Signup Flow**:
```
1. User enters email, password, referral code
2. Firebase.auth().createUserWithEmailAndPassword(email, password)
3. Get Firebase ID token
4. POST /auth/signup {
     firebase_uid: string,
     email: string,
     hardware_id: string,
     fcm_token: string,
     referral_code?: string
   }
5. Backend creates user record
6. Backend verifies referral code → distribute rewards
7. Return {token, user, plan}
8. Store token + user info in Redux
9. Navigate to HomeScreen
```

**Login Flow**:
```
1. User enters email, password
2. Firebase.auth().signInWithEmailAndPassword(email, password)
3. On success, firebaseAuth state change triggers onAuthStateChanged
4. Backend receives firebase_uid
5. POST /auth/login {firebase_uid}
6. Backend returns {token, user, plan}
7. Store in Redux + AsyncStorage
8. Navigate to HomeScreen
```

**Google Sign-In Flow**:
```
1. User clicks "Sign In with Google"
2. Firebase.auth().signInWithPopup(GoogleAuthProvider)
3. Firebase creates/updates user
4. Get Firebase token
5. Send to backend with hardware_id + fcm_token
6. Backend syncs user
7. Store token + user info
8. Navigate to HomeScreen
```

### 2. Search Implementation (3-Tier)

**Client-Side Search**:
```typescript
// hooks/useSearch.ts
const useSearch = () => {
  const dispatch = useDispatch();
  const [query, setQuery] = useState('');
  const debouncedQuery = useDebounce(query, 500);

  const { data, isLoading, error } = useSearchQuery(debouncedQuery);

  useEffect(() => {
    if (debouncedQuery) {
      // RTK Query handles caching automatically
      // - Checks Redux cache first
      // - If not cached, makes API request
      // - Response includes source: "redis" | "database" | "live_scrape"
    }
  }, [debouncedQuery]);

  return { 
    data, 
    isLoading, 
    error,
    setQuery,
    handleSearch: () => dispatch(searchSlice.actions.addToHistory(debouncedQuery))
  };
};
```

**Backend Search Endpoint**:
```
POST /api/v1/search/search
{
  query: "iPhone 15",
  filters: {
    price_min?: 50000,
    price_max?: 100000,
    platforms?: ["amazon", "flipkart"],
    rating_min?: 4,
    results_limit?: 50
  }
}

Response (from cache/DB/live scrape):
{
  results: [
    {
      product_id: "uuid",
      title: "iPhone 15 Pro Max",
      listings: [
        {
          platform: "amazon",
          price: 79999,
          original_price: 99999,
          discount: 20,
          rating: 4.5,
          reviews: 2345,
          url: "https://amazon.in/dp/..."
        },
        {
          platform: "flipkart",
          price: 82000,
          ...
        }
      ]
    }
  ],
  source: "redis|database|live_scrape",
  cached_at: "2024-01-15T10:30:00Z",
  cache_ttl: 300  // seconds
}
```

**Caching Strategy**:
- Tier 1: Redis (5 min TTL) - in-memory, fastest
- Tier 2: PostgreSQL (1 hour TTL) - persistent, fast
- Tier 3: Live Scrape (real-time) - slowest, most accurate

### 3. Price Alerts & Watchlist

**Add to Watchlist**:
```
1. User on ProductDetailScreen
2. Clicks "Add to Watchlist ❤️"
3. Modal opens: "Set target price"
   - Default: Lowest current price - 10%
   - Current lowest: ₹79,999
   - Default target: ₹71,999
4. User can adjust target price
5. POST /api/v1/watchlist/add {
     product_id: "uuid",
     target_price: 71999,
     notify_any_drop: true,  // alert on any price change
     user_fcm_token: "firebase_token"
   }
6. Backend stores + FCM token
7. Update Redux watchlistSlice
8. Show success toast: "Added to watchlist"
9. Added product shows ❤️ (filled red)
```

**Price Drop Notification**:
```
Backend Job (hourly):
1. Check all watchlist items
2. Fetch current prices from platforms
3. Compare with target price
4. If price < target:
   - Send FCM message to user's device
   - Message: "🔥 iPhone 15 Pro dropped to ₹74,999 (was ₹79,999)"
   - Data: {product_id, new_price, old_price}

Frontend (app receives message):
1. onMessage listener (app in foreground)
   - Show banner notification
   - Update watchlist item with new price
   - Show red badge on Watchlist tab

2. onNotificationOpenedApp (app in background/killed)
   - User taps notification
   - App opens → Navigate to ProductDetailScreen
   - Update price information
```

### 4. Streak Gamification

**Daily Check-In**:
```
1. User opens app (HomeScreen)
2. Auto-trigger on app focus: POST /api/v1/streak/check-in
3. Backend checks:
   - Is user already checked in today? (No → proceed)
   - Is last checkin < 48 hours ago? (Yes → maintain streak)
4. Response:
   {
     current_streak: 47,
     longest_streak: 89,
     checked_in_today: true,
     reward?: {
       type: "milestone",  // milestone | bonus | freeze_refund
       value: 50,  // extra searches or reward days
       milestone_day: 7
     },
     freeze_count: 2  // remaining freezes
   }
5. If reward = milestone:
   - Show modal with confetti animation
   - Display reward details
   - Play celebration sound
6. Update Redux streakSlice.current = 47
7. Render StreakWidget with new count
```

**Milestones Rewards**:
```
Day 3:  +10 searches
Day 7:  1 month free Pro
Day 14: Expand watchlist to 50 (from 5)
Day 30: 1 year free Premium
Day 60: +500 searches (1 year worth)
Day 100: Exclusive badge 🏆
Day 365: Lifetime Pro status
```

**Streak Freeze**:
```
- Free tier: 0 freezes/month
- Pro tier: 2 freezes/month
- Premium tier: 5 freezes/month

When streak breaks:
- User can POST /api/v1/streak/use-freeze
- Streak maintained (not lost)
- Freeze count decreases
- User gets notification: "Streak saved! You have 1 freeze left"
```

### 5. Subscription & Payments

**Plans Available**:
```
FREE:
- 10 searches/day
- 5 watchlist items
- Show ads (AdMob)
- No price to pay
- Free forever

PRO (₹99/month):
- 100 searches/day
- 50 watchlist items
- No ads
- Auto-renew monthly
- Cancel anytime

PREMIUM (₹999/year):
- Unlimited searches
- Unlimited watchlist
- No ads
- 1 year validity
- Can cancel before renewal
```

**Google Play Billing (Android)**:
```
1. User on PlansScreen
2. Clicks "Upgrade to Pro" button
3. Check platform: if Android → requestPurchase()
4. Google Play Billing dialog opens
5. User completes payment
6. Purchase token received
7. POST /api/v1/subscription/verify-purchase {
     bundle_id: "com.dealhunt.app",
     product_id: "dealhunt_pro_monthly",
     purchase_token: "token_from_google"
   }
8. Backend verifies with Google API
9. If valid:
   - Update user.plan = "pro"
   - Set subscription_end_date = now + 30 days
   - Return {success: true, plan: "pro", ends_at: date}
10. Update Redux subscriptionSlice
11. Show success modal: "Upgrade successful! 🎉"
12. Navigate to HomeScreen
```

**Razorpay (Web)**:
```
1. User on web version of PlansScreen
2. Clicks "Upgrade to Pro" button
3. POST /api/v1/subscription/create-order {
     plan_id: 2,  // Pro plan
     user_id: "uuid"
   }
4. Backend creates Razorpay order
5. Returns {order_id, amount, currency}
6. Frontend opens Razorpay modal:
   RazorpayCheckout.open({
     key_id: process.env.RAZORPAY_KEY_ID,
     order_id: response.order_id,
     email: user.email,
     contact: user.phone,
     amount: response.amount,
     onSuccess: (response) => verifyPayment(response),
     onError: (error) => showError(error)
   })
7. User pays, Razorpay processes payment
8. Razorpay webhook to backend: validates signature
9. Frontend calls GET /api/v1/subscription/status
10. Returns {plan: "pro", valid_until: date}
11. Update Redux + show success
```

### 6. Advertisements

**AdMob Setup**:
```typescript
// Initialize in app startup
import { MobileAds } from 'react-native-google-mobile-ads';

MobileAds()
  .initialize()
  .then(adapterStatuses => {
    // Ads ready
  });
```

**Banner Ad** (Always visible for free users):
```typescript
// SearchResultsScreen.tsx
const SearchResultsScreen = () => {
  const plan = useSelector(state => state.subscription.plan);

  return (
    <>
      <SearchResults />
      {plan === 'free' && <AdBanner />}  {/* Bottom banner */}
    </>
  );
};

// components/AdBanner.tsx
const AdBanner = () => {
  return (
    <BannerAd
      unitId={process.env.ADMOB_BANNER_ID}
      size={BannerAdSize.ANCHORED_ADAPTIVE_BANNER}
      requestOptions={{
        requestNonPersonalizedAds: false,
      }}
    />
  );
};
```

**Interstitial Ad** (After 3rd search):
```typescript
// hooks/useSearch.ts
const useSearch = () => {
  const searchCount = useSelector(state => state.search.history.length);
  const plan = useSelector(state => state.subscription.plan);

  const handleSearch = () => {
    // ... perform search ...
    
    if (plan === 'free' && searchCount % 3 === 0) {
      // Show interstitial after 3rd search
      showInterstitialAd();
    }
  };
};
```

**Rewarded Ad** (+5 searches):
```typescript
// When user reaches search limit
const RewardedAdButton = () => {
  const handleWatchAd = () => {
    showRewardedAd({
      onReward: () => {
        // User watched full ad
        POST /api/v1/admin/grant-searches {
          user_id: "uuid",
          extra_searches: 5
        }
        // Update Redux searchSlice.quota += 5
        showToast('✅ 5 searches added!');
      },
      onSkip: () => {
        showToast('⚠️ Please watch the full ad to earn searches');
      }
    });
  };

  return (
    <Button 
      title="Watch Ad for +5 Searches" 
      onPress={handleWatchAd}
    />
  );
};
```

---

## 🔄 API INTEGRATION MAPPING

### All 60+ Backend Endpoints Mapped to Frontend

#### **Auth Endpoints (7)**
| Endpoint | Method | Frontend Usage | Redux Action |
|----------|--------|---|---|
| `/auth/signup` | POST | SignupScreen | authSlice.signup |
| `/auth/login` | POST | LoginScreen | authSlice.login |
| `/auth/refresh-token` | POST | Auto on token expire | authSlice.refreshToken |
| `/auth/me` | GET | ProfileScreen on mount | authSlice.fetchProfile |
| `/auth/me` | PUT | Edit ProfileScreen | authSlice.updateProfile |
| `/auth/me` | DELETE | Delete account modal | authSlice.deleteAccount |
| `/auth/verify-referral-code` | POST | SignupScreen | authSlice.verifyReferral |

#### **Search Endpoints (4)**
| Endpoint | Method | Frontend Usage | RTK Query |
|----------|--------|---|---|
| `/search/search` | POST | SearchResultsScreen | apiSlice.useSearchQuery |
| `/search/by-url` | POST | URLSearchScreen | apiSlice.useURLSearchQuery |
| `/search/trending` | GET | HomeScreen | apiSlice.useTrendingQuery |
| `/search/platforms/supported` | GET | FilterSheet | apiSlice.usePlatformsQuery |

#### **Product Endpoints (2)**
| Endpoint | Method | Frontend Usage | RTK Query |
|----------|--------|---|---|
| `/products/{id}` | GET | ProductDetailScreen | apiSlice.useProductQuery |
| `/products/{id}/price-history` | GET | PriceChart component | apiSlice.usePriceHistoryQuery |

#### **Watchlist Endpoints (5)**
| Endpoint | Method | Frontend Usage | Redux Action |
|----------|--------|---|---|
| `/watchlist` | GET | WatchlistScreen on mount | watchlistSlice.fetchList |
| `/watchlist` | POST | ProductDetail "Add" | watchlistSlice.addItem |
| `/watchlist/{id}` | PUT | Watchlist edit modal | watchlistSlice.updateItem |
| `/watchlist/{id}` | DELETE | Watchlist item swipe | watchlistSlice.removeItem |
| `/watchlist/check/{id}` | GET | ProductDetail checks | watchlistSlice.checkIfWatched |

#### **Streak Endpoints (5)**
| Endpoint | Method | Frontend Usage | Redux Action |
|----------|--------|---|---|
| `/streak/check-in` | POST | HomeScreen on mount | streakSlice.checkIn |
| `/streak/status` | GET | StreakScreen | streakSlice.fetchStatus |
| `/streak/milestones` | GET | MilestonesScreen | streakSlice.fetchMilestones |
| `/streak/use-freeze` | POST | Streak broken modal | streakSlice.useFreeze |
| `/streak/leaderboard` | GET | LeaderboardScreen (Phase 2) | streakSlice.fetchLeaderboard |

#### **Subscription Endpoints (8)**
| Endpoint | Method | Frontend Usage | RTK Query |
|----------|--------|---|---|
| `/subscription/plans` | GET | PlansScreen | apiSlice.usePlansQuery |
| `/subscription/payment-methods` | GET | CheckoutScreen | apiSlice.usePaymentMethodsQuery |
| `/subscription/create-order` | POST | CheckoutScreen (Razorpay) | apiSlice.useCreateOrderMutation |
| `/subscription/verify-payment` | POST | CheckoutScreen (Razorpay) | apiSlice.useVerifyPaymentMutation |
| `/subscription/verify-purchase` | POST | CheckoutScreen (Google Play) | apiSlice.useVerifyPurchaseMutation |
| `/subscription/acknowledge-purchase` | POST | CheckoutScreen (Google Play) | apiSlice.useAcknowledgePurchaseMutation |
| `/subscription/status` | GET | HomeScreen quota | subscriptionSlice.fetchStatus |
| `/subscription/cancel` | POST | SettingsScreen unsubscribe | subscriptionSlice.cancelPlan |

---

## 🛠️ REDUX STATE STRUCTURE

```typescript
// Redux State Shape
interface RootState {
  auth: {
    user: User | null;
    token: string | null;
    isLoading: boolean;
    error: string | null;
    isAuthenticated: boolean;
  };
  search: {
    results: Product[];
    query: string;
    filters: SearchFilters;
    isLoading: boolean;
    error: string | null;
    history: string[];  // recent searches
    searchedAt: Date | null;
  };
  watchlist: {
    items: WatchlistItem[];
    isLoading: boolean;
    error: string | null;
    lastSyncedAt: Date | null;
  };
  streak: {
    current: number;
    longest: number;
    rewardsEarned: Reward[];
    freezesRemaining: number;
    checkedInToday: boolean;
    lastCheckInAt: Date | null;
  };
  subscription: {
    plan: 'free' | 'pro' | 'premium';
    validUntil: Date | null;
    searchesRemaining: number;
    watchlistLimit: number;
    isLoading: boolean;
  };
  app: {
    theme: 'light' | 'dark';
    notificationsEnabled: boolean;
    offlineMode: boolean;
    language: 'en';
  };
}
```

---

## 🌐 WEB APP IMPLEMENTATION

### Landing Page `/`
```typescript
// web/components/LandingPage.tsx
const LandingPage = () => {
  return (
    <>
      <Header />
      <Hero 
        title="Never Overpay Again"
        subtitle="Compare prices across 6 platforms instantly"
        cta_button="Download APK"
      />
      <Features
        items={[
          { icon: '📊', title: 'Price Comparison', desc: '6 platforms at once' },
          { icon: '🔔', title: 'Price Alerts', desc: 'Notify on drops' },
          { icon: '🔥', title: 'Streaks & Rewards', desc: 'Earn daily bonuses' },
        ]}
      />
      <Testimonials
        items={[
          { user: 'Amit K.', saved: '₹12,000 in 3 months' },
          { user: 'Priya S.', saved: '₹5,500 in 1 month' }
        ]}
      />
      <CTABanner text="Get the app now" />
      <Footer />
    </>
  );
};
```

### Search Demo `/search`
```
- Search bar (functional, hits backend)
- Show only 3 results (not full list)
- Bottom banner: "Download APK to see all 50 results"
- Each product card: "View in app" button
```

### Download Page `/download`
```
- Latest APK version (v1.0.5)
- File size: 45 MB
- [Download APK] button (direct link)
- Installation steps with screenshots
- QR code for mobile scan
- "Coming soon to Play Store"
```

---

## 📦 DEPLOYMENT

### Android APK Build
```bash
# Generate release key (one-time)
keytool -genkey -v -keystore release-key.keystore -keyalg RSA -keysize 2048 -validity 10000 -alias dealhunt

# Build APK
cd android
./gradlew assembleRelease
# Output: android/app/build/outputs/apk/release/app-release.apk

# Upload to GitHub Releases
# https://github.com/yourusername/dealhunt-app/releases/v1.0.5
```

### Web Deployment (Vercel)
```bash
npm run build:web
# Deploy to Vercel
vercel --prod
# Domain: dealhunt.in
```

---

## 🚀 NEXT STEPS

1. ✅ **Set up project** - Create React Native project, install dependencies
2. ✅ **Create folder structure** - Organize all directories
3. ✅ **Configure Firebase** - Download google-services.json, setup auth
4. ✅ **Configure Redux** - Setup store, slices, RTK Query
5. ✅ **Create Auth screens** - LoginScreen, SignupScreen, Onboarding
6. ✅ **Create Navigation** - AppNavigator, AuthStack, MainTabs
7. ✅ **Create Home screen** - Trending + Streak widget
8. ✅ **Create Search feature** - SearchScreen, SearchResultsScreen
9. ✅ **Create Product detail** - ProductDetailScreen with price chart
10. ✅ **Setup AdMob** - Banner, interstitial, rewarded ads
11. ✅ **Setup Payment** - Google Play + Razorpay
12. ✅ **Setup Notifications** - FCM for price alerts
13. ✅ **Test all flows** - Auth, Search, Payments, Notifications, Offline
14. ✅ **Build APK** - Generate release APK
15. ✅ **Deploy Web** - Create landing page, deploy to Vercel

This is your complete implementation spec. Start with project setup and core navigation, then build screens one by one. Each screen connects to Redux + RTK Query for seamless state management and API caching.
