// ============================================
// DEALHUNT APP - CONSTANTS & CONFIGURATION
// ============================================

import {
  FIREBASE_API_KEY,
  FIREBASE_AUTH_DOMAIN,
  FIREBASE_PROJECT_ID,
  FIREBASE_STORAGE_BUCKET,
  FIREBASE_MESSAGING_SENDER_ID,
  FIREBASE_APP_ID,
  API_BASE_URL,
  APP_NAME,
  APP_VERSION,
} from '@env';


// --------------------------------------------
// FIREBASE CONFIGURATION
// --------------------------------------------
export const FIREBASE_CONFIG = {
  apiKey: FIREBASE_API_KEY,
  authDomain: FIREBASE_AUTH_DOMAIN,
  projectId: FIREBASE_PROJECT_ID,
  storageBucket: FIREBASE_STORAGE_BUCKET,
  messagingSenderId: FIREBASE_MESSAGING_SENDER_ID,
  appId: FIREBASE_APP_ID,
};


// --------------------------------------------
// API CONFIGURATION
// For physical Android device: Use WiFi IP (10.239.221.203)
// For emulator/localhost: Use 127.0.0.1
// Run: ipconfig | findstr IPv4
// --------------------------------------------
export const API = {
  BASE_URL: API_BASE_URL || 'http://10.239.221.203:8000/api/v1',
  TIMEOUT: 30000, // 30 seconds
  
  // Auth Endpoints
  ENDPOINTS: {
    // Authentication
    ME: '/auth/me',
    ME_STATS: '/auth/me/stats',
    LOGOUT: '/auth/logout',
    TOKEN_STATUS: '/auth/token-status',
    VERIFY_REFERRAL: '/auth/verify-referral-code',
    SIGNUP_PUBLIC: '/auth/signup-public',
    
    // Search (Part 2)
    SEARCH: '/search/search',
    SEARCH_BY_URL: '/search/by-url',
    TRENDING: '/search/trending',
    
    // Products (Part 2)
    PRODUCT_DETAIL: '/products', // + /{product_id}
    PRICE_HISTORY: '/products', // + /{product_id}/price-history
    
    // Watchlist (Part 3)
    WATCHLIST: '/watchlist',
    WATCHLIST_CHECK: '/watchlist/check', // + /{product_id}
    
    // Streak (Part 4)
    STREAK_CHECK_IN: '/streak/check-in',
    STREAK_STATUS: '/streak/status',
    STREAK_MILESTONES: '/streak/milestones',
    
    // Subscription (Part 5)
    SUBSCRIPTION_PLANS: '/subscription/plans',
  },
};

// --------------------------------------------
// STORAGE KEYS
// --------------------------------------------
export const STORAGE_KEYS = {
  AUTH_TOKEN: 'dealhunt_auth_token',
  USER_DATA: 'dealhunt_user_data',
  FIREBASE_UID: 'dealhunt_firebase_uid',
  HARDWARE_ID: 'dealhunt_hardware_id',
  ONBOARDING_COMPLETE: 'dealhunt_onboarding_done',
  THEME: 'dealhunt_theme',
};

// --------------------------------------------
// VALIDATION RULES
// --------------------------------------------
export const VALIDATION = {
  EMAIL_REGEX: /^[^\s@]+@[^\s@]+\.[^\s@]+$/,
  PASSWORD_MIN_LENGTH: 6,
  PASSWORD_REGEX: /^(?=.*[A-Z])(?=.*\d).{8,}$/, // Min 8 chars, 1 uppercase, 1 number
  REFERRAL_CODE_LENGTH: 6,
};

