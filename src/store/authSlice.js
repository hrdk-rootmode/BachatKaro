// ============================================
// DEALHUNT APP - AUTH REDUX SLICE
// Part 4 Update: Added Pro Trial Management
// ============================================

import { createSlice, createAsyncThunk, createSelector } from '@reduxjs/toolkit';
import { REHYDRATE } from 'redux-persist';

import { signInWithEmail, signUpWithEmail, firebaseSignOut, getFreshIdToken } from '../services/firebase';
import { authAPI } from '../services/api';
import {
  storeAuthToken,
  storeUserData,
  storeFirebaseUid,
  clearAllAuthData,
  getAuthToken,
  getUserData,
} from '../services/storage';

// --------------------------------------------
// INITIAL STATE
// --------------------------------------------

const initialState = {
  // User data from backend
  user: null,
  
  // Firebase user info
  firebaseUser: null,
  
  // Authentication status
  isAuthenticated: false,
  isLoading: false,
  isInitializing: true, // For app startup check
  
  // Error handling
  error: null,
  
  // Referral
  referralCode: null, // User's own referral code
  referralValid: null, // Validation result for entered code
  
  // ✅ NEW: Pro Trial System (Part 4)
  isPro: false,                    // Permanent Pro status from backend
  proTrialActive: false,           // Temporary trial from streak rewards
  proTrialExpiresAt: null,         // ISO timestamp when trial ends
  proTrialDurationHours: null,     // How many hours the trial lasts

  // Session expiry handling
  sessionExpired: false,
  sessionExpiredMessage: null,
  
  // Ban information
  banInfo: null, // Store ban details for navigation
  accountBlocked: false, // Flag to indicate if account is blocked
};

// --------------------------------------------
// HELPERS
// --------------------------------------------

const withTimeout = (promise, timeoutMs, label) => {
  return Promise.race([
    promise,
    new Promise((_, reject) => {
      setTimeout(() => reject(new Error(`${label} timed out`)), timeoutMs);
    }),
  ]);
};

const buildFallbackUserFromFirebase = (firebaseUser) => ({
  uid: firebaseUser?.uid,
  firebase_uid: firebaseUser?.uid,
  email: firebaseUser?.email,
  plan: 'free',
  daily_limit: 10,
  searches_today: 0,
  watchlist_count: 0,
  current_streak: 0,
});

// ✅ NEW: Check if Pro trial is still valid
const isProTrialValid = (expiresAt) => {
  if (!expiresAt) return false;
  return new Date(expiresAt).getTime() > Date.now();
};

// --------------------------------------------
// ASYNC THUNKS
// --------------------------------------------

/**
 * Login with email and password
 */
export const loginWithEmail = createAsyncThunk(
  'auth/loginWithEmail',
  async ({ email, password }, { rejectWithValue }) => {
    try {
      // Step 1: Firebase authentication
      const firebaseResult = await signInWithEmail(email, password);
      
      if (!firebaseResult.success) {
        return rejectWithValue(firebaseResult.error);
      }
      
      // Step 2: Store token ONCE
      await storeAuthToken(firebaseResult.idToken);
      await storeFirebaseUid(firebaseResult.user.uid);
      
      // Step 3: Wait 1 second to avoid clock skew
      await new Promise(resolve => setTimeout(resolve, 1000));
      
      // Step 4: Single backend call with retry
      let backendResult = await authAPI.getMe();
      
      if (!backendResult.success && backendResult.statusCode === 401) {
        // Retry only for expired/invalid auth tokens.
        const freshToken = await getFreshIdToken(true);
        if (freshToken.success) {
          await storeAuthToken(freshToken.idToken);
          backendResult = await authAPI.getMe();
        }
      }
        
      if (!backendResult.success) {
        // If the backend is temporarily unavailable, let the user in with
        // the Firebase identity and sync backend data later.
        const fallbackUser = buildFallbackUserFromFirebase(firebaseResult.user);
        await storeUserData(fallbackUser);

        return {
          user: fallbackUser,
          firebaseUser: firebaseResult.user,
          idToken: firebaseResult.idToken,
          backendSync: false,
        };
      }
      
      await storeUserData(backendResult.data);
      
      return {
        user: backendResult.data,
        firebaseUser: firebaseResult.user,
        idToken: firebaseResult.idToken,
      };
    } catch (error) {
      await clearAllAuthData();
      return rejectWithValue(error.message || 'Login failed');
    }
  }
);

