// ============================================
// DEALHUNT APP - SEARCH STACK NAVIGATOR (UPDATED)
// ============================================

import React from 'react';
import { createStackNavigator } from '@react-navigation/stack';

// Real screens
import SearchScreenPremium from '../screens/search/SearchScreenPremium';
import ProductDetailScreen from '../screens/product/ProductDetailScreen';
import CrossPlatformComparisonScreen from '../screens/product/CrossPlatformComparisonScreen';

// Constants
import { COLORS } from '../utils/constants';

// --------------------------------------------
// SEARCH STACK NAVIGATOR
// --------------------------------------------

const Stack = createStackNavigator();

const SearchStack = () => {
  return (
    <Stack.Navigator
      screenOptions={{
        headerShown: false,
        cardStyle: { backgroundColor: COLORS.background },
        // Smooth transitions
        cardStyleInterpolator: ({ current, layouts }) => {
          return {
            cardStyle: {
              transform: [
                {
                  translateX: current.progress.interpolate({
                    inputRange: [0, 1],
                    outputRange: [layouts.screen.width, 0],
                  }),
                },
              ],
            },
          };
        },
      }}
    >
      <Stack.Screen 
        name="SearchMain" 
        component={SearchScreenPremium}
      />
      <Stack.Screen 
        name="ProductDetail" 
        component={ProductDetailScreen}
      />
      <Stack.Screen 
        name="CrossPlatformComparison" 
        component={CrossPlatformComparisonScreen}
      />
    </Stack.Navigator>
  );
};

export default SearchStack;