// ============================================
// DEALHUNT APP - ROOT NAVIGATOR
// Part 4 Update: Added Streak Check on App Launch
// ============================================

import React, { useEffect, useRef } from 'react';
import { View, Text, StyleSheet, ActivityIndicator, AppState, Image, Alert, Modal, TouchableOpacity } from 'react-native';
import { createStackNavigator } from '@react-navigation/stack';
import { useSelector, useDispatch } from 'react-redux';

// Navigation
import MainTabs from './MainTabs';

// Screens
import LoginScreen from '../screens/auth/LoginScreen';
import PlansScreen from '../screens/subscription/PlansScreen';
import BannedUserScreen from '../screens/auth/BannedUserScreen';
// Store
import {
  checkAuthStatus,
  forceFinishInitialization,
  selectIsAuthenticated,
  selectIsInitializing,
  checkProTrialExpiration,
  selectUser,
  refreshUserData,
  selectSessionExpired,
  selectSessionExpiredMessage,
  clearSessionExpired,
  selectBanInfo,
  clearBanInfo,
} from '../store/authSlice';
import { fetchWatchlist } from '../store/watchlistSlice';
import { fetchPaymentHistory, fetchSubscriptionStatus } from '../store/subscriptionSlice';
import { checkAndMarkStreak } from '../store/streakSlice';
import { selectThemePalette, syncThemeWithPlan } from '../store/themeSlice';

// Constants
import { COLORS, APP } from '../utils/constants';

// --------------------------------------------
// LOADING SCREEN
// --------------------------------------------

const LoadingScreen = () => (
  <View style={styles.loadingContainer}>
    <Image source={require('../../assets/deal.png')} style={styles.loadingLogo} resizeMode="contain" />
    <Text style={styles.loadingAppName}>{APP.NAME}</Text>
    <ActivityIndicator size="large" color={COLORS.primary} style={styles.loadingSpinner} />
    {/* <Text style={styles.loadingText}>Loading...</Text> */}
  </View>
);

// --------------------------------------------
// STACK NAVIGATOR
// --------------------------------------------

const Stack = createStackNavigator();

// --------------------------------------------
// APP NAVIGATOR COMPONENT
// --------------------------------------------