/**
 * Signup with email and password
 */
export const signupWithEmail = createAsyncThunk(
  'auth/signupWithEmail',
  async ({ email, password, referralCode }, { rejectWithValue }) => {
    try {
      // Step 1: Firebase create user
      const firebaseResult = await signUpWithEmail(email, password);
      
      if (!firebaseResult.success) {
        return rejectWithValue(firebaseResult.error);
      }
      
      // Step 2: Store Firebase token
      await storeAuthToken(firebaseResult.idToken);
      await storeFirebaseUid(firebaseResult.user.uid);

      // Ensure we use a freshly minted token before backend bootstrap.
      const freshTokenResult = await getFreshIdToken(true);
      if (freshTokenResult.success && freshTokenResult.idToken) {
        await storeAuthToken(freshTokenResult.idToken);
      }
      
      // Step 3: Get/create user profile from backend
      // Backend auto-creates user on first /auth/me call
      // If referral code provided, backend will process it
      let backendResult = await authAPI.getMe();

      // One more hard retry for 401 with a forced fresh token.
      if (!backendResult.success && backendResult.statusCode === 401) {
        const retryTokenResult = await getFreshIdToken(true);
        if (retryTokenResult.success && retryTokenResult.idToken) {
          await storeAuthToken(retryTokenResult.idToken);
          backendResult = await authAPI.getMe();
        }
      }
      
      if (!backendResult.success) {
        if (backendResult.statusCode === 401) {
          const fallbackUser = buildFallbackUserFromFirebase(firebaseResult.user);
          await storeUserData(fallbackUser);
          return {
            user: fallbackUser,
            firebaseUser: firebaseResult.user,
            idToken: firebaseResult.idToken,
            isNewUser: true,
            backendSync: false,
          };
        }
        return rejectWithValue(backendResult.error);
      }
      
      // Step 4: Store user data
      await storeUserData(backendResult.data);
      
      return {
        user: backendResult.data,
        firebaseUser: firebaseResult.user,
        idToken: firebaseResult.idToken,
        isNewUser: true,
      };
    } catch (error) {
      console.error('Signup error:', error);
      return rejectWithValue(error.message || 'Signup failed');
    }
  }
);

/**
 * Check if user is already logged in (app startup)
 */
export const checkAuthStatus = createAsyncThunk(
  'auth/checkAuthStatus',
  async (_, { rejectWithValue }) => {
    let storedUser = null;
    try {
      // Step 1: Check for stored token
      const storedToken = await withTimeout(getAuthToken(), 5000, 'Read auth token');
      storedUser = await withTimeout(getUserData(), 5000, 'Read user data');
      
      if (!storedToken || !storedUser) {
        return { isLoggedIn: false, sessionExpired: false };
      }
      
      // Step 2: Verify token is still valid by calling backend
      let backendResult = await authAPI.getMe();

      // If token is expired, attempt a forced token refresh and retry once.
      if (!backendResult.success && backendResult.statusCode === 401) {
        const refreshResult = await withTimeout(getFreshIdToken(true), 8000, 'Refresh Firebase token');
        if (refreshResult.success && refreshResult.idToken) {
          await storeAuthToken(refreshResult.idToken);
          backendResult = await authAPI.getMe();
        }
      }
      
      if (!backendResult.success) {
        if (backendResult.statusCode === 401 && storedUser) {
          await clearAllAuthData();
          return {
            isLoggedIn: false,
            sessionExpired: true,
            sessionExpiredMessage: 'Your session has ended. Please log in again to continue.',
          };
        }

        // If the backend is temporarily unreachable, keep the cached user so
        // the app can still open and retry sync later.
        if (backendResult.statusCode === 0 && storedUser) {
          return {
            isLoggedIn: true,
            user: storedUser,
            backendSync: false,
            sessionExpired: false,
          };
        }

        // Token invalid, clear storage
        await clearAllAuthData();
        return { isLoggedIn: false, sessionExpired: false };
      }
      
      // Step 3: Update stored user data (might have changed)
      await storeUserData(backendResult.data);
      
      return {
        isLoggedIn: true,
        user: backendResult.data,
        sessionExpired: false,
      };
    } catch (error) {
      console.error('Auth check error:', error);

      // Keep users signed in with cached profile when startup verification stalls.
      if (storedUser) {
        return {
          isLoggedIn: true,
          user: storedUser,
          backendSync: false,
          sessionExpired: false,
        };
      }

      await clearAllAuthData();
      return { isLoggedIn: false, sessionExpired: false };
    }
  }
);

