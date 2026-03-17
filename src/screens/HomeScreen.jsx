// ============================================
// DEALHUNT APP - HOME SCREEN (PLACEHOLDER)
// ============================================

import React from 'react';
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  Alert,
} from 'react-native';

import Button from '../components/common/Button';
import { useAuth } from '../hooks/useAuth';
import { COLORS, APP } from '../utils/constants';
import { SafeAreaView } from 'react-native-safe-area-context';
// --------------------------------------------
// HOME SCREEN COMPONENT
// --------------------------------------------

const HomeScreen = () => {
  const {
    user,
    userPlan,
    searchesRemaining,
    watchlistCount,
    currentStreak,
    referralCode,
    signOut,
    isLoading,
  } = useAuth();

  // --------------------------------------------
  // HANDLERS
  // --------------------------------------------

  const handleLogout = () => {
    Alert.alert(
      'Logout',
      'Are you sure you want to logout?',
      [
        { text: 'Cancel', style: 'cancel' },
        {
          text: 'Logout',
          style: 'destructive',
          onPress: async () => {
            await signOut();
          },
        },
      ]
    );
  };

  // --------------------------------------------
  // RENDER
  // --------------------------------------------

  return (
    <SafeAreaView style={styles.container}>
      <ScrollView
        contentContainerStyle={styles.scrollContent}
        showsVerticalScrollIndicator={false}
      >
        {/* Header */}
        <View style={styles.header}>
          <Text style={styles.welcomeText}>Welcome to</Text>
          <Text style={styles.appName}>{APP.NAME} 🔍</Text>
        </View>

        {/* Success Card */}
        <View style={styles.successCard}>
          <Text style={styles.successIcon}>✅</Text>
          <Text style={styles.successTitle}>Authentication Complete!</Text>
          <Text style={styles.successSubtitle}>
            Part 1 is working perfectly
          </Text>
        </View>

        {/* User Info Card */}
        <View style={styles.card}>
          <Text style={styles.cardTitle}>👤 Your Profile</Text>
          
          <View style={styles.infoRow}>
            <Text style={styles.infoLabel}>Email:</Text>
            <Text style={styles.infoValue}>{user?.email || 'N/A'}</Text>
          </View>
          
          <View style={styles.infoRow}>
            <Text style={styles.infoLabel}>Plan:</Text>
            <View style={[styles.badge, styles[`badge_${userPlan}`]]}>
              <Text style={styles.badgeText}>{userPlan?.toUpperCase()}</Text>
            </View>
          </View>
          
          <View style={styles.infoRow}>
            <Text style={styles.infoLabel}>User ID:</Text>
            <Text style={styles.infoValueSmall}>
              {user?.id?.slice(0, 8) || 'N/A'}...
            </Text>
          </View>
        </View>

        {/* Stats Card */}
        <View style={styles.card}>
          <Text style={styles.cardTitle}>📊 Your Stats</Text>
          
          <View style={styles.statsGrid}>
            <View style={styles.statItem}>
              <Text style={styles.statValue}>{searchesRemaining ?? '10'}</Text>
              <Text style={styles.statLabel}>Searches Left</Text>
            </View>
            
            <View style={styles.statItem}>
              <Text style={styles.statValue}>{watchlistCount}</Text>
              <Text style={styles.statLabel}>Watchlist</Text>
            </View>
            
            <View style={styles.statItem}>
              <Text style={styles.statValue}>{currentStreak}</Text>
              <Text style={styles.statLabel}>Day Streak 🔥</Text>
            </View>
          </View>
        </View>

        {/* Referral Card */}
        <View style={styles.card}>
          <Text style={styles.cardTitle}>🎁 Your Referral Code</Text>
          <View style={styles.referralContainer}>
            <Text style={styles.referralCode}>{referralCode || 'Loading...'}</Text>
          </View>
          <Text style={styles.referralHint}>
            Share this code with friends to earn rewards!
          </Text>
        </View>

        {/* Coming Soon Card */}
        <View style={styles.comingSoonCard}>
          <Text style={styles.comingSoonTitle}>🚀 Coming in Next Parts</Text>
          <Text style={styles.comingSoonItem}>• Part 2: Search & Price Comparison</Text>
          <Text style={styles.comingSoonItem}>• Part 3: Watchlist & Alerts</Text>
          <Text style={styles.comingSoonItem}>• Part 4: Streak System</Text>
          <Text style={styles.comingSoonItem}>• Part 5: Subscriptions</Text>
          <Text style={styles.comingSoonItem}>• Part 6: Ads & Polish</Text>
        </View>

        {/* Logout Button */}
        <View style={styles.logoutContainer}>
          <Button
            title="Logout"
            onPress={handleLogout}
            variant="outline"
            loading={isLoading}
          />
        </View>

        {/* Version */}
        <Text style={styles.version}>v{APP.VERSION} - Part 1 Complete</Text>
      </ScrollView>
    </SafeAreaView>
  );
};

