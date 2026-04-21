// ============================================
// DEALHUNT APP - STREAK REDUX SLICE
// Part 4: Gamification & Engagement System
// ============================================

import { createSlice, createAsyncThunk, createSelector } from '@reduxjs/toolkit';
import { streakAPI } from '../services/streakApi';
import { activateProTrial, refreshUserData } from './authSlice';
import { fetchWatchlist } from './watchlistSlice';
import { fetchSubscriptionStatus } from './subscriptionSlice';

const getMilestoneDays = (milestones = []) => {
  return milestones
    .map((m) => Number(m?.days ?? m?.streak_days ?? 0))
    .filter((d) => Number.isFinite(d) && d > 0)
    .sort((a, b) => a - b);
};

const getNextMilestoneDayFromMilestones = (streakDays, milestones = []) => {
  const days = getMilestoneDays(milestones);
  return days.find((day) => day > Number(streakDays || 0)) || null;
};

// --------------------------------------------
// INITIAL STATE
// --------------------------------------------

const initialState = {
  // Streak data
  currentStreak: 0,
  longestStreak: 0,
  todayCompleted: false,
  lastVisitDate: null, // 'YYYY-MM-DD' format
  
  // Additional data from backend
  nextMilestone: null,
  milestones: [],
  streakHistory: [],
  
  // Loading states
  isLoading: false,
  isCheckingIn: false,
  error: null,
  
  // Reward system
  unlockedReward: null, // { milestone, reward_type, details: { duration_hours, message } }
  isRewardModalVisible: false,
  
  // Metadata
  lastCheckedAt: null, // Timestamp of last check
};

// --------------------------------------------
// ASYNC THUNKS
// --------------------------------------------

/**
 * Check and mark streak on app launch
 * Implements the core app-launch data flow:
 * 1. First GET current status
 * 2. If today not completed, POST check-in
 * 3. Update streak state
 * 4. Trigger reward modal if milestone reached
 */
export const checkAndMarkStreak = createAsyncThunk(
  'streak/checkAndMark',
  async (_, { dispatch, rejectWithValue }) => {
    try {
      // Step 1: Get current status without modifying
      const statusResult = await streakAPI.getStreakStatus();
      
      if (!statusResult.success) {
        // Non-critical: don't block app if streak service is down
        console.warn('[StreakSlice] Status check failed (non-critical):', statusResult.error);
        return rejectWithValue(statusResult.error || 'Failed to get streak status');
      }
      
      const statusData = statusResult.data;
      
      // Step 2: If already checked in today, return status
      if (statusData.todayCompleted) {
        const milestones = Array.isArray(statusData.milestones) ? statusData.milestones : [];
        console.log('[StreakSlice] Already checked in today. Current streak:', statusData.currentStreak);
        return {
          currentStreak: statusData.currentStreak,
          longestStreak: statusData.longestStreak,
          todayCompleted: statusData.todayCompleted,
          lastVisitDate: statusData.lastVisitDate,
          nextMilestone:
            statusData.nextMilestone ??
            getNextMilestoneDayFromMilestones(statusData.currentStreak, milestones),
          milestones,
          streakHistory: statusData.streakHistory,
          streakMilestoneReward: statusData.streakMilestoneReward || null,
        };
      }
      
      // Step 3: Not checked in yet, perform check-in
      console.log('[StreakSlice] Checking in for today...');
      const checkInResult = await streakAPI.checkIn();
      
      if (!checkInResult.success) {
        console.warn('[StreakSlice] Check-in failed (non-critical):', checkInResult.error);
        // Return the status we got earlier rather than failing completely
        return {
          currentStreak: statusData.currentStreak,
          longestStreak: statusData.longestStreak,
          todayCompleted: statusData.todayCompleted,
          lastVisitDate: statusData.lastVisitDate,
          nextMilestone: statusData.nextMilestone,
          streakHistory: statusData.streakHistory,
          streakMilestoneReward: null,
        };
      }
      
      // Step 4: Return updated data from check-in
      const checkInData = checkInResult.data;
      const milestones = Array.isArray(checkInData.milestones)
        ? checkInData.milestones
        : Array.isArray(statusData.milestones)
          ? statusData.milestones
          : [];
      
      // Log streak events
      if (checkInData.isNewStreak) {
        console.log('[StreakSlice] 🎉 New streak started!');
      }
      if (checkInData.wasReset) {
        console.log('[StreakSlice] 💔 Streak was reset. Starting fresh.');
      }
      if (checkInData.streakMilestoneReward) {
        console.log('[StreakSlice] 🎁 Milestone reward unlocked!', checkInData.streakMilestoneReward);
        const rewardType = checkInData.streakMilestoneReward.reward_type;
        if (rewardType === 'watchlist_slots') {
          dispatch(fetchWatchlist({ forceRefresh: true }));
        }
        if (rewardType === 'premium_days' || rewardType === 'free_month') {
          dispatch(fetchSubscriptionStatus());
        }
      }

      // Keep user/watchlist state synced after check-in updates streak/usage stats.
      dispatch(refreshUserData());
      dispatch(fetchWatchlist({ forceRefresh: true }));
      
      return {
        currentStreak: checkInData.currentStreak,
        longestStreak: checkInData.longestStreak,
        todayCompleted: checkInData.todayCompleted,
        lastVisitDate: checkInData.lastVisitDate,
        nextMilestone:
          checkInData.nextMilestone ??
          getNextMilestoneDayFromMilestones(checkInData.currentStreak, milestones),
        milestones,
        streakHistory: checkInData.streakHistory || [],
        streakMilestoneReward: checkInData.streakMilestoneReward || null,
        message: checkInData.message,
        isNewStreak: checkInData.isNewStreak,
        wasReset: checkInData.wasReset,
      };
    } catch (error) {
      console.error('[StreakSlice] checkAndMarkStreak error:', error);
      // Non-critical: don't block app launch
      return rejectWithValue(error.message || 'Streak check failed');
    }
  }
);