/**
 * Logout user
 */
export const logout = createAsyncThunk(
  'auth/logout',
  async (_, { rejectWithValue }) => {
    try {
      // Step 1: Logout from backend
      await authAPI.logout();
      
      // Step 2: Logout from Firebase
      await firebaseSignOut();
      
      // Step 3: Clear all stored data
      await clearAllAuthData();
      
      return { success: true };
    } catch (error) {
      console.error('Logout error:', error);
      // Still clear local data even if API call fails
      await clearAllAuthData();
      return { success: true };
    }
  }
);

/**
 * Verify referral code
 */
export const verifyReferral = createAsyncThunk(
  'auth/verifyReferral',
  async (referralCode, { rejectWithValue }) => {
    try {
      const result = await authAPI.verifyReferralCode(referralCode);
      
      if (!result.success) {
        return rejectWithValue(result.error || 'Invalid referral code');
      }
      
      return result.data;
    } catch (error) {
      return rejectWithValue(error.message || 'Failed to verify referral code');
    }
  }
);

/**
 * Refresh user data from backend
 */
export const refreshUserData = createAsyncThunk(
  'auth/refreshUserData',
  async (_, { rejectWithValue }) => {
    try {
      const result = await authAPI.getMe();
      
      if (!result.success) {
        return rejectWithValue(result.error);
      }
      
      await storeUserData(result.data);
      return result.data;
    } catch (error) {
      return rejectWithValue(error.message);
    }
  }
);

// --------------------------------------------
// AUTH SLICE
// --------------------------------------------