// --------------------------------------------
// STYLES
// --------------------------------------------

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: COLORS.background,
  },
  
  scrollContent: {
    padding: 20,
    paddingBottom: 40,
  },
  
  header: {
    alignItems: 'center',
    marginBottom: 24,
    marginTop: 10,
  },
  
  welcomeText: {
    fontSize: 18,
    color: COLORS.gray600,
  },
  
  appName: {
    fontSize: 32,
    fontWeight: 'bold',
    color: COLORS.primary,
    marginTop: 4,
  },
  
  successCard: {
    backgroundColor: COLORS.successLight,
    borderRadius: 16,
    padding: 24,
    alignItems: 'center',
    marginBottom: 20,
    borderWidth: 1,
    borderColor: COLORS.success,
  },
  
  successIcon: {
    fontSize: 48,
    marginBottom: 12,
  },
  
  successTitle: {
    fontSize: 20,
    fontWeight: 'bold',
    color: COLORS.success,
    marginBottom: 4,
  },
  
  successSubtitle: {
    fontSize: 14,
    color: COLORS.gray600,
  },
  
  card: {
    backgroundColor: COLORS.white,
    borderRadius: 16,
    padding: 20,
    marginBottom: 16,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.1,
    shadowRadius: 8,
    elevation: 4,
  },
  
  cardTitle: {
    fontSize: 18,
    fontWeight: '600',
    color: COLORS.textPrimary,
    marginBottom: 16,
  },
  
  infoRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingVertical: 8,
    borderBottomWidth: 1,
    borderBottomColor: COLORS.gray100,
  },
  
  infoLabel: {
    fontSize: 14,
    color: COLORS.gray600,
  },
  
  infoValue: {
    fontSize: 14,
    fontWeight: '600',
    color: COLORS.textPrimary,
  },
  
  infoValueSmall: {
    fontSize: 12,
    fontWeight: '500',
    color: COLORS.gray500,
    fontFamily: 'monospace',
  },
  
  badge: {
    paddingHorizontal: 12,
    paddingVertical: 4,
    borderRadius: 12,
  },
  
  badge_free: {
    backgroundColor: COLORS.gray200,
  },
  
  badge_basic: {
    backgroundColor: COLORS.infoLight,
  },
  
  badge_premium: {
    backgroundColor: COLORS.warningLight,
  },
  
  badgeText: {
    fontSize: 12,
    fontWeight: '700',
    color: COLORS.gray700,
  },
  
  statsGrid: {
    flexDirection: 'row',
    justifyContent: 'space-around',
  },
  
  statItem: {
    alignItems: 'center',
  },
  
  statValue: {
    fontSize: 28,
    fontWeight: 'bold',
    color: COLORS.primary,
  },
  
  statLabel: {
    fontSize: 12,
    color: COLORS.gray500,
    marginTop: 4,
  },
  
  referralContainer: {
    backgroundColor: COLORS.gray50,
    borderRadius: 12,
    padding: 16,
    alignItems: 'center',
    borderWidth: 2,
    borderColor: COLORS.primary,
    borderStyle: 'dashed',
  },
  
  referralCode: {
    fontSize: 24,
    fontWeight: 'bold',
    color: COLORS.primary,
    letterSpacing: 3,
  },
  
  referralHint: {
    fontSize: 12,
    color: COLORS.gray500,
    textAlign: 'center',
    marginTop: 12,
  },
  
  comingSoonCard: {
    backgroundColor: COLORS.gray50,
    borderRadius: 16,
    padding: 20,
    marginBottom: 20,
  },
  
  comingSoonTitle: {
    fontSize: 16,
    fontWeight: '600',
    color: COLORS.textPrimary,
    marginBottom: 12,
  },
  
  comingSoonItem: {
    fontSize: 14,
    color: COLORS.gray600,
    marginBottom: 6,
  },
  
  logoutContainer: {
    marginTop: 10,
  },
  
  version: {
    fontSize: 12,
    color: COLORS.gray400,
    textAlign: 'center',
    marginTop: 20,
  },
});

export default HomeScreen;