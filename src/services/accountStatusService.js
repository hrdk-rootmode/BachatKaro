import api from './api';

/**
 * Account Status Service
 * Handles checking and managing account status including banned users
 */

export const checkAccountStatus = async () => {
  try {
    const response = await api.get('/auth/account-status');
    return response.data;
  } catch (error) {
    console.error('Failed to check account status:', error);
    throw error;
  }
};

/**
 * Handle API errors for account status
 * Returns true if user is banned, false otherwise
 */
export const handleAccountStatusError = (error) => {
  if (error.response?.status === 403) {
    const errorData = error.response.data;
    if (errorData?.error === 'account_blocked') {
      return {
        isBanned: true,
        reason: errorData.reason || 'Violation of terms of service',
        blockedAt: errorData.blocked_at,
        message: errorData.message
      };
    }
  }
  return { isBanned: false };
};

/**
 * Check if current user is banned and get ban details
 */
export const getBanStatus = async () => {
  try {
    const status = await checkAccountStatus();
    return {
      isBanned: status.is_blocked,
      reason: status.block_reason,
      blockedAt: status.blocked_at,
      email: status.email
    };
  } catch (error) {
    const banStatus = handleAccountStatusError(error);
    if (banStatus.isBanned) {
      return {
        isBanned: true,
        reason: banStatus.reason,
        blockedAt: banStatus.blockedAt,
        email: null
      };
    }
    throw error;
  }
};