const authSlice = createSlice({
  name: 'auth',
  initialState,
  
  reducers: {
    // Force end initialization if startup flow hangs
    forceFinishInitialization: (state) => {
      state.isInitializing = false;
      state.isLoading = false;
    },

    // Clear error
    clearError: (state) => {
      state.error = null;
    },
    
    // Clear referral validation
    clearReferralValidation: (state) => {
      state.referralValid = null;
    },
    
    // Update user data locally
    updateUserLocal: (state, action) => {
      if (state.user) {
        state.user = { ...state.user, ...action.payload };
      }
    },
    
    // Set loading state
    setLoading: (state, action) => {
      state.isLoading = action.payload;
    },
    
    // Reset auth state (for testing)
    resetAuth: () => initialState,

    // Mark session expired from API / 401 recovery
    markSessionExpired: (state, action) => {
      state.isAuthenticated = false;
      state.isLoading = false;
      state.isInitializing = false;
      state.user = null;
      state.firebaseUser = null;
      state.referralCode = null;
      state.error = null;
      state.isPro = false;
      state.proTrialActive = false;
      state.proTrialExpiresAt = null;
      state.proTrialDurationHours = null;
      state.sessionExpired = true;
      state.sessionExpiredMessage = action.payload?.message || 'Your session has ended. Please log in again to continue.';
    },

    clearSessionExpired: (state) => {
      state.sessionExpired = false;
      state.sessionExpiredMessage = null;
    },
    
    // ✅ NEW: Activate Pro Trial (Part 4)
    activateProTrial: (state, action) => {
      const { durationHours } = action.payload;
      
      if (!durationHours || durationHours <= 0) {
        console.warn('[AuthSlice] Invalid trial duration:', durationHours);
        return;
      }
      
      const now = Date.now();
      const expiresAt = new Date(now + durationHours * 60 * 60 * 1000).toISOString();
      
      state.proTrialActive = true;
      state.proTrialExpiresAt = expiresAt;
      state.proTrialDurationHours = durationHours;
      
      console.log(`[AuthSlice] ✅ Pro trial activated: ${durationHours}h (expires: ${expiresAt})`);
    },
    
    // ✅ NEW: Clear Pro Trial (when expired or manually cleared)
    clearProTrial: (state) => {
      state.proTrialActive = false;
      state.proTrialExpiresAt = null;
      state.proTrialDurationHours = null;
      console.log('[AuthSlice] Pro trial cleared');
    },
    
    // ✅ NEW: Check if Pro trial has expired (call this periodically)
    checkProTrialExpiration: (state) => {
      if (state.proTrialActive && state.proTrialExpiresAt) {
        if (!isProTrialValid(state.proTrialExpiresAt)) {
          console.log('[AuthSlice] Pro trial expired');
          state.proTrialActive = false;
          state.proTrialExpiresAt = null;
          state.proTrialDurationHours = null;
        }
      }
    },

    // Development-only helper: nudge trial expiry forward/backward for faster testing.
    debugAdjustProTrialMinutesForDev: (state, action) => {
      const minutesDelta = Number(action.payload?.minutesDelta || 0);
      if (!Number.isFinite(minutesDelta) || minutesDelta === 0) {
        return;
      }

      if (!state.proTrialActive || !state.proTrialExpiresAt) {
        console.warn('[AuthSlice] Cannot adjust trial time: no active trial');
        return;
      }

      const now = Date.now();
      const currentExpiry = new Date(state.proTrialExpiresAt).getTime();
      const safeCurrentExpiry = Number.isFinite(currentExpiry) ? currentExpiry : now;
      const adjustedExpiry = safeCurrentExpiry + minutesDelta * 60 * 1000;

      if (adjustedExpiry <= now) {
        state.proTrialActive = false;
        state.proTrialExpiresAt = null;
        state.proTrialDurationHours = null;
        return;
      }

      state.proTrialExpiresAt = new Date(adjustedExpiry).toISOString();
      state.proTrialDurationHours = Math.max(1, Math.ceil((adjustedExpiry - now) / (1000 * 60 * 60)));
    },

    // Handle banned user action from API
    accountBlocked: (state, action) => {
      const { isBanned, reason, blockedAt, message } = action.payload || {};
      
      state.accountBlocked = true;
      state.isAuthenticated = false;
      state.isLoading = false;
      state.isInitializing = false;
      state.user = null;
      state.firebaseUser = null;
      state.referralCode = null;
      state.error = message || 'Your account has been blocked.';
      state.isPro = false;
      state.proTrialActive = false;
      state.proTrialExpiresAt = null;
      state.proTrialDurationHours = null;
      state.sessionExpired = false;
      state.sessionExpiredMessage = null;
      
      // Store ban info for navigation
      state.banInfo = {
        isBanned,
        reason: reason || 'Violation of terms of service',
        blockedAt: blockedAt || null,
        message: message || 'Your account has been blocked.'
      };
      
      console.log('[AuthSlice] Account blocked:', { isBanned, reason, blockedAt });
    },

    clearBanInfo: (state) => {
      state.banInfo = null;
      state.accountBlocked = false;
    },
  },
  
  extraReducers: (builder) => {
    // --------------------------------------------
    // REHYDRATION GUARD
    // Reset volatile UI flags that should not survive app restarts
    // ✅ UPDATED: Check Pro trial expiration on rehydration
    // --------------------------------------------
    builder.addCase(REHYDRATE, (state) => {
      state.isLoading = false;
      state.isInitializing = true;
      state.error = null;
      state.referralValid = null;
      
      // Check if Pro trial expired while app was closed
      if (state.proTrialActive && state.proTrialExpiresAt) {
        if (!isProTrialValid(state.proTrialExpiresAt)) {
          console.log('[AuthSlice] Pro trial expired during rehydration');
          state.proTrialActive = false;
          state.proTrialExpiresAt = null;
          state.proTrialDurationHours = null;
        }
      }
    });

    // --------------------------------------------
    // LOGIN
    // ✅ UPDATED: Set isPro from user data
    // --------------------------------------------
    builder.addCase(loginWithEmail.pending, (state) => {
      state.isLoading = true;
      state.error = null;
    });
    
    builder.addCase(loginWithEmail.fulfilled, (state, action) => {
      state.isLoading = false;
      state.isAuthenticated = true;
      state.isInitializing = false;
      state.user = action.payload.user;
      state.firebaseUser = action.payload.firebaseUser;
      state.referralCode = action.payload.user?.referral_code;
      state.error = null;
      state.sessionExpired = false;
      state.sessionExpiredMessage = null;
      
      // ✅ NEW: Set permanent Pro status from user plan
      const userPlan = action.payload.user?.plan?.toLowerCase();
      state.isPro = userPlan === 'pro' || userPlan === 'premium';
    });
    
    builder.addCase(loginWithEmail.rejected, (state, action) => {
      state.isLoading = false;
      state.isAuthenticated = false;
      state.error = action.payload || 'Login failed';
    });
    
    // --------------------------------------------
    // SIGNUP
    // ✅ UPDATED: Set isPro from user data
    // --------------------------------------------
    builder.addCase(signupWithEmail.pending, (state) => {
      state.isLoading = true;
      state.error = null;
    });
    
    builder.addCase(signupWithEmail.fulfilled, (state, action) => {
      state.isLoading = false;
      state.isAuthenticated = true;
      state.isInitializing = false;
      state.user = action.payload.user;
      state.firebaseUser = action.payload.firebaseUser;
      state.referralCode = action.payload.user?.referral_code;
      state.error = null;
      state.sessionExpired = false;
      state.sessionExpiredMessage = null;
      
      // ✅ NEW: Set permanent Pro status from user plan
      const userPlan = action.payload.user?.plan?.toLowerCase();
      state.isPro = userPlan === 'pro' || userPlan === 'premium';
    });
    
    builder.addCase(signupWithEmail.rejected, (state, action) => {
      state.isLoading = false;
      state.isAuthenticated = false;
      state.error = action.payload || 'Signup failed';
    });
    
    // --------------------------------------------
    // CHECK AUTH STATUS
    // ✅ UPDATED: Set isPro from user data
    // --------------------------------------------
    builder.addCase(checkAuthStatus.pending, (state) => {
      state.isInitializing = true;
    });
    
    builder.addCase(checkAuthStatus.fulfilled, (state, action) => {
      state.isInitializing = false;
      state.isAuthenticated = action.payload.isLoggedIn;
      state.user = action.payload.user || null;
      state.referralCode = action.payload.user?.referral_code || null;
      state.sessionExpired = Boolean(action.payload.sessionExpired);
      state.sessionExpiredMessage = action.payload.sessionExpiredMessage || null;
      
      // ✅ NEW: Set permanent Pro status from user plan
      if (action.payload.user) {
        const userPlan = action.payload.user?.plan?.toLowerCase();
        state.isPro = userPlan === 'pro' || userPlan === 'premium';
      } else {
        state.isPro = false;
      }
    });
    
    builder.addCase(checkAuthStatus.rejected, (state) => {
      state.isInitializing = false;
      state.isAuthenticated = false;
      state.user = null;
      state.isPro = false;
      state.sessionExpired = false;
      state.sessionExpiredMessage = null;
    });
    
    // --------------------------------------------
    // LOGOUT
    // ✅ UPDATED: Clear Pro trial on logout
    // --------------------------------------------
    builder.addCase(logout.pending, (state) => {
      state.isLoading = true;
    });
    
    builder.addCase(logout.fulfilled, (state) => {
      state.isLoading = false;
      state.isAuthenticated = false;
      state.user = null;
      state.firebaseUser = null;
      state.referralCode = null;
      state.error = null;
      state.sessionExpired = false;
      state.sessionExpiredMessage = null;
      
      // ✅ NEW: Clear Pro trial
      state.isPro = false;
      state.proTrialActive = false;
      state.proTrialExpiresAt = null;
      state.proTrialDurationHours = null;
    });
    
    builder.addCase(logout.rejected, (state) => {
      // Still logout locally even if API fails
      state.isLoading = false;
      state.isAuthenticated = false;
      state.user = null;
      state.firebaseUser = null;
      state.sessionExpired = false;
      state.sessionExpiredMessage = null;
      
      // ✅ NEW: Clear Pro trial
      state.isPro = false;
      state.proTrialActive = false;
      state.proTrialExpiresAt = null;
      state.proTrialDurationHours = null;
    });
    
    // --------------------------------------------
    // VERIFY REFERRAL
    // --------------------------------------------
    builder.addCase(verifyReferral.pending, (state) => {
      state.referralValid = null;
    });
    
    builder.addCase(verifyReferral.fulfilled, (state, action) => {
      state.referralValid = {
        valid: true,
        data: action.payload,
      };
    });
    
    builder.addCase(verifyReferral.rejected, (state, action) => {
      state.referralValid = {
        valid: false,
        error: action.payload,
      };
    });
    
    // --------------------------------------------
    // REFRESH USER DATA
    // ✅ UPDATED: Update isPro when refreshing user data
    // --------------------------------------------
    builder.addCase(refreshUserData.fulfilled, (state, action) => {
      state.user = action.payload;
      state.referralCode = action.payload?.referral_code;
      
      // ✅ NEW: Update Pro status
      const userPlan = action.payload?.plan?.toLowerCase();
      state.isPro = userPlan === 'pro' || userPlan === 'premium';
    });
  },
});