/**
 * Fetch milestone information
 * Optional: Load milestone data separately for milestone screen
 */
export const fetchMilestones = createAsyncThunk(
  'streak/fetchMilestones',
  async (_, { rejectWithValue }) => {
    try {
      const result = await streakAPI.getMilestones();
      
      if (!result.success) {
        return rejectWithValue(result.error || 'Failed to fetch milestones');
      }
      
      return result.data;
    } catch (error) {
      console.error('[StreakSlice] fetchMilestones error:', error);
      return rejectWithValue(error.message || 'Failed to fetch milestones');
    }
  }
);

/**
 * Claim streak reward
 * This will be connected to authSlice in Phase 2
 * @param {Object} reward - The reward object from backend
 */
export const claimStreakReward = createAsyncThunk(
  'streak/claimReward',
  async (reward, { dispatch, rejectWithValue }) => {
    try {
      console.log('[StreakSlice] Claiming reward:', reward);

      const rewardType = reward?.reward_type || reward?.rewardType || reward?.type || null;

      if (rewardType === 'premium_days') {
        const durationHours = Number(reward?.details?.duration_hours || reward?.reward_value || 24);
        if (!Number.isFinite(durationHours) || durationHours <= 0) {
          return rejectWithValue('Invalid reward duration');
        }

        // Activate temporary Pro access from claimed streak reward.
        dispatch(activateProTrial({ durationHours }));
      }
      
      // Hide the modal
      dispatch(hideRewardModal());
      
      return { success: true, rewardType };
    } catch (error) {
      console.error('[StreakSlice] claimStreakReward error:', error);
      return rejectWithValue(error.message || 'Failed to claim reward');
    }
  }
);

/**
 * Development-only helper: fully reset streak and streak rewards on backend + local state.
 * Keeps data consistent after app reload.
 */
export const debugResetStreakCompletelyForDev = createAsyncThunk(
  'streak/debugResetComplete',
  async (_, { dispatch, rejectWithValue }) => {
    try {
      const result = await streakAPI.debugReset();
      if (!result?.success) {
        return rejectWithValue(result?.error || 'Failed to reset streak');
      }

      dispatch(fetchWatchlist({ forceRefresh: true }));
      dispatch(refreshUserData());

      return result.data || {};
    } catch (error) {
      return rejectWithValue(error?.message || 'Failed to reset streak');
    }
  }
);

