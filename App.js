// ============================================
// DEALHUNT APP - ROOT COMPONENT (UPDATED)
// ============================================

import React from 'react';
import { StatusBar, View, Text, ScrollView } from 'react-native';
import { NavigationContainer } from '@react-navigation/native';
import { Provider } from 'react-redux';
import { PersistGate } from 'redux-persist/integration/react';

// Store
import { store, persistor } from './src/store/store';

// Navigation
import AppNavigator from './src/navigation/AppNavigator';
import TopToastProvider from './src/components/common/TopToastProvider';

// Global Modals
import RewardModal from './src/components/RewardModal';
import SubscriptionSuccessModal from './src/components/SubscriptionSuccessModal';

// Constants
import { COLORS } from './src/utils/constants';

// ============================================
// ERROR BOUNDARY COMPONENT
// ============================================

class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error) {
    return { hasError: true, error };
  }

  componentDidCatch(error, errorInfo) {
    console.error('[ErrorBoundary] Caught error:', error);
    console.error('[ErrorBoundary] Error info:', errorInfo);
  }

  render() {
    if (this.state.hasError) {
      return (
        <View style={{ flex: 1, backgroundColor: COLORS.background, justifyContent: 'center', padding: 20 }}>
          <StatusBar barStyle="dark-content" backgroundColor={COLORS.background} />
          <Text style={{ fontSize: 24, fontWeight: 'bold', marginBottom: 16, color: COLORS.text }}>
            ⚠️ App Error
          </Text>
          <ScrollView style={{ marginBottom: 16 }}>
            <Text style={{ fontSize: 14, color: COLORS.textSecondary, marginBottom: 8 }}>
              {this.state.error?.message || 'An unexpected error occurred'}
            </Text>
            <Text style={{ fontSize: 12, color: COLORS.textTertiary }}>
              {this.state.error?.stack}
            </Text>
          </ScrollView>
          <Text
            style={{
              padding: 12,
              backgroundColor: COLORS.primary,
              color: 'white',
              textAlign: 'center',
              borderRadius: 8,
            }}
            onPress={() => this.setState({ hasError: false, error: null })}
          >
            Retry
          </Text>
        </View>
      );
    }

    return this.props.children;
  }
}

// ============================================
// ROOT APP COMPONENT
// ============================================

const App = () => {
  return (
    <ErrorBoundary>
      <Provider store={store}>
        <PersistGate loading={null} persistor={persistor}>
          <NavigationContainer>
            <TopToastProvider>
              <StatusBar
                barStyle="dark-content"
                backgroundColor={COLORS.background}
              />
              <AppNavigator />
              
              {/* Global Modals */}
              <RewardModal />
              <SubscriptionSuccessModal />
            </TopToastProvider>
          </NavigationContainer>
        </PersistGate>
      </Provider>
    </ErrorBoundary>
  );
};

export default App;