// ============================================
// DEALHUNT APP - API SERVICE (AXIOS)
// ============================================

import axios from 'axios';
import * as Device from 'expo-device';

import { API, ERROR_MESSAGES } from '../utils/constants';
import { getAuthToken, storeAuthToken, getHardwareId, storeHardwareId, clearAllAuthData } from './storage';
import { getFreshIdToken } from './firebase';

// --------------------------------------------
// CREATE AXIOS INSTANCE
// --------------------------------------------

const apiClient = axios.create({
  baseURL: API.BASE_URL,
  timeout: API.TIMEOUT,

  headers: {
    'Content-Type': 'application/json',
    'Accept': 'application/json',
  },
});

try {
  console.log('API Client initialized with base URL:', API.BASE_URL);
  if (!API.BASE_URL) {
    console.warn('⚠️  WARNING: API.BASE_URL is not configured. Backend calls will fail.');
  }
} catch (e) {
  console.error('Error initializing API client:', e);
}

const getReduxStore = () => {
  try {
    // Lazy import avoids require cycle: store -> authSlice -> api -> store
    const storeModule = require('../store/store');
    return storeModule?.store || storeModule?.default || null;
  } catch (error) {
    return null;
  }
};

const dispatchToStore = (action) => {
  const reduxStore = getReduxStore();
  if (!reduxStore?.dispatch) {
    return false;
  }

  reduxStore.dispatch(action);
  return true;
};

// --------------------------------------------
// GET OR CREATE HARDWARE ID
// --------------------------------------------

const getDeviceHardwareId = async () => {
  try {
    // Check if already stored
    let hardwareId = await getHardwareId();
    
    if (!hardwareId) {
      // Generate hardware ID from device info
      const deviceInfo = [
        Device.brand,
        Device.modelName,
        Device.osName,
        Device.osVersion,
        Device.deviceName,
      ].filter(Boolean).join('-');
      
      // Create a hash-like ID
      hardwareId = `${deviceInfo}-${Date.now()}`.replace(/\s+/g, '_');
      
      await storeHardwareId(hardwareId);
    }
    
    return hardwareId;
  } catch (error) {
    console.error('API: Error getting hardware ID:', error.message);
    return `fallback-${Date.now()}`;
  }
};

// --------------------------------------------
// REQUEST INTERCEPTOR
// Add auth token to all requests
// --------------------------------------------
// REPLACE the request interceptor with this:
apiClient.interceptors.request.use(
  async (config) => {
    try {
      const token = await getAuthToken();
      
      if (token) {
        config.headers.Authorization = `Bearer ${token}`;
      }
      
      // Add hardware ID to ALL auth endpoints
      if (config.url?.includes('/auth/')) {
        const hardwareId = await getDeviceHardwareId();
        config.headers['X-Hardware-ID'] = hardwareId;
      }
      
      return config;
    } catch (error) {
      return config;
    }
  },
  (error) => Promise.reject(error)
);

// REPLACE the response interceptor with this simpler version:
apiClient.interceptors.response.use(
  (response) => response,
  async (error) => {
    const originalRequest = error.config;
    const requestUrl = originalRequest?.url || '';
    const isAuthLoginOrSignup = requestUrl.includes('/auth/login') || requestUrl.includes('/auth/signup') || requestUrl.includes('/auth/signup-public');
    const isLogoutRequest = requestUrl.includes('/auth/logout');

    // Retry transient network failures once for idempotent GET requests.
    const requestMethod = String(originalRequest?.method || '').toLowerCase();
    const isNetworkFailure = !error.response && !!error.request;
    if (isNetworkFailure && requestMethod === 'get' && !originalRequest?._networkRetry) {
      originalRequest._networkRetry = true;
      return apiClient(originalRequest);
    }
    
    // Only retry ONCE on 401, no complex logic
    if (error.response?.status === 401 && !originalRequest._retry && !isAuthLoginOrSignup && !isLogoutRequest) {
      originalRequest._retry = true;
      
      try {
        // Simple token refresh
        const result = await getFreshIdToken(true);
        if (result.success) {
          await storeAuthToken(result.idToken);
          originalRequest.headers.Authorization = `Bearer ${result.idToken}`;
          return apiClient(originalRequest);
        }
      } catch (e) {
        // Silent fail, let error handler below process it
      }

      try {
        await clearAllAuthData();
      } catch (storageError) {
        console.error('API: Failed to clear auth data after 401:', storageError?.message || storageError);
      }

      const didDispatchSessionExpiry = dispatchToStore({
        type: 'auth/markSessionExpired',
        payload: {
          message: ERROR_MESSAGES.TOKEN_EXPIRED,
        },
      });

      if (!didDispatchSessionExpiry) {
        console.warn('API: Store unavailable while marking session expired.');
      }
    }
    
    return Promise.reject(handleApiError(error));
  }
);

