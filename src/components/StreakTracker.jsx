// ============================================
// DEALHUNT APP - STREAK TRACKER COMPONENT
// Part 4: Gamification UI
// ============================================

import React, { useMemo } from 'react';
import { View, Text, StyleSheet } from 'react-native';
import { useSelector } from 'react-redux';
import { Ionicons } from '@expo/vector-icons';
import { LinearGradient } from 'expo-linear-gradient';

import {
  selectStreakData,
  selectNextMilestone,
} from '../store/streakSlice';
import { COLORS, STREAK_MILESTONES } from '../utils/constants';

// --------------------------------------------
// DAY INDICATOR COMPONENT
// --------------------------------------------

const DayIndicator = ({ label, status }) => {
  const getStyle = () => {
    switch (status) {
      case 'completed':
        return { bg: COLORS.success + '20', border: COLORS.success, icon: 'checkmark', iconColor: COLORS.success };
      case 'today':
        return { bg: COLORS.primary + '20', border: COLORS.primary, icon: 'flame', iconColor: COLORS.primary };
      case 'future':
        return { bg: COLORS.gray100, border: COLORS.gray300, icon: null, iconColor: COLORS.gray400 };
      case 'broken':
        return { bg: COLORS.error + '10', border: COLORS.error + '30', icon: 'close', iconColor: COLORS.error };
      default:
        return { bg: COLORS.gray100, border: COLORS.gray300, icon: null, iconColor: COLORS.gray400 };
    }
  };

  const style = getStyle();

  return (
    <View style={[styles.dayIndicator, { backgroundColor: style.bg, borderColor: style.border }]}>
      {style.icon ? (
        <Ionicons name={style.icon} size={14} color={style.iconColor} />
      ) : (
        <Text style={[styles.dayLabel, { color: style.iconColor }]}>{label}</Text>
      )}
    </View>
  );
};

// --------------------------------------------
// STREAK TRACKER COMPONENT
// --------------------------------------------

const StreakTracker = () => {
  const streakData = useSelector(selectStreakData);
  const nextMilestone = useSelector(selectNextMilestone);

  const {
    currentStreak = 0,
    longestStreak = 0,
    todayCompleted = false,
    isLoading = false,
  } = streakData || {};

  // Calculate week visualization
  const weekDays = useMemo(() => {
    const days = ['M', 'T', 'W', 'T', 'F', 'S', 'S'];
    const completedCount = Math.min(Math.max(currentStreak, 0), days.length);
    const todayIndex = todayCompleted
      ? Math.min(Math.max(currentStreak - 1, 0), days.length - 1)
      : -1;

    return days.map((label, index) => {
      if (index < completedCount) {
        if (index === todayIndex) {
          return { label, status: 'today' };
        }
        return { label, status: 'completed' };
      }

      if (!todayCompleted && index === completedCount && index < days.length) {
        return { label, status: 'broken' };
      }

      return { label, status: 'future' };
    });
  }, [currentStreak, todayCompleted]);

  // Get next milestone info
  const milestoneInfo = useMemo(() => {
    if (nextMilestone) {
      return {
        days: nextMilestone,
        reward: STREAK_MILESTONES[nextMilestone],
      };
    }

    // Calculate from constants if backend doesn't provide
    const milestones = Object.keys(STREAK_MILESTONES).map(Number).sort((a, b) => a - b);
    const next = milestones.find(m => m > currentStreak);
    
    if (next) {
      return {
        days: next,
        reward: STREAK_MILESTONES[next],
      };
    }

    return null;
  }, [currentStreak, nextMilestone]);

  const daysUntilReward = milestoneInfo ? milestoneInfo.days - currentStreak : null;

  // Messages
  const getMessage = () => {
    if (isLoading) return 'Loading your streak...';
    if (currentStreak === 0) return 'Start your streak today! 🚀';
    if (currentStreak === 1) return 'Great start! Keep it going tomorrow 💪';
    if (currentStreak >= 30) return `Amazing ${currentStreak}-day streak! 🔥`;
    if (todayCompleted) return `${currentStreak} days strong! Come back tomorrow 🎯`;
    return `${currentStreak} day streak! Check in to continue 🔥`;
  };

  return (
    <View style={styles.container}>
      <LinearGradient
        colors={['#FF6B35', '#F97316']}
        start={{ x: 0, y: 0 }}
        end={{ x: 1, y: 1 }}
        style={styles.gradient}
      >
        <View style={styles.content}>
          {/* Header */}
          <View style={styles.header}>
            <View style={styles.headerLeft}>
              <Text style={styles.fireEmoji}>🔥</Text>
              <View>
                <Text style={styles.streakCount}>{currentStreak} Day Streak</Text>
                <Text style={styles.subtitle}>{getMessage()}</Text>
              </View>
            </View>
            {longestStreak > currentStreak && (
              <View style={styles.badge}>
                <Ionicons name="trophy" size={12} color="#FFA500" />
                <Text style={styles.badgeText}>Best: {longestStreak}</Text>
              </View>
            )}
          </View>

          {/* Week Visualization */}
          <View style={styles.weekContainer}>
            {weekDays.map((day, index) => (
              <DayIndicator key={index} label={day.label} status={day.status} />
            ))}
          </View>

          {/* Next Milestone */}
          {milestoneInfo && daysUntilReward > 0 && (
            <View style={styles.milestoneContainer}>
              <Ionicons name="gift" size={16} color="rgba(255,255,255,0.9)" />
              <Text style={styles.milestoneText}>
                {daysUntilReward} more {daysUntilReward === 1 ? 'day' : 'days'} until{' '}
                <Text style={styles.milestoneBold}>{milestoneInfo.reward?.label}</Text>
              </Text>
            </View>
          )}

          {/* Max milestone reached */}
          {currentStreak >= 30 && !milestoneInfo && (
            <View style={styles.milestoneContainer}>
              <Ionicons name="star" size={16} color="#FFD700" />
              <Text style={styles.milestoneText}>
                You've reached the max streak! 🏆
              </Text>
            </View>
          )}
        </View>
      </LinearGradient>
    </View>
  );
};

