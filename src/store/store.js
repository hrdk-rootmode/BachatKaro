// ============================================
// DEALHUNT APP - REDUX STORE CONFIGURATION
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

// --------------------------------------------
// PERSIST CONFIGURATION
// --------------------------------------------

const persistConfig = {
  key: 'dealhunt_root',
  version: 1,
  storage: AsyncStorage,
  whitelist: ['auth'], // Only persist auth state
  // blacklist: [], // Don't persist these
};

// --------------------------------------------
// ROOT REDUCER
// --------------------------------------------

const rootReducer = combineReducers({
  auth: authReducer,
  // Add more slices here in future parts:
  // search: searchReducer,     // Part 2
  // watchlist: watchlistReducer, // Part 3
  // streak: streakReducer,     // Part 4
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
 *   }
 * }
 */

export default store;