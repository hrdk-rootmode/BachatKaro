import React from 'react';
import { createStackNavigator } from '@react-navigation/stack';
import HomeScreenV2 from '../screens/HomeScreenV2';
import ProductDetailScreen from '../screens/product/ProductDetailScreen';
import CrossPlatformComparisonScreen from '../screens/product/CrossPlatformComparisonScreen';

const Stack = createStackNavigator();

const HomeStack = () => (
  <Stack.Navigator screenOptions={{ headerShown: false }}>
    <Stack.Screen name="Home" component={HomeScreenV2} />
    <Stack.Screen name="ProductDetail" component={ProductDetailScreen} />
    <Stack.Screen name="CrossPlatformComparison" component={CrossPlatformComparisonScreen} />
  </Stack.Navigator>
);

export default HomeStack;