// --------------------------------------------
// ERROR HANDLER
// --------------------------------------------

const handleApiError = (error) => {
  let errorMessage = ERROR_MESSAGES.UNKNOWN_ERROR;
  let statusCode = 0;
  let errorCode = null;
  const requestMethod = String(error.config?.method || 'GET').toUpperCase();
  const requestPath = error.config?.url || 'unknown-endpoint';
  const isBackgroundFeedEndpoint =
    requestPath.includes('/home/cross-platform') ||
    requestPath.includes('/home/featured') ||
    requestPath.includes('/search/trending');

  const normalizeMessage = (value, fallback) => {
    if (typeof value === 'string') return value;
    if (value && typeof value === 'object') {
      return value.message || value.detail || value.error || fallback;
    }
    return fallback;
  };

  const isDailySearchLimitEvent = () => {
    if (statusCode !== 429) return false;
    const lowerPath = String(requestPath || '').toLowerCase();
    return lowerPath.includes('/search/search');
  };
  
  if (error.response) {
    // Server responded with error
    statusCode = error.response.status;
    errorCode = error.response.data?.error?.code;
    
    switch (statusCode) {
      case 400:
        errorMessage = normalizeMessage(error.response.data?.detail, 'Invalid request.');
        break;
      case 401:
        errorMessage = ERROR_MESSAGES.TOKEN_EXPIRED;
        break;
      case 403:
        if (error.response.data?.error === 'account_blocked') {
          // Handle banned user - don't show generic error
          errorMessage = error.response.data?.message || 'Your account has been blocked.';
          // Store ban info for navigation
          const didDispatchBlocked = dispatchToStore({
            type: 'auth/accountBlocked',
            payload: {
              isBanned: true,
              reason: error.response.data?.reason || 'Violation of terms of service',
              blockedAt: error.response.data?.blocked_at,
              message: error.response.data?.message,
            },
          });

          if (!didDispatchBlocked) {
            console.warn('Failed to dispatch account blocked action: store unavailable.');
          }
        } else if (errorCode === 'DEVICE_LIMIT') {
          errorMessage = ERROR_MESSAGES.DEVICE_LIMIT;
        } else {
          errorMessage = 'Access denied.';
        }
        break;
      case 404:
        errorMessage = 'Resource not found.';
        break;
      case 409:
        errorMessage = normalizeMessage(error.response.data?.detail, 'Account already exists.');
        break;
      case 429: {
        const backendMessage = error.response.data?.detail || error.response.data?.message;
        const requestUrl = error.config?.url || '';

        // Keep signup-specific copy only for auth/signup endpoints.
        if (requestUrl.includes('/auth/signup-public')) {
          errorMessage = normalizeMessage(backendMessage, ERROR_MESSAGES.IP_LIMIT);
        } else {
          errorMessage = normalizeMessage(backendMessage, 'Too many requests. Please try again shortly.');
        }
        break;
      }
      case 500:
        errorMessage = ERROR_MESSAGES.SERVER_ERROR;
        break;
      default:
        errorMessage = normalizeMessage(error.response.data?.detail, ERROR_MESSAGES.SERVER_ERROR);
    }
  } else if (error.request) {
    // Request made but no response
    const networkLog = `API Error [Network] ${requestMethod} ${requestPath} (base: ${apiClient.defaults.baseURL})`;
    if (isBackgroundFeedEndpoint) {
      console.warn(networkLog);
    } else {
      console.error(networkLog);
    }
    errorMessage = ERROR_MESSAGES.NETWORK_ERROR;
  } else {
    // Something else happened
    console.error(`API Error [Unknown]:`, error.message);
    console.error('Error details:', error);
    errorMessage = error.message || ERROR_MESSAGES.UNKNOWN_ERROR;
  }
  
  if (isDailySearchLimitEvent()) {
    // This is an expected product-state event; UI should show it as alert/toast.
    // Avoid noisy global console errors.
    console.warn(`API Notice [${statusCode}] ${requestMethod} ${requestPath}:`, errorMessage);
  } else if (statusCode === 0 && isBackgroundFeedEndpoint) {
    console.warn(`API Error [${statusCode}] ${requestMethod} ${requestPath}:`, errorMessage);
  } else {
    console.error(`API Error [${statusCode}] ${requestMethod} ${requestPath}:`, errorMessage);
  }
  
  return {
    success: false,
    error: errorMessage,
    statusCode,
    errorCode,
    data: error.response?.data || null,
  };
};

