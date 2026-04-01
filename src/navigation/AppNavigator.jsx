// ============================================
// DEALHUNT APP - ROOT NAVIGATOR
// Part 4 Update: Added Streak Check on App Launch
// ============================================

import React, { useEffect, useRef } from 'react';
import { View, Text, StyleSheet, ActivityIndicator, AppState } from 'react-native';
import { createStackNavigator } from '@react-navigation/stack';
import { useSelector, useDispatch } from 'react-redux';

// Navigation
import MainTabs from './MainTabs';

// Screens
import LoginScreen from '../screens/auth/LoginScreen';

// Store
import {
  checkAuthStatus,
  forceFinishInitialization,
  selectIsAuthenticated,
  selectIsInitializing,
  checkProTrialExpiration,
} from '../store/authSlice';

// ✅ NEW: Import streak check
import { checkAndMarkStreak } from '../store/streakSlice';

// Constants
import { COLORS, APP } from '../utils/constants';

// --------------------------------------------
// LOADING SCREEN
// --------------------------------------------

const LoadingScreen = () => (
  <View style={styles.loadingContainer}>
    <Text style={styles.loadingLogo}>🔍</Text>
    <Text style={styles.loadingAppName}>{APP.NAME}</Text>
    <ActivityIndicator size="large" color={COLORS.primary} style={styles.loadingSpinner} />
    <Text style={styles.loadingText}>Loading...</Text>
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
  
  // ✅ NEW: Track if we've already checked streak this session
  const hasCheckedStreakRef = useRef(false);
  
  // ✅ NEW: Track app state for foreground detection
  const appState = useRef(AppState.currentState);

  // Check auth status on mount
  useEffect(() => {
    dispatch(checkAuthStatus());

    // Failsafe: never keep splash/loading forever in case startup checks hang.
    const watchdog = setTimeout(() => {
      dispatch(forceFinishInitialization());
    }, 15000);

    return () => clearTimeout(watchdog);
  }, [dispatch]);

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
    }
  }, [isAuthenticated, isInitializing, dispatch]);

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
        
        // Optionally: Re-check streak if user has been away for a while
        // For now, we only check once per app session
      }
      
      appState.current = nextAppState;
    });

    return () => {
      subscription?.remove();
    };
  }, [dispatch]);

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

  return (
    <Stack.Navigator screenOptions={{ headerShown: false }}>
      {isAuthenticated ? (
        // Authenticated: Show main app with tabs
        <Stack.Screen
          name="Main"
          component={MainTabs}
          options={{
            animationTypeForReplace: 'push',
          }}
        />
      ) : (
        // Not authenticated: Show login
        <Stack.Screen
          name="Login"
          component={LoginScreen}
          options={{
            animationTypeForReplace: 'pop',
          }}
        />
      )}
    </Stack.Navigator>
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
    backgroundColor: COLORS.background,
  },
  
  loadingLogo: {
    fontSize: 80,
    marginBottom: 16,
  },
  
  loadingAppName: {
    fontSize: 32,
    fontWeight: 'bold',
    color: COLORS.primary,
    marginBottom: 24,
  },
  
  loadingSpinner: {
    marginBottom: 16,
  },
  
  loadingText: {
    fontSize: 16,
    color: COLORS.gray500,
  },
});

export default AppNavigator;