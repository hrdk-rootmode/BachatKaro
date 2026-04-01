import React from 'react';
import { createStackNavigator } from '@react-navigation/stack';

import WatchlistScreen from '../screens/WatchlistScreen';
import ProductDetailScreen from '../screens/product/ProductDetailScreen';
import CrossPlatformComparisonScreen from '../screens/product/CrossPlatformComparisonScreen';

const Stack = createStackNavigator();

const WatchlistStack = () => (
  <Stack.Navigator screenOptions={{ headerShown: false }}>
    <Stack.Screen name="WatchlistMain" component={WatchlistScreen} />
    <Stack.Screen name="ProductDetail" component={ProductDetailScreen} />
    <Stack.Screen
      name="CrossPlatformComparison"
      component={CrossPlatformComparisonScreen}
    />
  </Stack.Navigator>
);

export default WatchlistStack;