// --------------------------------------------
// STREAK SLICE
// --------------------------------------------

const streakSlice = createSlice({
  name: 'streak',
  initialState,
  
  reducers: {
    /**
     * Hide the reward modal
     */
    hideRewardModal: (state) => {
      state.isRewardModalVisible = false;
      state.unlockedReward = null;
    },
    
    /**
     * Manually reset streak state (for testing/debugging)
     */
    resetStreakState: () => initialState,
    
    /**
     * Clear error state
     */
    clearStreakError: (state) => {
      state.error = null;
    },
    
    /**
     * Update last checked timestamp
     */
    updateLastChecked: (state) => {
      state.lastCheckedAt = new Date().toISOString();
    },

    /**
     * Development-only helper: increases streak for quick UI testing.
     * Handles both positive increments and missed days (negative values).
     */
    debugIncreaseStreakForDev: (state, action) => {
      const increment = Number(action.payload?.days || 1);
      const previous = Math.max(0, Number(state.currentStreak || 0));
      
      // Handle missed day (negative increment)
      if (increment < 0) {
        // Reset streak if missed day
        state.currentStreak = 0;
        state.todayCompleted = false;
        state.lastVisitDate = null; // Reset to simulate missed day
        console.log(`[StreakDebug] Day missed! Streak reset from ${previous} to 0`);
      } else {
        // Normal increment
        const next = previous + increment;
        state.currentStreak = next;
        state.todayCompleted = true;
        state.lastVisitDate = new Date().toISOString().split('T')[0];

      }

      state.longestStreak = Math.max(Number(state.longestStreak || 0), state.currentStreak);
      state.nextMilestone = getNextMilestoneDayFromMilestones(state.currentStreak, state.milestones);
      state.lastCheckedAt = new Date().toISOString();
      state.error = null;
      state.isLoading = false;
      state.isCheckingIn = false;
    },

    /**
     * Development-only helper: resets streak state for repeat testing.
     */
    debugResetStreakForDev: (state) => {
      console.log(`[StreakDebug] Manual streak reset from ${state.currentStreak} to 0`);
      state.currentStreak = 0;
      state.longestStreak = 0;
      state.todayCompleted = false;
      state.lastVisitDate = null;
      state.nextMilestone = getNextMilestoneDayFromMilestones(0, state.milestones);
      state.streakHistory = [];
      state.unlockedReward = null;
      state.isRewardModalVisible = false;
      state.error = null;
      state.isLoading = false;
      state.isCheckingIn = false;
      state.lastCheckedAt = new Date().toISOString();
    },
  },
  
  extraReducers: (builder) => {
    // --------------------------------------------
    // CHECK AND MARK STREAK
    // --------------------------------------------
    builder.addCase(checkAndMarkStreak.pending, (state) => {
      state.isLoading = true;
      state.isCheckingIn = true;
      state.error = null;
    });
    
    builder.addCase(checkAndMarkStreak.fulfilled, (state, action) => {
      const payload = action.payload;
      
      state.isLoading = false;
      state.isCheckingIn = false;
      state.currentStreak = payload.currentStreak;
      state.longestStreak = payload.longestStreak;
      state.todayCompleted = payload.todayCompleted;
      state.lastVisitDate = payload.lastVisitDate;
      state.nextMilestone = payload.nextMilestone;
      if (Array.isArray(payload.milestones)) {
        state.milestones = payload.milestones;
      }
      state.streakHistory = payload.streakHistory || [];
      state.lastCheckedAt = new Date().toISOString();
      state.error = null;
      
      // CRITICAL: Check if milestone reward was returned
      if (payload.streakMilestoneReward) {
        state.unlockedReward = payload.streakMilestoneReward;
        state.isRewardModalVisible = true;
      }
    });
    
    builder.addCase(checkAndMarkStreak.rejected, (state, action) => {
      state.isLoading = false;
      state.isCheckingIn = false;
      state.error = action.payload || 'Failed to check streak';
      
      // Don't show error to user - streak is non-critical feature
      console.warn('[StreakSlice] Streak check failed (non-critical):', state.error);
    });
    
    // --------------------------------------------
    // FETCH MILESTONES
    // --------------------------------------------
    builder.addCase(fetchMilestones.pending, (state) => {
      state.isLoading = true;
      state.error = null;
    });
    
    builder.addCase(fetchMilestones.fulfilled, (state, action) => {
      state.isLoading = false;
      state.milestones = Array.isArray(action.payload.milestones) ? action.payload.milestones : [];
      state.nextMilestone =
        action.payload.nextMilestone ??
        getNextMilestoneDayFromMilestones(state.currentStreak, state.milestones);
    });
    
    builder.addCase(fetchMilestones.rejected, (state, action) => {
      state.isLoading = false;
      state.error = action.payload || 'Failed to fetch milestones';
    });
    
    // --------------------------------------------
    // CLAIM REWARD
    // --------------------------------------------
    builder.addCase(claimStreakReward.pending, (state) => {
      state.isLoading = true;
    });
    
    builder.addCase(claimStreakReward.fulfilled, (state) => {
      state.isLoading = false;
      // Modal already hidden by the thunk dispatching hideRewardModal
    });
    
    builder.addCase(claimStreakReward.rejected, (state, action) => {
      state.isLoading = false;
      state.error = action.payload || action.error.message || 'Failed to claim reward';
    });

    builder.addCase(debugResetStreakCompletelyForDev.pending, (state) => {
      state.isLoading = true;
      state.error = null;
    });

    builder.addCase(debugResetStreakCompletelyForDev.fulfilled, (state) => {
      const nowIso = new Date().toISOString();
      state.isLoading = false;
      state.currentStreak = 0;
      state.longestStreak = 0;
      state.todayCompleted = true;
      state.lastVisitDate = nowIso.split('T')[0];
      state.nextMilestone = getNextMilestoneDayFromMilestones(0, state.milestones);
      state.streakHistory = [];
      state.unlockedReward = null;
      state.isRewardModalVisible = false;
      state.lastCheckedAt = nowIso;
      state.error = null;
      state.isCheckingIn = false;
    });

    builder.addCase(debugResetStreakCompletelyForDev.rejected, (state, action) => {
      state.isLoading = false;
      state.error = action.payload || action.error.message || 'Failed to reset streak';
    });
  },
});

