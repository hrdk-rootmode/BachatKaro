// ============================================
// DEALHUNT APP - CUSTOM AUTH HOOK
// ============================================

import { useCallback, useEffect } from 'react';
import { useDispatch, useSelector } from 'react-redux';

import {
  loginWithEmail,
  signupWithEmail,
  logout,
  checkAuthStatus,
  verifyReferral,
  refreshUserData,
  clearError,
  clearReferralValidation,
  selectUser,
  selectIsAuthenticated,
  selectIsLoading,
  selectIsInitializing,
  selectAuthError,
  selectReferralCode,
  selectReferralValid,
} from '../store/authSlice';

import { validateLoginForm, validateSignupForm } from '../utils/validators';

// --------------------------------------------
// USE AUTH HOOK
// --------------------------------------------

export const useAuth = () => {
  const dispatch = useDispatch();
  
  // Selectors
  const user = useSelector(selectUser);
  const isAuthenticated = useSelector(selectIsAuthenticated);
  const isLoading = useSelector(selectIsLoading);
  const isInitializing = useSelector(selectIsInitializing);
  const error = useSelector(selectAuthError);
  const referralCode = useSelector(selectReferralCode);
  const referralValid = useSelector(selectReferralValid);

  // --------------------------------------------
  // LOGIN
  // --------------------------------------------
  
  const login = useCallback(async (email, password) => {
    // Validate form
    const validation = validateLoginForm(email, password);
    
    if (!validation.valid) {
      return {
        success: false,
        errors: validation.errors,
      };
    }
    
    // Dispatch login action
    const result = await dispatch(loginWithEmail({
      email: validation.values.email,
      password,
    }));
    
    if (loginWithEmail.fulfilled.match(result)) {
      return { success: true, user: result.payload.user };
    } else {
      return { success: false, error: result.payload };
    }
  }, [dispatch]);

  // --------------------------------------------
  // SIGNUP
  // --------------------------------------------
  
  const signup = useCallback(async (email, password, confirmPassword, referralCodeInput) => {
    // Validate form
    const validation = validateSignupForm(email, password, confirmPassword, referralCodeInput);
    
    if (!validation.valid) {
      return {
        success: false,
        errors: validation.errors,
      };
    }
    
    // Dispatch signup action
    const result = await dispatch(signupWithEmail({
      email: validation.values.email,
      password,
      referralCode: validation.values.referralCode,
    }));
    
    if (signupWithEmail.fulfilled.match(result)) {
      return { success: true, user: result.payload.user };
    } else {
      return { success: false, error: result.payload };
    }
  }, [dispatch]);

  // --------------------------------------------
  // LOGOUT
  // --------------------------------------------
  
  const signOut = useCallback(async () => {
    const result = await dispatch(logout());
    return { success: true };
  }, [dispatch]);

  // --------------------------------------------
  // CHECK AUTH STATUS (App startup)
  // --------------------------------------------
  
  const checkAuth = useCallback(async () => {
    const result = await dispatch(checkAuthStatus());
    return checkAuthStatus.fulfilled.match(result);
  }, [dispatch]);

  // --------------------------------------------
  // VERIFY REFERRAL CODE
  // --------------------------------------------
  
  const checkReferralCode = useCallback(async (code) => {
    if (!code || code.trim() === '') {
      dispatch(clearReferralValidation());
      return { valid: true, skipped: true };
    }
    
    const result = await dispatch(verifyReferral(code.trim().toUpperCase()));
    
    if (verifyReferral.fulfilled.match(result)) {
      return { valid: true, data: result.payload };
    } else {
      return { valid: false, error: result.payload };
    }
  }, [dispatch]);

  // --------------------------------------------
  // REFRESH USER DATA
  // --------------------------------------------
  
  const refreshUser = useCallback(async () => {
    const result = await dispatch(refreshUserData());
    return refreshUserData.fulfilled.match(result);
  }, [dispatch]);

  // --------------------------------------------
  // CLEAR ERROR
  // --------------------------------------------
  
  const clearAuthError = useCallback(() => {
    dispatch(clearError());
  }, [dispatch]);

  // --------------------------------------------
  // CLEAR REFERRAL VALIDATION
  // --------------------------------------------
  
  const clearReferral = useCallback(() => {
    dispatch(clearReferralValidation());
  }, [dispatch]);

  // --------------------------------------------
  // COMPUTED VALUES
  // --------------------------------------------
  
  const userPlan = user?.plan || 'free';
  const searchesRemaining = user?.searches_today !== undefined
    ? (user?.daily_limit || 10) - user.searches_today
    : null;
  const watchlistCount = user?.watchlist_count || 0;
  const currentStreak = user?.current_streak || 0;

  // --------------------------------------------
  // RETURN
  // --------------------------------------------
  
  return {
    // State
    user,
    isAuthenticated,
    isLoading,
    isInitializing,
    error,
    referralCode,
    referralValid,
    
    // Computed
    userPlan,
    searchesRemaining,
    watchlistCount,
    currentStreak,
    
    // Actions
    login,
    signup,
    signOut,
    checkAuth,
    checkReferralCode,
    refreshUser,
    clearAuthError,
    clearReferral,
  };
};

export default useAuth;