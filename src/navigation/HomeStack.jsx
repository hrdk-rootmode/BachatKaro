import React from 'react';
import { createStackNavigator } from '@react-navigation/stack';
import HomeScreenV2 from '../screens/HomeScreenV2';
import NotificationsScreen from '../screens/NotificationsScreen';
import ProductDetailScreen from '../screens/product/ProductDetailScreen';
import CrossPlatformComparisonScreen from '../screens/product/CrossPlatformComparisonScreen';
import CategoryProductsScreen from '../screens/CategoryProductsScreen';

const Stack = createStackNavigator();

const HomeStack = () => (
  <Stack.Navigator screenOptions={{ headerShown: false }}>
    <Stack.Screen name="Home" component={HomeScreenV2} />
    <Stack.Screen name="Notifications" component={NotificationsScreen} />
    <Stack.Screen name="ProductDetail" component={ProductDetailScreen} />
    <Stack.Screen name="CrossPlatformComparison" component={CrossPlatformComparisonScreen} />
    <Stack.Screen name="CategoryProducts" component={CategoryProductsScreen} />
  </Stack.Navigator>
);

export default HomeStack;