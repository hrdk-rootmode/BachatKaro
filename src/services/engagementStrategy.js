// ============================================
// ENGAGEMENT STRATEGY SERVICE
// Intelligent user retention & gamification psychology
// ============================================

/**
 * ENGAGEMENT INTELLIGENCE FRAMEWORK
 * 
 * Key Principles:
 * 1. Loss Aversion: Users fear losing streaks more than gaining rewards
 * 2. Social Proof: Users compare progress with peers/averages
 * 3. Progress Visualization: Show tangible progress (% of goal)
 * 4. Variable Rewards: Unpredictable rewards maintain engagement longer
 * 5. Urgency & Scarcity: Limited time offers create action
 * 6. Identity Building: "You are a deal hunter" not "You hunt deals"
 */

// Engagement triggers based on streak milestones and user behavior
export const ENGAGEMENT_TRIGGERS = {
  // Retention alerts (push notifications / in-app)
  STREAK_RISK: {
    at: 'next_day_missing', // Trigger when 1 day away from losing streak
    intensity: 'high',
    message: 'Your {day}-day streak is almost gone! Check in now to keep it alive 🔥',
    icon: 'flame-outline',
    color: '#EF4444',
  },
  
  MILESTONE_APPROACHING: {
    at: 'milestone_1_day_away',
    intensity: 'medium',
    message: 'One more day to unlock {reward_title}! You\'ve got this 💪',
    icon: 'gift',
    color: '#F59E0B',
  },

  STREAK_MILESTONE_REACHED: {
    at: 'milestone_reached',
    intensity: 'max',
    message: 'Incredible! You\'ve reached {streak} days! 🎉',
    icon: 'trophy',
    color: '#10B981',
    action: 'show_celebration_modal',
  },

  COMEBACK: {
    at: 'user_returns_after_miss',
    intensity: 'medium',
    message: 'Welcome back! Your new streak starts today. You\'ve got this! 🚀',
    icon: 'play-circle',
    color: '#3B82F6',
  },

  SOCIAL_PROOF: {
    at: 'every_3rd_checkin',
    intensity: 'low',
    message: 'You\'re now in the top {percentile}% of active savers! 👑',
    icon: 'stats-chart',
    color: '#8B5CF6',
  },
};

// Personalized engagement messaging based on user behavior patterns
export const getPersonalizedEngagementMessage = (currentStreak, behavior) => {
  const { daysActive, missCount, lastMissDate, isConsistent } = behavior || {};

  if (currentStreak === 0 && missCount > 2) {
    return {
      title: 'We missed you! 💔',
      subtitle: 'Starting fresh is brave. Let\'s build a better habit together.',
      tone: 'supportive',
      urgency: 'low',
    };
  }

  if (currentStreak > 0 && currentStreak < 7 && isConsistent) {
    return {
      title: 'You\'ve got the momentum! 🔥',
      subtitle: 'A full week is within sight. What\'s just one more day?',
      tone: 'motivational',
      urgency: 'medium',
    };
  }

  if (currentStreak >= 7 && currentStreak < 30) {
    return {
      title: 'Hall of Fame incoming 🏆',
      subtitle: `You're ${currentStreak} days in. Only ${30 - currentStreak} days to Monthly Champion status!`,
      tone: 'aspirational',
      urgency: 'high',
    };
  }

  if (currentStreak >= 30 && currentStreak < 100) {
    return {
      title: 'Legendary in the making 👑',
      subtitle: `You're in the elite 5%. Century Champion is just ${100 - currentStreak} days away!`,
      tone: 'elite',
      urgency: 'high',
    };
  }

  if (currentStreak >= 100) {
    return {
      title: 'You ARE the legend 🌟',
      subtitle: 'Keep this streak alive forever. You\'re inspiration to others.',
      tone: 'legendary',
      urgency: 'low',
    };
  }

  return {
    title: 'One check-in away from rewards ✨',
    subtitle: 'Your next milestone is closer than you think.',
    tone: 'supportive',
    urgency: 'medium',
  };
};

// Variable reward system - unpredictable bonuses maintain engagement
export const getVariableReward = (currentStreak) => {
  const random = Math.random();
  
  // 10% chance of bonus reward
  if (random < 0.1) {
    return {
      type: 'bonus',
      message: 'Bonus! You earned an extra reward today! 🎊',
      duration: 12,
      icon: '✨',
    };
  }

  // 20% chance of streak multiplier
  if (random < 0.3) {
    return {
      type: 'multiplier',
      message: 'Double rewards today! Keep the streak alive! 2x 🔥',
      multiplier: 2,
      icon: '2️⃣',
    };
  }

  return null;
};

// Engagement scoring to determine when to show subtle nudges
export const calculateEngagementScore = (currentStreak, userData) => {
  let score = 0;

  // Streak consistency
  score += Math.min(currentStreak * 2, 40);

  // Watchlist activity
  score += Math.min((userData?.watchlistCount || 0) * 5, 30);

  // Recent activity
  const lastActiveMs = new Date(userData?.lastActive).getTime();
  const daysSinceActive = (Date.now() - lastActiveMs) / (1000 * 60 * 60 * 24);
  if (daysSinceActive < 1) score += 20;
  if (daysSinceActive < 7) score += 10;

  // Payment history (shows committed user)
  if (userData?.planExpiresAt) score += 15;

  return Math.min(score, 100);
};

// Smart timing for notifications (don't overwhelm users)
export const getOptimalNotificationTime = (currentStreak) => {
  if (currentStreak < 3) {
    // New users: frequent encouragement
    return { frequency: 'daily', bestTime: 'morning' };
  }
  if (currentStreak < 10) {
    // Building habit: support critical days
    return { frequency: 'every_other_day', bestTime: 'evening' };
  }
  if (currentStreak < 30) {
    // Building momentum: milestone focus
    return { frequency: '3_times_week', bestTime: 'midnight_warning' };
  }
  
  // Established users: maintenance only
  return { frequency: 'weekly', bestTime: 'weekly_summary' };
};

// Competitive social proof (gamification)
export const getUserRankTier = (currentStreak) => {
  if (currentStreak < 3) return { tier: 'Spark', emoji: '✨', color: '#FBBF24' };
  if (currentStreak < 7) return { tier: 'Flame', emoji: '🔥', color: '#FF6B35' };
  if (currentStreak < 15) return { tier: 'Inferno', emoji: '🌪️', color: '#F97316' };
  if (currentStreak < 30) return { tier: 'Legendary', emoji: '⚡', color: '#EF4444' };
  if (currentStreak < 60) return { tier: 'Mythical', emoji: '👑', color: '#8B5CF6' };
  return { tier: 'Eternal', emoji: '🔮', color: '#6366F1' };
};

export default {
  ENGAGEMENT_TRIGGERS,
  getPersonalizedEngagementMessage,
  getVariableReward,
  calculateEngagementScore,
  getOptimalNotificationTime,
  getUserRankTier,
};