// --------------------------------------------
// STYLES
// --------------------------------------------

const styles = StyleSheet.create({
  container: {
    marginHorizontal: 16,
    marginTop: 12,
    marginBottom: 8,
    borderRadius: 16,
    overflow: 'hidden',
    shadowColor: '#FF6B35',
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.2,
    shadowRadius: 8,
    elevation: 6,
  },
  gradient: {
    padding: 16,
  },
  content: {
    gap: 12,
  },
  header: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'flex-start',
  },
  headerLeft: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
    flex: 1,
  },
  fireEmoji: {
    fontSize: 36,
  },
  streakCount: {
    fontSize: 20,
    fontWeight: '800',
    color: COLORS.white,
    letterSpacing: 0.5,
  },
  subtitle: {
    fontSize: 13,
    color: 'rgba(255,255,255,0.9)',
    marginTop: 2,
    fontWeight: '500',
  },
  badge: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: 'rgba(255,255,255,0.25)',
    paddingHorizontal: 10,
    paddingVertical: 6,
    borderRadius: 12,
    gap: 4,
  },
  badgeText: {
    fontSize: 12,
    fontWeight: '700',
    color: COLORS.white,
  },
  weekContainer: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    gap: 6,
    marginTop: 4,
  },
  dayIndicator: {
    flex: 1,
    aspectRatio: 1,
    borderRadius: 8,
    borderWidth: 2,
    alignItems: 'center',
    justifyContent: 'center',
  },
  dayLabel: {
    fontSize: 12,
    fontWeight: '700',
  },
  milestoneContainer: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: 'rgba(255,255,255,0.2)',
    paddingHorizontal: 12,
    paddingVertical: 8,
    borderRadius: 10,
    gap: 8,
    marginTop: 4,
  },
  milestoneText: {
    fontSize: 13,
    color: 'rgba(255,255,255,0.95)',
    fontWeight: '500',
    flex: 1,
  },
  milestoneBold: {
    fontWeight: '700',
    color: COLORS.white,
  },
});

export default StreakTracker;