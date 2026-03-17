// ============================================
// DEALHUNT APP - AUTH REDUX SLICE
// ============================================

import { createSlice, createAsyncThunk } from '@reduxjs/toolkit';

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
      
      // Step 2: Store Firebase token
      await storeAuthToken(firebaseResult.idToken);
      await storeFirebaseUid(firebaseResult.user.uid);
      
      // Step 3: Get user profile from backend (auto-creates if new)
      const backendResult = await authAPI.getMe();
      
      if (!backendResult.success) {
        return rejectWithValue(backendResult.error);
      }
      
      // Step 4: Store user data
      await storeUserData(backendResult.data);
      
      return {
        user: backendResult.data,
        firebaseUser: firebaseResult.user,
        idToken: firebaseResult.idToken,
      };
    } catch (error) {
      console.error('Login error:', error);
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
      
      // Step 3: Get/create user profile from backend
      // Backend auto-creates user on first /auth/me call
      // If referral code provided, backend will process it
      const backendResult = await authAPI.getMe();
      
      if (!backendResult.success) {
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
    try {
      // Step 1: Check for stored token
      const storedToken = await getAuthToken();
      const storedUser = await getUserData();
      
      if (!storedToken || !storedUser) {
        return { isLoggedIn: false };
      }
      
      // Step 2: Verify token is still valid by calling backend
      const backendResult = await authAPI.getMe();
      
      if (!backendResult.success) {
        // Token invalid, clear storage
        await clearAllAuthData();
        return { isLoggedIn: false };
      }
      
      // Step 3: Update stored user data (might have changed)
      await storeUserData(backendResult.data);
      
      return {
        isLoggedIn: true,
        user: backendResult.data,
      };
    } catch (error) {
      console.error('Auth check error:', error);
      await clearAllAuthData();
      return { isLoggedIn: false };
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
  },
  
  extraReducers: (builder) => {
    // --------------------------------------------
    // LOGIN
    // --------------------------------------------
    builder.addCase(loginWithEmail.pending, (state) => {
      state.isLoading = true;
      state.error = null;
    });
    
    builder.addCase(loginWithEmail.fulfilled, (state, action) => {
      state.isLoading = false;
      state.isAuthenticated = true;
      state.user = action.payload.user;
      state.firebaseUser = action.payload.firebaseUser;
      state.referralCode = action.payload.user?.referral_code;
      state.error = null;
    });
    
    builder.addCase(loginWithEmail.rejected, (state, action) => {
      state.isLoading = false;
      state.isAuthenticated = false;
      state.error = action.payload || 'Login failed';
    });
    
    // --------------------------------------------
    // SIGNUP
    // --------------------------------------------
    builder.addCase(signupWithEmail.pending, (state) => {
      state.isLoading = true;
      state.error = null;
    });
    
    builder.addCase(signupWithEmail.fulfilled, (state, action) => {
      state.isLoading = false;
      state.isAuthenticated = true;
      state.user = action.payload.user;
      state.firebaseUser = action.payload.firebaseUser;
      state.referralCode = action.payload.user?.referral_code;
      state.error = null;
    });
    
    builder.addCase(signupWithEmail.rejected, (state, action) => {
      state.isLoading = false;
      state.isAuthenticated = false;
      state.error = action.payload || 'Signup failed';
    });
    
    // --------------------------------------------
    // CHECK AUTH STATUS
    // --------------------------------------------
    builder.addCase(checkAuthStatus.pending, (state) => {
      state.isInitializing = true;
    });
    
    builder.addCase(checkAuthStatus.fulfilled, (state, action) => {
      state.isInitializing = false;
      state.isAuthenticated = action.payload.isLoggedIn;
      state.user = action.payload.user || null;
      state.referralCode = action.payload.user?.referral_code || null;
    });
    
    builder.addCase(checkAuthStatus.rejected, (state) => {
      state.isInitializing = false;
      state.isAuthenticated = false;
      state.user = null;
    });
    
    // --------------------------------------------
    // LOGOUT
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
    });
    
    builder.addCase(logout.rejected, (state) => {
      // Still logout locally even if API fails
      state.isLoading = false;
      state.isAuthenticated = false;
      state.user = null;
      state.firebaseUser = null;
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
    // --------------------------------------------
    builder.addCase(refreshUserData.fulfilled, (state, action) => {
      state.user = action.payload;
      state.referralCode = action.payload?.referral_code;
    });
  },
});

// --------------------------------------------
// EXPORTS
// --------------------------------------------

export const {
  clearError,
  clearReferralValidation,
  updateUserLocal,
  setLoading,
  resetAuth,
} = authSlice.actions;

// Selectors
export const selectUser = (state) => state.auth.user;
export const selectIsAuthenticated = (state) => state.auth.isAuthenticated;
export const selectIsLoading = (state) => state.auth.isLoading;
export const selectIsInitializing = (state) => state.auth.isInitializing;
export const selectAuthError = (state) => state.auth.error;
export const selectReferralCode = (state) => state.auth.referralCode;
export const selectReferralValid = (state) => state.auth.referralValid;

export default authSlice.reducer;