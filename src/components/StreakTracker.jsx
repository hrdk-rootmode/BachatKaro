import React, { useMemo } from 'react';
import { View, Text, StyleSheet, ScrollView } from 'react-native';
import { useSelector } from 'react-redux';
import { Ionicons } from '@expo/vector-icons';
import { LinearGradient } from 'expo-linear-gradient';

import {
  selectStreakData,
  selectStreakMilestones,
} from '../store/streakSlice';
import { COLORS } from '../utils/constants';

const rewardTypeColor = {
  search_bonus: '#F59E0B',
  daily_search_bonus: '#FB923C',
  watchlist_slots: '#10B981',
  premium_days: '#3B82F6',
  unlimited_hours: '#2563EB',
  free_month: '#8B5CF6',
};

const formatRewardText = (rewardType, rewardValue, announcementText) => {
  if (announcementText) {
    return announcementText;
  }
  const amount = Number(rewardValue || 0);
  switch (rewardType) {
    case 'search_bonus':
      return `+${amount} Extra Searches`;
    case 'daily_search_bonus':
      return `+${amount} Daily Searches`;
    case 'watchlist_slots':
      return `+${amount} Watchlist Slots`;
    case 'premium_days':
      return `${amount} Day Pro Access`;
    case 'unlimited_hours':
      return `${amount} Hours Unlimited Search`;
    case 'free_month':
      return '1 Free Month';
    default:
      return announcementText || 'Special Reward';
  }
};

const normalizeMilestone = (milestone) => {
  const days = Number(milestone?.days ?? milestone?.streak_days ?? 0);
  const rewardType = String(milestone?.reward_type || '').toLowerCase();
  return {
    days,
    emoji: milestone?.badge_emoji || '🎯',
    title: milestone?.badge_name || `${days}-Day Milestone`,
    reward: formatRewardText(rewardType, milestone?.reward_value, milestone?.announcement_text),
    color: rewardTypeColor[rewardType] || '#6366F1',
  };
};

// Day indicator for weekly view
const DayIndicator = ({ label, status }) => {
  const getStyle = () => {
    switch (status) {
      case 'completed':
        return { bg: COLORS.success + '20', border: COLORS.success, icon: 'checkmark', iconColor: COLORS.success };
      case 'today':
        return { bg: COLORS.primary + '20', border: COLORS.primary, icon: 'flame', iconColor: COLORS.primary };
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

// Milestone card for rewards display
const MilestoneCard = ({ days, milestone, isCompleted, isCurrent }) => (
  <View 
    style={[
      styles.milestoneCard,
      isCompleted && styles.milestoneCardCompleted,
      isCurrent && styles.milestoneCardCurrent
    ]}
  >
    <View style={[styles.milestoneHeader, { backgroundColor: isCompleted ? milestone.color : '#E5E7EB' }]}>
      <Text style={styles.milestoneEmoji}>{milestone.emoji}</Text>
      <Text style={[styles.milestoneDays, { color: isCompleted ? 'white' : '#6B7280' }]}>
        {days} Days
      </Text>
    </View>
    <View style={styles.milestoneContent}>
      <Text style={[styles.milestoneTitle, { color: isCompleted ? milestone.color : '#374151' }]}>
        {milestone.title}
      </Text>
      <Text style={[styles.milestoneReward, { color: isCompleted ? '#059669' : '#6B7280' }]}>
        {milestone.reward}
      </Text>
      {isCompleted && (
        <View style={styles.completedBadge}>
          <Ionicons name="checkmark-circle" size={12} color="#059669" />
          <Text style={styles.completedText}>Unlocked</Text>
        </View>
      )}
    </View>
  </View>
);
// Main streak tracker component
const StreakTracker = () => {
  const streakData = useSelector(selectStreakData);
  const milestoneConfig = useSelector(selectStreakMilestones);

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
        return { label, status: index === todayIndex ? 'today' : 'completed' };
      }
      if (!todayCompleted && index === completedCount && index < days.length) {
        return { label, status: 'broken' };
      }
      return { label, status: 'future' };
    });
  }, [currentStreak, todayCompleted]);

  const milestones = useMemo(() => {
    return (Array.isArray(milestoneConfig) ? milestoneConfig : [])
      .map(normalizeMilestone)
      .filter((item) => Number.isFinite(item.days) && item.days > 0)
      .sort((a, b) => a.days - b.days);
  }, [milestoneConfig]);

  // Get next milestone info
  const milestoneInfo = useMemo(() => {
    const next = milestones.find((m) => m.days > currentStreak);
    
    if (next) {
      return {
        days: next.days,
        daysRemaining: next.days - currentStreak,
        reward: next,
      };
    }
    return null;
  }, [currentStreak, milestones]);

  // Dynamic message
  const getMessage = () => {
    if (isLoading) return 'Loading your streak...';
    if (currentStreak === 0) return 'Start your streak today!';
    if (currentStreak === 1) return 'Great start! Keep it going!';
    if (currentStreak >= 50) return `Amazing dedication! ${currentStreak} days!`;
    if (todayCompleted) return `${currentStreak} days strong!`;
    return `${currentStreak} days, check in to continue!`;
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
          {/* Header with streak value */}
          <View style={styles.header}>
            <View style={styles.headerLeft}>
              <Text style={styles.fireEmoji}>🔥</Text>
              <View style={styles.headerText}>
                <Text style={styles.streakCount}>{currentStreak} Days</Text>
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

          {/* Week visualization */}
          <View style={styles.weekContainer}>
            {weekDays.map((day, index) => (
              <DayIndicator key={index} label={day.label} status={day.status} />
            ))}
          </View>

          {/* Next milestone preview */}
          {milestoneInfo && (
            <View style={styles.nextMilestoneContainer}>
              <Ionicons name="gift" size={14} color="rgba(255,255,255,0.9)" />
              <View style={styles.milestonePreviewText}>
                <Text style={styles.nextMilestoneMain}>
                  {milestoneInfo.daysRemaining} more days
                </Text>
                <Text style={styles.nextMilestoneSmall}>
                  until {milestoneInfo.reward.title}
                </Text>
              </View>
            </View>
          )}
        </View>
      </LinearGradient>

      {/* Rewards Journey Section */}
      <View style={styles.rewardsSection}>
        <View style={styles.rewardsSectionHeader}>
          <Ionicons name="star" size={18} color={COLORS.primary} />
          <Text style={styles.rewardsSectionTitle}>Rewards Journey</Text>
        </View>
        
        <ScrollView 
          horizontal 
          showsHorizontalScrollIndicator={false} 
          style={styles.milestoneScroll}
          contentContainerStyle={styles.milestoneScrollContent}
        >
          {milestones.map((milestone) => {
            const isCompleted = currentStreak >= milestone.days;
            const isCurrent = currentStreak === milestone.days;
            
            return (
              <MilestoneCard 
                key={milestone.days}
                days={milestone.days}
                milestone={milestone}
                isCompleted={isCompleted}
                isCurrent={isCurrent}
              />
            );
          })}
        </ScrollView>
      </View>
    </View>
  );
};

