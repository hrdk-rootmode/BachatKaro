import React from 'react';
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  TouchableOpacity,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useDispatch, useSelector } from 'react-redux';
import { Ionicons } from '@expo/vector-icons';

import StreakTracker from '../components/StreakTracker';
import {
  selectStreakData,
} from '../store/streakSlice';
import {
  activateProTrial,
  selectProTrialInfo,
  debugAdjustProTrialMinutesForDev,
} from '../store/authSlice';

import { COLORS } from '../utils/constants';

const formatTrialTimeRemaining = (expiresAt) => {
  if (!expiresAt) return null;

  const remainingMs = new Date(expiresAt).getTime() - Date.now();
  if (remainingMs <= 0) return null;

  const hours = Math.floor(remainingMs / (1000 * 60 * 60));
  const minutes = Math.floor((remainingMs % (1000 * 60 * 60)) / (1000 * 60));
  const seconds = Math.floor((remainingMs % (1000 * 60)) / 1000);
  return `${hours}:${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`;
};

const StreakScreen = () => {
  const dispatch = useDispatch();
  const streakData = useSelector(selectStreakData);
  const proTrialInfo = useSelector(selectProTrialInfo);
  const [trialTimeRemaining, setTrialTimeRemaining] = React.useState(null);

  const currentStreak = streakData?.currentStreak || 0;
  const longestStreak = streakData?.longestStreak || 0;
  const todayCompleted = Boolean(streakData?.todayCompleted);

  const handleActivateTrialForDev = () => {
    dispatch(activateProTrial({ durationHours: 1 }));
  };

  const handleAdjustTrialMinutes = (minutesDelta) => {
    dispatch(debugAdjustProTrialMinutesForDev({ minutesDelta }));
  };

  React.useEffect(() => {
    if (!proTrialInfo?.isActive || !proTrialInfo?.expiresAt) {
      setTrialTimeRemaining(null);
      return;
    }

    const updateTimer = () => {
      setTrialTimeRemaining(formatTrialTimeRemaining(proTrialInfo.expiresAt));
    };

    updateTimer();
    const interval = setInterval(updateTimer, 1000);
    return () => clearInterval(interval);
  }, [proTrialInfo?.expiresAt, proTrialInfo?.isActive]);

  return (
    <SafeAreaView style={styles.container}>
      <ScrollView contentContainerStyle={styles.content} showsVerticalScrollIndicator={false}>
        {/* Header */}
        <View style={styles.header}>
          <Text style={styles.title}>Daily Streak</Text>
          <Text style={styles.subtitle}>Keep your streak alive and earn rewards</Text>
        </View>

        {/* Main Streak Tracker */}
        <StreakTracker />

        {/* Quick Stats */}
        <View style={styles.statsCard}>
          <View style={styles.statItem}>
            <View style={styles.statIcon}>
              <Ionicons name="flame" size={20} color="#FF6B35" />
            </View>
            <Text style={styles.statValue}>{currentStreak}</Text>
            <Text style={styles.statLabel}>Current</Text>
          </View>
          <View style={styles.statDivider} />
          <View style={styles.statItem}>
            <View style={styles.statIcon}>
              <Ionicons name="trophy" size={20} color="#FFB800" />
            </View>
            <Text style={styles.statValue}>{longestStreak}</Text>
            <Text style={styles.statLabel}>Best</Text>
          </View>
          <View style={styles.statDivider} />
          <View style={styles.statItem}>
            <View style={styles.statIcon}>
              <Ionicons 
                name={todayCompleted ? "checkmark-circle" : "radio-button-off"} 
                size={20} 
                color={todayCompleted ? "#10B981" : "#A3A3A3"}
              />
            </View>
            <Text style={styles.statValue}>{todayCompleted ? 'Done' : 'Pending'}</Text>
            <Text style={styles.statLabel}>Today</Text>
          </View>
        </View>

        {/* Tips Section */}
        <View style={styles.tipsSection}>
          <View style={styles.tipsHeader}>
            <Ionicons name="bulb-outline" size={18} color={COLORS.primary} />
            <Text style={styles.tipsTitle}>Quick Tips</Text>
          </View>
          <Text style={styles.tipItem}>💡 Open the app daily to maintain your streak</Text>
          <Text style={styles.tipItem}>🎁 Reach milestones to unlock exclusive rewards</Text>
          <Text style={styles.tipItem}>⏰ Check in anytime to keep your streak alive</Text>
        </View>

        {/* Rewards Guide */}
        <View style={styles.guideSection}>
          <View style={styles.guideHeader}>
            <Ionicons name="gift" size={18} color="#8B5CF6" />
            <Text style={styles.guideTitle}>What You Get</Text>
          </View>
          <View style={styles.guideItem}>
            <Text style={styles.guideDay}>5 Days</Text>
            <Text style={styles.guideReward}>+5 Extra Searches</Text>
          </View>
          <View style={styles.guideItem}>
            <Text style={styles.guideDay}>7 Days</Text>
            <Text style={styles.guideReward}>+1 Watchlist Slot</Text>
          </View>
          <View style={styles.guideItem}>
            <Text style={styles.guideDay}>10 Days</Text>
            <Text style={styles.guideReward}>+3 Watchlist Slots</Text>
          </View>
          <View style={styles.guideItem}>
            <Text style={styles.guideDay}>15 Days</Text>
            <Text style={styles.guideReward}>+6 Hours Unlimited Search</Text>
          </View>
        </View>

        {/* Dev Controls */}
        {__DEV__ && (
          <View style={styles.devCard}>
            <Text style={styles.devTitle}>Developer Trial Debug</Text>
            <Text style={styles.devSubtitle}>
              Temporary test control moved here from Home screen.
            </Text>

            <TouchableOpacity
              style={[styles.devButton, styles.devButtonTrial]}
              onPress={handleActivateTrialForDev}
              activeOpacity={0.85}
            >
              <Text style={styles.devButtonText}>Activate 1hr Pro Trial</Text>
            </TouchableOpacity>

            <View style={styles.devActionRow}>
              <TouchableOpacity
                style={[styles.devButton, styles.devButtonNudge]}
                onPress={() => handleAdjustTrialMinutes(15)}
                activeOpacity={0.85}
              >
                <Text style={styles.devButtonText}>+15m</Text>
              </TouchableOpacity>

              <TouchableOpacity
                style={[styles.devButton, styles.devButtonNudge]}
                onPress={() => handleAdjustTrialMinutes(-15)}
                activeOpacity={0.85}
              >
                <Text style={styles.devButtonText}>-15m</Text>
              </TouchableOpacity>
            </View>

            {proTrialInfo?.isActive && (
              <Text style={styles.devTrialMeta}>
                Trial remaining: {trialTimeRemaining || formatTrialTimeRemaining(proTrialInfo?.expiresAt) || 'expired'}
              </Text>
            )}
          </View>
        )}
      </ScrollView>
    </SafeAreaView>
  );
};

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: COLORS.background,
  },
  
  content: {
    paddingBottom: 28,
    paddingHorizontal: 16,
    paddingTop: 12,
  },
  
  header: {
    marginBottom: 20,
  },
  
  title: {
    fontSize: 32,
    fontWeight: 'bold',
    color: COLORS.textPrimary,
  },
  
  subtitle: {
    fontSize: 14,
    color: COLORS.textSecondary,
    marginTop: 6,
    fontWeight: '500',
  },

  // Stats Card Styles
  statsCard: {
    backgroundColor: COLORS.white,
    borderRadius: 14,
    paddingVertical: 16,
    paddingHorizontal: 12,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.08,
    shadowRadius: 4,
    elevation: 3,
    marginBottom: 20,
  },

  statItem: {
    flex: 1,
    alignItems: 'center',
  },

  statIcon: {
    marginBottom: 6,
  },

  statValue: {
    fontSize: 20,
    fontWeight: '800',
    color: COLORS.primary,
  },

  statLabel: {
    fontSize: 12,
    color: COLORS.textSecondary,
    marginTop: 4,
    fontWeight: '600',
  },

  statDivider: {
    width: 1,
    height: 40,
    backgroundColor: COLORS.gray200,
  },

  // Tips Section
  tipsSection: {
    backgroundColor: COLORS.white,
    borderRadius: 12,
    padding: 16,
    marginBottom: 16,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.05,
    shadowRadius: 3,
    elevation: 2,
  },

  tipsHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    marginBottom: 12,
  },

  tipsTitle: {
    fontSize: 15,
    fontWeight: '700',
    color: COLORS.textPrimary,
  },

  tipItem: {
    fontSize: 13,
    color: COLORS.textSecondary,
    marginBottom: 10,
    fontWeight: '500',
    lineHeight: 18,
  },

  // Guide Section
  guideSection: {
    backgroundColor: '#F3E8FF',
    borderRadius: 12,
    padding: 16,
    marginBottom: 16,
    borderLeftWidth: 4,
    borderLeftColor: '#8B5CF6',
  },

  guideHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    marginBottom: 14,
  },

  guideTitle: {
    fontSize: 15,
    fontWeight: '700',
    color: '#6D28D9',
  },

  guideItem: {
    flexDirection: 'row',
    alignItems: 'center',
    marginBottom: 10,
    paddingVertical: 8,
    paddingHorizontal: 12,
    backgroundColor: 'rgba(255,255,255,0.6)',
    borderRadius: 8,
  },

  guideDay: {
    fontSize: 13,
    fontWeight: '700',
    color: '#7C3AED',
    minWidth: 70,
  },

  guideReward: {
    fontSize: 13,
    color: '#6D28D9',
    fontWeight: '600',
    flex: 1,
  },

  // Dev Card Styles
  devCard: {
    backgroundColor: '#FFF4E9',
    borderRadius: 12,
    padding: 14,
    marginTop: 20,
    borderWidth: 1,
    borderColor: '#FCDAB7',
  },

  devTitle: {
    fontSize: 15,
    fontWeight: '700',
    color: '#9A3412',
  },

  devSubtitle: {
    fontSize: 12,
    color: '#B45309',
    marginTop: 4,
    marginBottom: 12,
  },

  devButton: {
    borderRadius: 10,
    paddingVertical: 11,
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: 14,
  },

  devButtonTrial: {
    backgroundColor: '#1D4ED8',
  },

  devActionRow: {
    flexDirection: 'row',
    marginTop: 10,
  },

  devButtonNudge: {
    flex: 1,
    backgroundColor: '#2563EB',
    marginHorizontal: 4,
  },

  devButtonText: {
    fontWeight: '600',
    fontSize: 14,
    color: COLORS.white,
  },

  devTrialMeta: {
    marginTop: 10,
    fontSize: 12,
    fontWeight: '600',
    color: '#1E3A8A',
    textAlign: 'center',
  },
});

export default StreakScreen;