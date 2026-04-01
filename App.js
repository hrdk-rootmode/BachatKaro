// ============================================
// DEALHUNT APP - ROOT COMPONENT (UPDATED)
// ============================================

import React from 'react';
import { StatusBar } from 'react-native';
import { NavigationContainer } from '@react-navigation/native';
import { Provider } from 'react-redux';
import { PersistGate } from 'redux-persist/integration/react';

// Store
import { store, persistor } from './src/store/store';

// Navigation
import AppNavigator from './src/navigation/AppNavigator';
import TopToastProvider from './src/components/common/TopToastProvider';

// Constants
import { COLORS } from './src/utils/constants';

// --------------------------------------------
// ROOT APP COMPONENT
// --------------------------------------------

const App = () => {
  return (
    <Provider store={store}>
      <PersistGate loading={null} persistor={persistor}>
        <NavigationContainer>
          <TopToastProvider>
            <StatusBar
              barStyle="dark-content"
              backgroundColor={COLORS.background}
            />
            <AppNavigator />
          </TopToastProvider>
        </NavigationContainer>
      </PersistGate>
    </Provider>
  );
};

export default App;