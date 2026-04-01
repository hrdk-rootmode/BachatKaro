// ============================================
// DEALHUNT APP - STREAK SCREEN
// Part 4: Streak Hub + Dev Testing Controls
// ============================================

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

import StreakTracker from '../components/StreakTracker';
import RewardModal from '../components/RewardModal';
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

// --------------------------------------------
// STREAK SCREEN COMPONENT
// --------------------------------------------

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
          <Text style={styles.title}>Streak</Text>
          <Text style={styles.subtitle}>Daily check-ins and milestone rewards</Text>
        </View>

        <StreakTracker />

        <View style={styles.summaryCard}>
          <View style={styles.summaryItem}>
            <Text style={styles.summaryValue}>{currentStreak}</Text>
            <Text style={styles.summaryLabel}>Current</Text>
          </View>
          <View style={styles.summaryDivider} />
          <View style={styles.summaryItem}>
            <Text style={styles.summaryValue}>{longestStreak}</Text>
            <Text style={styles.summaryLabel}>Best</Text>
          </View>
          <View style={styles.summaryDivider} />
          <View style={styles.summaryItem}>
            <Text style={styles.summaryValue}>{todayCompleted ? 'YES' : 'NO'}</Text>
            <Text style={styles.summaryLabel}>Today</Text>
          </View>
        </View>

        {/* Info Cards */}
        <View style={styles.infoCard}>
          <Text style={styles.infoTitle}>🎯 How it works</Text>
          <Text style={styles.infoText}>
            Open the app daily to keep your streak alive and unlock milestone rewards.
          </Text>
        </View>

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

      <RewardModal />
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
  
  content: {
    paddingBottom: 28,
    padding: 20,
  },
  
  header: {
    marginBottom: 30,
  },
  
  title: {
    fontSize: 28,
    fontWeight: 'bold',
    color: COLORS.textPrimary,
  },
  
  subtitle: {
    fontSize: 14,
    color: COLORS.textSecondary,
    marginTop: 4,
  },

  summaryCard: {
    backgroundColor: COLORS.white,
    borderRadius: 14,
    paddingVertical: 14,
    paddingHorizontal: 12,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.1,
    shadowRadius: 6,
    elevation: 4,
    marginBottom: 24,
  },

  summaryItem: {
    flex: 1,
    alignItems: 'center',
  },

  summaryDivider: {
    width: 1,
    height: 36,
    backgroundColor: COLORS.gray200,
  },

  summaryValue: {
    fontSize: 22,
    fontWeight: '800',
    color: COLORS.primary,
  },

  summaryLabel: {
    fontSize: 12,
    color: COLORS.textSecondary,
    marginTop: 3,
    fontWeight: '600',
  },

  infoCard: {
    backgroundColor: COLORS.infoLight,
    borderRadius: 12,
    padding: 16,
    marginBottom: 16,
  },

  infoTitle: {
    fontSize: 16,
    fontWeight: '600',
    color: COLORS.textPrimary,
    marginBottom: 8,
  },

  infoText: {
    fontSize: 14,
    color: COLORS.textSecondary,
    lineHeight: 20,
  },

  devCard: {
    backgroundColor: '#FFF4E9',
    borderRadius: 12,
    padding: 14,
    marginTop: 20,
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