// --------------------------------------------
// EXPORTS
// --------------------------------------------

export const {
  forceFinishInitialization,
  clearError,
  clearReferralValidation,
  updateUserLocal,
  setLoading,
  resetAuth,
  markSessionExpired,
  clearSessionExpired,
  activateProTrial,          // ✅ NEW
  clearProTrial,             // ✅ NEW
  checkProTrialExpiration,   // ✅ NEW
  debugAdjustProTrialMinutesForDev,
  accountBlocked,            // ✅ NEW: Handle banned user
  clearBanInfo,
} = authSlice.actions;

// Selectors
export const selectUser = (state) => state.auth.user;
export const selectIsAuthenticated = (state) => state.auth.isAuthenticated;
export const selectIsLoading = (state) => state.auth.isLoading;
export const selectIsInitializing = (state) => state.auth.isInitializing;
export const selectAuthError = (state) => state.auth.error;
export const selectReferralCode = (state) => state.auth.referralCode;
export const selectReferralValid = (state) => state.auth.referralValid;
export const selectSessionExpired = (state) => state.auth.sessionExpired;
export const selectSessionExpiredMessage = (state) => state.auth.sessionExpiredMessage;

// ✅ NEW: Pro Trial Selectors
export const selectIsPermanentPro = (state) => state.auth.isPro;
export const selectProTrialActive = (state) => state.auth.proTrialActive;
export const selectProTrialExpiresAt = (state) => state.auth.proTrialExpiresAt;
export const selectProTrialDurationHours = (state) => state.auth.proTrialDurationHours;

/**
 * ✅ NEW: Master Pro selector
 * Returns true if user has EITHER permanent Pro OR active trial
 */
export const selectIsPro = (state) => {
  const permanentPro = state.auth.isPro;
  const trialActive = state.auth.proTrialActive;
  const trialExpiry = state.auth.proTrialExpiresAt;

  if (permanentPro) return true;
  return Boolean(trialActive && trialExpiry);
};

/**
 * ✅ NEW: Get Pro trial info for UI display
 */
export const selectProTrialInfo = createSelector(
  [selectProTrialActive, selectProTrialExpiresAt, selectProTrialDurationHours],
  (isActive, expiresAt, durationHours) => {
    if (!isActive || !expiresAt) {
      return null;
    }

    return {
      isActive: true,
      expiresAt,
      durationHours,
    };
  }
);

// ✅ NEW: Ban info selector
export const selectBanInfo = (state) => state.auth.banInfo;

export default authSlice.reducer;