// --------------------------------------------
// API METHODS
// --------------------------------------------

/**
 * GET request
 */
export const get = async (endpoint, params = {}) => {
  try {
    const response = await apiClient.get(endpoint, { params });
    return {
      success: true,
      data: response.data,
      status: response.status,
    };
  } catch (error) {
    return error;
  }
};

/**
 * POST request
 */
export const post = async (endpoint, data = {}) => {
  try {
    const response = await apiClient.post(endpoint, data);
    return {
      success: true,
      data: response.data,
      status: response.status,
    };
  } catch (error) {
    return error;
  }
};

/**
 * PUT request
 */
export const put = async (endpoint, data = {}) => {
  try {
    const response = await apiClient.put(endpoint, data);
    return {
      success: true,
      data: response.data,
      status: response.status,
    };
  } catch (error) {
    return error;
  }
};

/**
 * DELETE request
 */
export const del = async (endpoint) => {
  try {
    const response = await apiClient.delete(endpoint);
    return {
      success: true,
      data: response.data,
      status: response.status,
    };
  } catch (error) {
    return error;
  }
};

// --------------------------------------------
// AUTH API ENDPOINTS
// --------------------------------------------

export const authAPI = {
  /**
   * Get current user profile (auto-creates on first call)
   */
  getMe: async () => {
    return await get(API.ENDPOINTS.ME);
  },

  /**
   * Update current user profile fields
   */
  updateMe: async (payload = {}) => {
    return await put(API.ENDPOINTS.ME, payload);
  },
  
  /**
   * Get user statistics
   */
  getStats: async () => {
    return await get(API.ENDPOINTS.ME_STATS);
  },

  /**
   * Reset today's search usage counters (development only)
   */
  resetSearchUsage: async () => {
    return await post(API.ENDPOINTS.ME_STATS_RESET_SEARCHES);
  },
  
  /**
   * Verify referral code
   */
  verifyReferralCode: async (referralCode) => {
    return await get(API.ENDPOINTS.VERIFY_REFERRAL, { referral_code: referralCode });
  },
  
  /**
   * Logout (server-side)
   */
  logout: async () => {
    return await post(API.ENDPOINTS.LOGOUT);
  },
  
  /**
   * Check token status
   */
  checkTokenStatus: async () => {
    return await get(API.ENDPOINTS.TOKEN_STATUS);
  },
};

// --------------------------------------------
// EXPORT
// --------------------------------------------

export default {
  get,
  post,
  put,
  del,
  authAPI,
  getDeviceHardwareId,
};