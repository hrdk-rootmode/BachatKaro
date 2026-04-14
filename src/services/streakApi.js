// ============================================
// DEALHUNT APP - STREAK API SERVICE
// Part 4: Streak System & Gamification
// ============================================

import { get, post } from './api';
import { API } from '../utils/constants';

const normalizePayload = (response) => {
  const payload = response?.data;

  if (payload && typeof payload === 'object' && payload.data && typeof payload.data === 'object') {
    return payload.data;
  }

  return payload && typeof payload === 'object' ? payload : {};
};

const buildErrorResult = (response, fallbackMessage, unauthorizedMessage) => {
  const statusCode = response?.statusCode ?? response?.status ?? 'UNKNOWN';

  if (statusCode === 401 || response?.code === 'UNAUTHORIZED') {
    return {
      success: false,
      error: unauthorizedMessage,
      code: 'UNAUTHORIZED',
    };
  }

  return {
    success: false,
    error: response?.error || fallbackMessage,
    code: statusCode,
  };
};

// --------------------------------------------
// STREAK API METHODS
// --------------------------------------------

export const streakAPI = {
  /**
   * Get current streak status for authenticated user
   * @returns {Promise<{success: boolean, data?: Object, error?: string}>}
   */
  getStreakStatus: async () => {
    try {
      const response = await get(API.ENDPOINTS.STREAK_STATUS);

      if (!response?.success) {
        return buildErrorResult(response, 'Failed to fetch streak status', 'Please login to view your streak');
      }

      const data = normalizePayload(response);

      return {
        success: true,
        data: {
          currentStreak: data.current_streak ?? data.currentStreak ?? 0,
          longestStreak: data.longest_streak ?? data.longestStreak ?? 0,
          todayCompleted:
            data.today_completed ??
            data.todayCompleted ??
            (typeof data.can_check_in_today === 'boolean' ? !data.can_check_in_today : false),
          lastVisitDate: data.last_visit_date || data.lastVisitDate || null,
          streakMilestoneReward:
            data.streak_milestone_reward ||
            data.streakMilestoneReward ||
            data.reward_unlocked ||
            data.rewardUnlocked ||
            null,
          // Additional fields the backend may provide
          nextMilestone: data.next_milestone || data.nextMilestone || null,
          streakHistory: data.streak_history || data.streakHistory || [],
        },
      };
    } catch (error) {
      console.error('[StreakAPI] Get status error:', error);

      if (error.response?.status === 401) {
        return {
          success: false,
          error: 'Please login to view your streak',
          code: 'UNAUTHORIZED',
        };
      }

      return {
        success: false,
        error:
          error.response?.data?.detail ||
          error.message ||
          'Failed to fetch streak status',
        code: error.response?.status || 'UNKNOWN',
      };
    }
  },

  /**
   * Check in for today – marks the daily visit and returns updated streak
   * @returns {Promise<{success: boolean, data?: Object, error?: string}>}
   */
  checkIn: async () => {
    try {
      const response = await post(API.ENDPOINTS.STREAK_CHECK_IN);

      if (!response?.success) {
        if (response?.statusCode === 409 || response?.status === 409) {
          const conflictData = normalizePayload(response);

          return {
            success: true,
            data: {
              todayCompleted: true,
              alreadyCheckedIn: true,
              message: response?.error || conflictData?.detail || 'Already checked in today',
              currentStreak: conflictData?.current_streak ?? conflictData?.currentStreak ?? 0,
              longestStreak: conflictData?.longest_streak ?? conflictData?.longestStreak ?? 0,
            },
          };
        }

        return buildErrorResult(response, 'Failed to check in', 'Please login to check in');
      }

      const data = normalizePayload(response);

      return {
        success: true,
        data: {
          currentStreak: data.current_streak ?? data.currentStreak ?? 0,
          longestStreak: data.longest_streak ?? data.longestStreak ?? 0,
          todayCompleted: data.today_completed ?? data.todayCompleted ?? true,
          lastVisitDate: data.last_visit_date || data.lastVisitDate || null,
          streakMilestoneReward:
            data.streak_milestone_reward ||
            data.streakMilestoneReward ||
            data.reward_unlocked ||
            data.rewardUnlocked ||
            null,
          message: data.message || 'Check-in successful!',
          isNewStreak: data.is_new_streak ?? data.isNewStreak ?? false,
          wasReset: data.was_reset ?? data.wasReset ?? false,
        },
      };
    } catch (error) {
      console.error('[StreakAPI] Check-in error:', error);

      // Already checked in today – treat as soft success
      if (error.response?.status === 409) {
        return {
          success: true,
          data: {
            todayCompleted: true,
            alreadyCheckedIn: true,
            message: error.response?.data?.detail || 'Already checked in today',
            currentStreak: error.response?.data?.current_streak ?? null,
            longestStreak: error.response?.data?.longest_streak ?? null,
          },
        };
      }

      if (error.response?.status === 401) {
        return {
          success: false,
          error: 'Please login to check in',
          code: 'UNAUTHORIZED',
        };
      }

      return {
        success: false,
        error:
          error.response?.data?.detail ||
          error.message ||
          'Failed to check in',
        code: error.response?.status || 'UNKNOWN',
      };
    }
  },

  /**
   * Get milestone progress for the authenticated user
   * @returns {Promise<{success: boolean, data?: Object, error?: string}>}
   */
  getMilestones: async () => {
    try {
      const response = await get(API.ENDPOINTS.STREAK_MILESTONES);

      if (!response?.success) {
        return buildErrorResult(response, 'Failed to fetch milestones', 'Please login to view milestones');
      }

      const data = normalizePayload(response);

      return {
        success: true,
        data: {
          milestones: data.milestones || [],
          currentStreak: data.current_streak ?? data.currentStreak ?? 0,
          nextMilestone: data.next_milestone || data.nextMilestone || null,
        },
      };
    } catch (error) {
      console.error('[StreakAPI] Get milestones error:', error);

      if (error.response?.status === 401) {
        return {
          success: false,
          error: 'Please login to view milestones',
          code: 'UNAUTHORIZED',
        };
      }

      return {
        success: false,
        error:
          error.response?.data?.detail ||
          error.message ||
          'Failed to fetch milestones',
        code: error.response?.status || 'UNKNOWN',
      };
    }
  },

  /**
   * Development helper: completely reset streak and reward-derived bonuses
   */
  debugReset: async () => {
    try {
      const response = await post(API.ENDPOINTS.STREAK_DEBUG_RESET);
      if (!response?.success) {
        return buildErrorResult(response, 'Failed to reset streak', 'Please login to reset streak');
      }

      return {
        success: true,
        data: normalizePayload(response),
      };
    } catch (error) {
      return {
        success: false,
        error: error?.response?.data?.detail || error?.message || 'Failed to reset streak',
      };
    }
  },
};

export default streakAPI;