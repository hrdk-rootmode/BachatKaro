// ============================================
// DEALHUNT APP - BOTTOM TAB NAVIGATOR
// Part 3: Added Watchlist Badge
// ============================================

import React from 'react';
import { View, Text, StyleSheet } from 'react-native';
import { createBottomTabNavigator } from '@react-navigation/bottom-tabs';
import { Ionicons } from '@expo/vector-icons';
import { useSelector } from 'react-redux';

// Stacks
import HomeStack from './HomeStack';
import SearchStack from './SearchStack';
import WatchlistStack from './WatchlistStack';

// Screens
import StreakScreen from '../screens/StreakScreen';
import ProfileScreen from '../screens/ProfileScreen';

// Redux - Watchlist count
import { selectWatchlistCount } from '../store/watchlistSlice';
import { selectCurrentStreak } from '../store/streakSlice';

// Constants
import { COLORS } from '../utils/constants';

const Tab = createBottomTabNavigator();

// --------------------------------------------
// BADGE COMPONENT
// --------------------------------------------

const TabBadge = ({ count }) => {
  if (!count || count <= 0) return null;
  
  const displayCount = count > 99 ? '99+' : count;
  
  return (
    <View style={styles.badge}>
      <Text style={styles.badgeText}>{displayCount}</Text>
    </View>
  );
};

// --------------------------------------------
// TAB ICON WITH BADGE
// --------------------------------------------

const TabIconWithBadge = ({ iconName, color, size, badgeCount }) => {
  return (
    <View style={styles.iconContainer}>
      <Ionicons name={iconName} size={size} color={color} />
      <TabBadge count={badgeCount} />
    </View>
  );
};

// --------------------------------------------
// MAIN TABS NAVIGATOR
// --------------------------------------------

const MainTabs = () => {
  // Get watchlist count from Redux
  const watchlistCount = useSelector(selectWatchlistCount);
  const currentStreak = useSelector(selectCurrentStreak);
  const shouldShowStreakTab = currentStreak >= 5;
  
  return (
    <Tab.Navigator
      screenOptions={({ route }) => ({
        headerShown: false,
        tabBarIcon: ({ focused, color, size }) => {
          let iconName;

          switch (route.name) {
            case 'HomeTab':
              iconName = focused ? 'home' : 'home-outline';
              break;
            case 'SearchTab':
              iconName = focused ? 'search' : 'search-outline';
              break;
            case 'WatchlistTab':
              iconName = focused ? 'heart' : 'heart-outline';
              // ✅ Return icon with badge for watchlist
              return (
                <TabIconWithBadge
                  iconName={iconName}
                  color={color}
                  size={size}
                  badgeCount={watchlistCount}
                />
              );
            case 'StreakTab':
              iconName = focused ? 'flame' : 'flame-outline';
              break;
            case 'ProfileTab':
              iconName = focused ? 'person' : 'person-outline';
              break;
            default:
              iconName = 'ellipse-outline';
          }

          return <Ionicons name={iconName} size={size} color={color} />;
        },
        tabBarActiveTintColor: COLORS.primary,
        tabBarInactiveTintColor: COLORS.gray500,
        tabBarLabelStyle: {
          fontSize: 12,
          marginBottom: 4,
        },
        tabBarStyle: {
          height: 75,
          paddingTop: 8,
          paddingBottom: 8,
          borderTopWidth: 1,
          borderTopColor: COLORS.gray200,
          backgroundColor: COLORS.white,
        },
      })}
    >
      <Tab.Screen 
        name="HomeTab" 
        component={HomeStack}
        options={{ tabBarLabel: 'Home' }}
      />
      <Tab.Screen 
        name="SearchTab" 
        component={SearchStack}
        options={{ tabBarLabel: 'Search' }}
      />
      <Tab.Screen 
        name="WatchlistTab" 
        component={WatchlistStack}
        options={{ tabBarLabel: 'Watchlist' }}
      />
      {shouldShowStreakTab && (
        <Tab.Screen
          name="StreakTab"
          component={StreakScreen}
          options={{ tabBarLabel: 'Streak' }}
        />
      )}
      <Tab.Screen 
        name="ProfileTab" 
        component={ProfileScreen}
        options={{ tabBarLabel: 'Profile' }}
      />
    </Tab.Navigator>
  );
};

// --------------------------------------------
// STYLES
// --------------------------------------------

const styles = StyleSheet.create({
  iconContainer: {
    position: 'relative',
    width: 28,
    height: 28,
    justifyContent: 'center',
    alignItems: 'center',
  },
  
  badge: {
    position: 'absolute',
    top: -4,
    right: -8,
    minWidth: 18,
    height: 18,
    borderRadius: 9,
    backgroundColor: COLORS.error,
    justifyContent: 'center',
    alignItems: 'center',
    paddingHorizontal: 4,
    borderWidth: 2,
    borderColor: COLORS.white,
  },
  
  badgeText: {
    color: COLORS.white,
    fontSize: 10,
    fontWeight: '700',
    textAlign: 'center',
  },
});

export default MainTabs;