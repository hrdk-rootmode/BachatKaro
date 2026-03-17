// ============================================
// DEALHUNT APP - ROOT COMPONENT
// ============================================

import React, { useEffect } from 'react';
import { StatusBar, View, Text, StyleSheet, ActivityIndicator } from 'react-native';
import { NavigationContainer } from '@react-navigation/native';
import { createStackNavigator } from '@react-navigation/stack';
import { Provider, useSelector, useDispatch } from 'react-redux';
import { PersistGate } from 'redux-persist/integration/react';

// Store
import { store, persistor } from './src/store/store';
import { checkAuthStatus, selectIsAuthenticated, selectIsInitializing } from './src/store/authSlice';

// Screens
import LoginScreen from './src/screens/auth/LoginScreen';
import HomeScreen from './src/screens/HomeScreen';

// Constants
import { COLORS, APP } from './src/utils/constants';

// --------------------------------------------
// NAVIGATION STACK
// --------------------------------------------

const Stack = createStackNavigator();

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
// APP NAVIGATOR
// --------------------------------------------

const AppNavigator = () => {
  const dispatch = useDispatch();
  const isAuthenticated = useSelector(selectIsAuthenticated);
  const isInitializing = useSelector(selectIsInitializing);

  // Check auth status on app start
  useEffect(() => {
    dispatch(checkAuthStatus());
  }, [dispatch]);

  // Show loading screen while checking auth
  if (isInitializing) {
    return <LoadingScreen />;
  }

  return (
    <Stack.Navigator screenOptions={{ headerShown: false }}>
      {isAuthenticated ? (
        // User is logged in - show main app
        <Stack.Screen
          name="Home"
          component={HomeScreen}
          options={{
            animationTypeForReplace: 'push',
          }}
        />
      ) : (
        // User is NOT logged in - show auth screens
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
// PERSIST LOADING COMPONENT
// --------------------------------------------

const PersistLoading = () => (
  <View style={styles.loadingContainer}>
    <ActivityIndicator size="large" color={COLORS.primary} />
  </View>
);

// --------------------------------------------
// ROOT APP COMPONENT
// --------------------------------------------

const App = () => {
  return (
    <Provider store={store}>
      <PersistGate loading={<PersistLoading />} persistor={persistor}>
        <NavigationContainer>
          <StatusBar
            barStyle="dark-content"
            backgroundColor={COLORS.background}
          />
          <AppNavigator />
        </NavigationContainer>
      </PersistGate>
    </Provider>
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

export default App;