const AppNavigator = () => {
  const dispatch = useDispatch();
  const isAuthenticated = useSelector(selectIsAuthenticated);
  const isInitializing = useSelector(selectIsInitializing);
  const user = useSelector(selectUser);
  const sessionExpired = useSelector(selectSessionExpired);
  const sessionExpiredMessage = useSelector(selectSessionExpiredMessage);
  const themePalette = useSelector(selectThemePalette);
  const banInfo = useSelector(selectBanInfo);
  
  // NEW: Track if we've already checked streak this session
  const hasCheckedStreakRef = useRef(false);
  
  // NEW: Track app state for foreground detection
  const appState = useRef(AppState.currentState);
  const lastSubscriptionFingerprintRef = useRef('');
  const hasShownSessionExpiryAlertRef = useRef(false);

  // Check auth status on mount
  useEffect(() => {
    dispatch(checkAuthStatus());

    // Failsafe: never keep splash/loading forever in case startup checks hang.
    const watchdog = setTimeout(() => {
      dispatch(forceFinishInitialization());
    }, 15000);

    return () => clearTimeout(watchdog);
  }, [dispatch]);

  useEffect(() => {
    if (!sessionExpired || isAuthenticated || isInitializing || hasShownSessionExpiryAlertRef.current) {
      return;
    }

    hasShownSessionExpiryAlertRef.current = true;

    Alert.alert(
      'Welcome back soon',
      sessionExpiredMessage || 'Your session has ended. Please log in again to continue using DealHunt.',
      [
        {
          text: 'Login again',
          onPress: () => {
            dispatch(clearSessionExpired());
            hasShownSessionExpiryAlertRef.current = false;
          },
        },
      ],
      { cancelable: false }
    );
  }, [dispatch, isAuthenticated, isInitializing, sessionExpired, sessionExpiredMessage]);

  const handleDismissBanModal = () => {
    dispatch(clearBanInfo());
  };

  // ✅ NEW: Check streak when user is authenticated and initialization complete
  useEffect(() => {
    // Only run if:
    // 1. User is authenticated
    // 2. Not initializing
    // 3. Haven't checked this session yet
    if (isAuthenticated && !isInitializing && !hasCheckedStreakRef.current) {
      console.log('[AppNavigator] User authenticated, checking streak...');
      
      // Dispatch the streak check
      dispatch(checkAndMarkStreak());
      
      // Mark as checked for this session
      hasCheckedStreakRef.current = true;
    }
    
    // Reset the flag when user logs out
    if (!isAuthenticated) {
      hasCheckedStreakRef.current = false;
      if (!sessionExpired) {
        hasShownSessionExpiryAlertRef.current = false;
      }
    }
  }, [isAuthenticated, isInitializing, dispatch, sessionExpired]);

  // ✅ NEW: Handle app state changes (foreground/background)
  useEffect(() => {
    const subscription = AppState.addEventListener('change', nextAppState => {
      // App coming to foreground
      if (
        appState.current.match(/inactive|background/) &&
        nextAppState === 'active'
      ) {
        console.log('[AppNavigator] App came to foreground');
        
        // Check Pro trial expiration
        dispatch(checkProTrialExpiration());
        if (isAuthenticated) {
          dispatch(refreshUserData());
          dispatch(fetchSubscriptionStatus());
          dispatch(fetchWatchlist());
        }
        
        // Optionally: Re-check streak if user has been away for a while
        // For now, we only check once per app session
      }
      
      appState.current = nextAppState;
    });

    return () => {
      subscription?.remove();
    };
  }, [dispatch, isAuthenticated]);

  // Keep theme synced with user subscription plan.
  useEffect(() => {
    dispatch(syncThemeWithPlan({ plan: user?.plan || 'free' }));
  }, [dispatch, user?.plan]);

  // Auto-refresh app data when subscription details change so all tabs stay in sync.
  useEffect(() => {
    if (!isAuthenticated) {
      lastSubscriptionFingerprintRef.current = '';
      return;
    }

    const fingerprint = `${String(user?.plan || 'free')}|${String(user?.plan_expires_at || '')}`;
    if (!lastSubscriptionFingerprintRef.current) {
      lastSubscriptionFingerprintRef.current = fingerprint;
      return;
    }

    if (lastSubscriptionFingerprintRef.current !== fingerprint) {
      lastSubscriptionFingerprintRef.current = fingerprint;
      dispatch(refreshUserData());
      dispatch(fetchSubscriptionStatus());
      dispatch(fetchPaymentHistory({ limit: 100 }));
      dispatch(fetchWatchlist());
      dispatch(checkAndMarkStreak());
    }
  }, [dispatch, isAuthenticated, user?.plan, user?.plan_expires_at]);

  // ✅ NEW: Periodic Pro trial expiration check (every minute)
  useEffect(() => {
    if (!isAuthenticated) return;
    
    const interval = setInterval(() => {
      dispatch(checkProTrialExpiration());
    }, 60000); // Check every minute
    
    return () => clearInterval(interval);
  }, [isAuthenticated, dispatch]);

  // Show loading while checking auth
  if (isInitializing) {
    return <LoadingScreen />;
  }

  const banMessage =
    banInfo?.message ||
    'Your account has been suspended due to a violation of our terms of service.';
  const banReason = banInfo?.reason;

  if (isAuthenticated) {
    return (
      <>
        <Stack.Navigator screenOptions={{ headerShown: false }}>
          <Stack.Screen
            name="Main"
            component={MainTabs}
            options={{
              animationTypeForReplace: 'push',
            }}
            initialParams={{ appThemePrimary: themePalette.primary }}
          />
          <Stack.Screen
            name="Plans"
            component={PlansScreen}
            options={{
              presentation: 'modal',
              animationTypeForReplace: 'push',
              gestureEnabled: true,
            }}
          />
          <Stack.Screen
            name="BannedUser"
            component={BannedUserScreen}
            options={{
              animationTypeForReplace: 'push',
              gestureEnabled: false,
            }}
          />
        </Stack.Navigator>
        <Modal
          visible={Boolean(banInfo?.isBanned)}
          transparent
          animationType="fade"
          onRequestClose={handleDismissBanModal}
        >
          <View style={styles.banModalOverlay}>
            <View style={styles.banModalCard}>
              <Text style={styles.banModalTitle}>Account Suspended</Text>
              <Text style={styles.banModalMessage}>{banMessage}</Text>
              {banReason ? <Text style={styles.banModalReason}>Reason: {banReason}</Text> : null}
              <TouchableOpacity style={styles.banModalButton} onPress={handleDismissBanModal}>
                <Text style={styles.banModalButtonText}>OK</Text>
              </TouchableOpacity>
            </View>
          </View>
        </Modal>
      </>
    );
  }

  return (
    <>
      <Stack.Navigator screenOptions={{ headerShown: false }}>
        <Stack.Screen
          name="Login"
          component={LoginScreen}
          options={{
            animationTypeForReplace: 'pop',
          }}
        />
      </Stack.Navigator>
      <Modal
        visible={Boolean(banInfo?.isBanned)}
        transparent
        animationType="fade"
        onRequestClose={handleDismissBanModal}
      >
        <View style={styles.banModalOverlay}>
          <View style={styles.banModalCard}>
            <Text style={styles.banModalTitle}>Account Suspended</Text>
            <Text style={styles.banModalMessage}>{banMessage}</Text>
            {banReason ? <Text style={styles.banModalReason}>Reason: {banReason}</Text> : null}
            <TouchableOpacity style={styles.banModalButton} onPress={handleDismissBanModal}>
              <Text style={styles.banModalButtonText}>OK</Text>
            </TouchableOpacity>
          </View>
        </View>
      </Modal>
    </>
  );
};

