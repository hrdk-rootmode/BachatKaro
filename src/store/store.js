// ============================================
// DEALHUNT APP - REDUX STORE CONFIGURATION (UPDATED)
// ============================================

import { configureStore, combineReducers } from '@reduxjs/toolkit';
import {
  persistStore,
  persistReducer,
  FLUSH,
  REHYDRATE,
  PAUSE,
  PERSIST,
  PURGE,
  REGISTER,
} from 'redux-persist';
import AsyncStorage from '@react-native-async-storage/async-storage';

// Import slices
import authReducer from './authSlice';
import searchReducer from './searchSlice';
import watchlistReducer from './watchlistSlice'; 
import streakReducer from './streakSlice';
// Part 3
// --------------------------------------------
// PERSIST CONFIGURATION
// --------------------------------------------

const persistConfig = {
  key: 'dealhunt_root',
  version: 1,
  storage: AsyncStorage,
  whitelist: ['auth'], // Only persist auth state (NOT search)
  // blacklist: ['search'], // Alternative way
};

// --------------------------------------------
// ROOT REDUCER
// --------------------------------------------

const rootReducer = combineReducers({
  auth: authReducer,
  search: searchReducer, // NEW: Added search reducer
  // Future slices:
  watchlist: watchlistReducer, // Part 3
  streak: streakReducer,       // Part 4
  // subscription: subscriptionReducer, // Part 5
});

// --------------------------------------------
// PERSISTED REDUCER
// --------------------------------------------

const persistedReducer = persistReducer(persistConfig, rootReducer);

// --------------------------------------------
// STORE CONFIGURATION
// --------------------------------------------

export const store = configureStore({
  reducer: persistedReducer,
  middleware: (getDefaultMiddleware) =>
    getDefaultMiddleware({
      serializableCheck: {
        // Ignore these action types (redux-persist)
        ignoredActions: [FLUSH, REHYDRATE, PAUSE, PERSIST, PURGE, REGISTER],
      },
    }),
  devTools: __DEV__, // Enable Redux DevTools in development
});

// --------------------------------------------
// PERSISTOR
// --------------------------------------------

export const persistor = persistStore(store);

// --------------------------------------------
// TYPES (For reference in JavaScript)
// --------------------------------------------

/**
 * RootState shape:
 * {
 *   auth: {
 *     user: Object | null,
 *     firebaseUser: Object | null,
 *     isAuthenticated: boolean,
 *     isLoading: boolean,
 *     isInitializing: boolean,
 *     error: string | null,
 *     referralCode: string | null,
 *     referralValid: Object | null,
 *   },
 *   search: {
 *     query: string,
 *     filters: Object,
 *     results: Array,
 *     totalResults: number,
 *     currentPage: number,
 *     hasMore: boolean,
 *     isSearching: boolean,
 *     searchError: string | null,
 *     recentSearches: Array,
 *     trendingProducts: Array,
 *     isTrendingLoading: boolean,
 *     currentProduct: Object | null,
 *   }
 * }
 */

export default store;