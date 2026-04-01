// ============================================
// DEALHUNT APP - STREAK API SERVICE
// Part 4: Streak System & Gamification
// ============================================

import apiClient from './api';
import { API } from '../utils/constants';

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
      const response = await apiClient.get(API.ENDPOINTS.STREAK_STATUS);

      return {
        success: true,
        data: {
          currentStreak: response.data.current_streak ?? 0,
          longestStreak: response.data.longest_streak ?? 0,
          todayCompleted: response.data.today_completed ?? false,
          lastVisitDate: response.data.last_visit_date || null,
          streakMilestoneReward: response.data.streak_milestone_reward || null,
          // Additional fields the backend may provide
          nextMilestone: response.data.next_milestone || null,
          streakHistory: response.data.streak_history || [],
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
      const response = await apiClient.post(API.ENDPOINTS.STREAK_CHECK_IN);

      return {
        success: true,
        data: {
          currentStreak: response.data.current_streak ?? 0,
          longestStreak: response.data.longest_streak ?? 0,
          todayCompleted: response.data.today_completed ?? true,
          lastVisitDate: response.data.last_visit_date || null,
          streakMilestoneReward: response.data.streak_milestone_reward || null,
          message: response.data.message || 'Check-in successful!',
          isNewStreak: response.data.is_new_streak || false,
          wasReset: response.data.was_reset || false,
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
      const response = await apiClient.get(API.ENDPOINTS.STREAK_MILESTONES);

      return {
        success: true,
        data: {
          milestones: response.data.milestones || [],
          currentStreak: response.data.current_streak ?? 0,
          nextMilestone: response.data.next_milestone || null,
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
};

export default streakAPI;