// --------------------------------------------
// STYLES
// --------------------------------------------

const styles = StyleSheet.create({
  loadingContainer: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    backgroundColor: '#FF6B35',
  },
  
  loadingLogo: {
    width: 120,
    height: 120,
    marginBottom: 16,
  },
  
  loadingAppName: {
    fontSize: 32,
    fontWeight: 'bold',
    color: '#FFFFFF',
    marginBottom: 24,
  },
  
  loadingSpinner: {
    marginBottom: 16,
  },
  
  loadingText: {
    fontSize: 16,
    color: '#FFFFFF',
  },

  banModalOverlay: {
    flex: 1,
    backgroundColor: 'rgba(0, 0, 0, 0.55)',
    justifyContent: 'center',
    alignItems: 'center',
    paddingHorizontal: 20,
  },

  banModalCard: {
    width: '100%',
    maxWidth: 420,
    borderRadius: 14,
    backgroundColor: '#FFFFFF',
    paddingHorizontal: 20,
    paddingVertical: 22,
    elevation: 8,
  },

  banModalTitle: {
    fontSize: 22,
    fontWeight: '700',
    color: '#151515',
    marginBottom: 10,
    textAlign: 'center',
  },

  banModalMessage: {
    fontSize: 15,
    lineHeight: 22,
    color: '#2E2E2E',
    textAlign: 'center',
  },

  banModalReason: {
    marginTop: 12,
    fontSize: 14,
    lineHeight: 20,
    color: '#A33A1D',
    textAlign: 'center',
  },

  banModalButton: {
    marginTop: 18,
    backgroundColor: COLORS.primary,
    paddingVertical: 12,
    borderRadius: 10,
    alignItems: 'center',
  },

  banModalButtonText: {
    color: '#FFFFFF',
    fontSize: 16,
    fontWeight: '700',
  },
});

export default AppNavigator;