const styles = StyleSheet.create({
  container: {
    marginHorizontal: 16,
    marginVertical: 12,
    borderRadius: 16,
    overflow: 'hidden',
    shadowColor: '#FF6B35',
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.15,
    shadowRadius: 8,
    elevation: 5,
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
    alignItems: 'center',
  },
  headerLeft: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
    flex: 1,
  },
  fireEmoji: {
    fontSize: 32,
  },
  headerText: {
    flex: 1,
  },
  streakCount: {
    fontSize: 24,
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
    backgroundColor: 'rgba(255,255,255,0.2)',
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
    fontSize: 11,
    fontWeight: '700',
  },
  nextMilestoneContainer: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: 'rgba(255,255,255,0.15)',
    paddingHorizontal: 12,
    paddingVertical: 10,
    borderRadius: 10,
    gap: 10,
  },
  milestonePreviewText: {
    flex: 1,
  },
  nextMilestoneMain: {
    fontSize: 14,
    fontWeight: '700',
    color: COLORS.white,
  },
  nextMilestoneSmall: {
    fontSize: 12,
    color: 'rgba(255,255,255,0.85)',
    marginTop: 2,
  },
  // Rewards section
  rewardsSection: {
    backgroundColor: COLORS.white,
    paddingHorizontal: 16,
    paddingVertical: 14,
    borderBottomLeftRadius: 16,
    borderBottomRightRadius: 16,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.08,
    shadowRadius: 4,
    elevation: 2,
  },
  rewardsSectionHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    marginBottom: 12,
  },
  rewardsSectionTitle: {
    fontSize: 16,
    fontWeight: '700',
    color: COLORS.textPrimary,
  },
  milestoneScroll: {
    marginHorizontal: -16,
    paddingHorizontal: 16,
  },
  milestoneScrollContent: {
    gap: 12,
    paddingRight: 16,
  },
  milestoneCard: {
    width: 130,
    backgroundColor: COLORS.white,
    borderRadius: 12,
    borderWidth: 2,
    borderColor: '#E5E7EB',
    overflow: 'hidden',
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.05,
    shadowRadius: 3,
    elevation: 1,
  },
  milestoneCardCompleted: {
    borderColor: '#10B981',
    shadowColor: '#10B981',
    shadowOpacity: 0.15,
  },
  milestoneCardCurrent: {
    borderColor: '#F59E0B',
    shadowColor: '#F59E0B',
    shadowOpacity: 0.2,
    transform: [{ scale: 1.04 }],
  },
  milestoneHeader: {
    paddingVertical: 10,
    paddingHorizontal: 10,
    alignItems: 'center',
    justifyContent: 'center',
    minHeight: 55,
  },
  milestoneEmoji: {
    fontSize: 22,
    marginBottom: 2,
  },
  milestoneDays: {
    fontSize: 12,
    fontWeight: '700',
  },
  milestoneContent: {
    padding: 10,
  },
  milestoneTitle: {
    fontSize: 13,
    fontWeight: '700',
    marginBottom: 3,
  },
  milestoneReward: {
    fontSize: 11,
    fontWeight: '500',
    marginBottom: 6,
  },
  completedBadge: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#D1FAE5',
    paddingHorizontal: 6,
    paddingVertical: 3,
    borderRadius: 6,
    gap: 3,
    alignSelf: 'flex-start',
  },
  completedText: {
    fontSize: 10,
    fontWeight: '600',
    color: '#059669',
  },
});

export default StreakTracker;