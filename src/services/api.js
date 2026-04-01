// ============================================
// DEALHUNT APP - API SERVICE (AXIOS)
// ============================================

import axios from 'axios';
import * as Device from 'expo-device';

import { API, ERROR_MESSAGES } from '../utils/constants';
import { getAuthToken, storeAuthToken, getHardwareId, storeHardwareId } from './storage';
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

console.log('API Client initialized with base URL:', API.BASE_URL);

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
    
    // Only retry ONCE on 401, no complex logic
    if (error.response?.status === 401 && !originalRequest._retry) {
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
  
  if (error.response) {
    // Server responded with error
    statusCode = error.response.status;
    errorCode = error.response.data?.error?.code;
    
    switch (statusCode) {
      case 400:
        errorMessage = error.response.data?.detail || 'Invalid request.';
        break;
      case 401:
        errorMessage = ERROR_MESSAGES.TOKEN_EXPIRED;
        break;
      case 403:
        if (errorCode === 'DEVICE_LIMIT') {
          errorMessage = ERROR_MESSAGES.DEVICE_LIMIT;
        } else {
          errorMessage = 'Access denied.';
        }
        break;
      case 404:
        errorMessage = 'Resource not found.';
        break;
      case 409:
        errorMessage = error.response.data?.detail || 'Account already exists.';
        break;
      case 429: {
        const backendMessage = error.response.data?.detail || error.response.data?.message;
        const requestUrl = error.config?.url || '';

        // Keep signup-specific copy only for auth/signup endpoints.
        if (requestUrl.includes('/auth/signup-public')) {
          errorMessage = backendMessage || ERROR_MESSAGES.IP_LIMIT;
        } else {
          errorMessage = backendMessage || 'Too many requests. Please try again shortly.';
        }
        break;
      }
      case 500:
        errorMessage = ERROR_MESSAGES.SERVER_ERROR;
        break;
      default:
        errorMessage = error.response.data?.detail || ERROR_MESSAGES.SERVER_ERROR;
    }
  } else if (error.request) {
    // Request made but no response
    console.error(`API Error [Network]: Request to ${error.config?.url} made but no response received`);
    console.error('Base URL:', apiClient.defaults.baseURL);
    console.error('Request details:', {
      method: error.config?.method,
      url: error.config?.url,
      fullUrl: error.config?.baseURL + error.config?.url,
    });
    errorMessage = ERROR_MESSAGES.NETWORK_ERROR;
  } else {
    // Something else happened
    console.error(`API Error [Unknown]:`, error.message);
    console.error('Error details:', error);
    errorMessage = error.message || ERROR_MESSAGES.UNKNOWN_ERROR;
  }
  
  console.error(`API Error [${statusCode}]:`, errorMessage);
  
  return {
    success: false,
    error: errorMessage,
    statusCode,
    errorCode,
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
   * Get user statistics
   */
  getStats: async () => {
    return await get(API.ENDPOINTS.ME_STATS);
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