// --------------------------------------------
// EXPORTS
// --------------------------------------------

// Actions
export const {
  hideRewardModal,
  resetStreakState,
  clearStreakError,
  updateLastChecked,
  debugIncreaseStreakForDev,
  debugResetStreakForDev,
} = streakSlice.actions;

// Selectors
export const selectCurrentStreak = (state) => state.streak.currentStreak;
export const selectLongestStreak = (state) => state.streak.longestStreak;
export const selectTodayCompleted = (state) => state.streak.todayCompleted;
export const selectLastVisitDate = (state) => state.streak.lastVisitDate;
export const selectNextMilestone = (state) => state.streak.nextMilestone;
export const selectStreakMilestones = (state) => state.streak.milestones;
export const selectStreakHistory = (state) => state.streak.streakHistory;
export const selectStreakLoading = (state) => state.streak.isLoading;
export const selectStreakError = (state) => state.streak.error;
export const selectUnlockedReward = (state) => state.streak.unlockedReward;
export const selectIsRewardModalVisible = (state) => state.streak.isRewardModalVisible;
export const selectLastCheckedAt = (state) => state.streak.lastCheckedAt;

// Composite selector for UI
export const selectStreakData = createSelector(
  [
    selectCurrentStreak,
    selectLongestStreak,
    selectTodayCompleted,
    selectLastVisitDate,
    selectNextMilestone,
    selectStreakLoading,
    selectLastCheckedAt,
  ],
  (currentStreak, longestStreak, todayCompleted, lastVisitDate, nextMilestone, isLoading, lastCheckedAt) => ({
    currentStreak,
    longestStreak,
    todayCompleted,
    lastVisitDate,
    nextMilestone,
    isLoading,
    lastCheckedAt,
  })
);

// Reducer
export default streakSlice.reducer;