// --------------------------------------------
// APP CONFIGURATION
// --------------------------------------------
export const APP = {
  NAME: APP_NAME || 'DealHunt',
  VERSION: APP_VERSION || '1.0.0',
  
  // Subscription Plans
  PLANS: {
    FREE: {
      id: 'free',
      name: 'Free',
      searches_per_day: 10,
      watchlist_limit: 5,
      price: 0,
    },
    BASIC: {
      id: 'basic',
      name: 'Basic',
      searches_per_day: 50,
      watchlist_limit: 20,
      price: 99, // ₹99/month
    },
    PREMIUM: {
      id: 'premium',
      name: 'Premium',
      searches_per_day: -1, // Unlimited
      watchlist_limit: 50,
      price: 999, // ₹999/year
    },
  },
  
  // First month free trial
  TRIAL_DAYS: 30,
};

// --------------------------------------------
// THEME COLORS
// --------------------------------------------
export const COLORS = {
  // Primary Brand Colors
  primary: '#FF6B35',      // Orange (DealHunt brand)
  primaryDark: '#E55A2B',
  primaryLight: '#FF8555',
  
  // Secondary Colors
  secondary: '#4ECDC4',    // Teal
  secondaryDark: '#3DBDB5',
  
  // Neutral Colors
  white: '#FFFFFF',
  black: '#000000',
  gray50: '#FAFAFA',
  gray100: '#F5F5F5',
  gray200: '#EEEEEE',
  gray300: '#E0E0E0',
  gray400: '#BDBDBD',
  gray500: '#9E9E9E',
  gray600: '#757575',
  gray700: '#616161',
  gray800: '#424242',
  gray900: '#212121',
  
  // Status Colors
  success: '#4CAF50',
  successLight: '#E8F5E9',
  error: '#F44336',
  errorLight: '#FFEBEE',
  warning: '#FFC107',
  warningLight: '#FFF8E1',
  info: '#2196F3',
  infoLight: '#E3F2FD',
  
  // Background
  background: '#FFFFFF',
  backgroundSecondary: '#F5F5F5',
  surface: '#FFFFFF',
  
  // Text
  textPrimary: '#212121',
  textSecondary: '#757575',
  textDisabled: '#BDBDBD',
  textOnPrimary: '#FFFFFF',
};

// --------------------------------------------
// REFERRAL REWARDS (Part 5 - Full UI)
// --------------------------------------------
export const REFERRAL_REWARDS = {
  NEW_USER_BONUS: 5,        // +5 searches for new user
  REFERRER_BONUS: 10,       // +10 searches for referrer
  
  MILESTONES: [
    { referrals: 1, reward: '+20 searches', type: 'searches', value: 20 },
    { referrals: 3, reward: '1 month Pro', type: 'subscription', months: 1 },
    { referrals: 5, reward: '2 months Pro', type: 'subscription', months: 2 },
    { referrals: 10, reward: '2 months Premium', type: 'subscription', months: 2, plan: 'premium' },
    { referrals: 25, reward: '4 months Premium (MAX)', type: 'subscription', months: 4, plan: 'premium', isMax: true },
    { referrals: 50, reward: '₹2000 voucher + Badge', type: 'voucher', value: 2000 },
  ],
};

// --------------------------------------------
// ERROR MESSAGES
// --------------------------------------------
export const ERROR_MESSAGES = {
  NETWORK_ERROR: 'Network error. Please check your connection.',
  SERVER_ERROR: 'Server error. Please try again later.',
  INVALID_CREDENTIALS: 'Invalid email or password.',
  EMAIL_IN_USE: 'This email is already registered.',
  WEAK_PASSWORD: 'Password must be at least 8 characters with 1 uppercase letter and 1 number.',
  INVALID_EMAIL: 'Please enter a valid email address.',
  INVALID_REFERRAL: 'Invalid referral code.',
  DEVICE_LIMIT: 'Maximum 3 accounts per device reached.',
  IP_LIMIT: 'Too many signups from your location. Try again tomorrow.',
  TOKEN_EXPIRED: 'Session expired. Please login again.',
  UNKNOWN_ERROR: 'Something went wrong. Please try again.',
};

export default {
  FIREBASE_CONFIG,
  API,
  STORAGE_KEYS,
  VALIDATION,
  APP,
  COLORS,
  REFERRAL_REWARDS,
  ERROR_MESSAGES,
};