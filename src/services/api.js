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

apiClient.interceptors.request.use(
  async (config) => {
    try {
      // Get stored Firebase token
      const token = await getAuthToken();
      
      // Log token status
      console.log(`API Request: ${config.method?.toUpperCase()} ${config.url}`);
      console.log(`  Token present: ${token ? 'YES' : 'NO (⚠️ AUTH TOKEN MISSING)'}`);
      console.log(`  Full URL: ${apiClient.defaults.baseURL}${config.url}`);
      
      if (token) {
        config.headers.Authorization = `Bearer ${token}`;
        console.log(`  Authorization header set: Bearer ${token.substring(0, 20)}...`);
      } else {
        console.warn('  ⚠️ No token stored! User may not be authenticated');
      }
      
      // Add hardware ID to relevant requests (signup, login)
      if (config.url?.includes('/auth/')) {
        const hardwareId = await getDeviceHardwareId();
        config.headers['X-Hardware-ID'] = hardwareId;
        console.log(`  Hardware ID: ${hardwareId}`);
      }
      
      return config;
    } catch (error) {
      console.error('API: Request interceptor error:', error.message);
      return config;
    }
  },
  (error) => {
    console.error('API: Request error:', error.message);
    return Promise.reject(error);
  }
);

// --------------------------------------------
// RESPONSE INTERCEPTOR
// Handle token refresh on 401
// --------------------------------------------

apiClient.interceptors.response.use(
  (response) => {
    // Log success (development only)
    console.log(`API Response: ${response.status} ${response.config.url}`);
    return response;
  },
  async (error) => {
    const originalRequest = error.config;
    
    // Handle 401 Unauthorized (token expired)
    if (error.response?.status === 401 && !originalRequest._retry) {
      originalRequest._retry = true;
      
      console.log('API: Token expired, attempting refresh...');
      
      try {
        // Get fresh token from Firebase
        const result = await getFreshIdToken(true);
        
        if (result.success && result.idToken) {
          // Store new token
          await storeAuthToken(result.idToken);
          
          // Update header and retry
          originalRequest.headers.Authorization = `Bearer ${result.idToken}`;
          
          console.log('API: Token refreshed, retrying request...');
          return apiClient(originalRequest);
        }
      } catch (refreshError) {
        console.error('API: Token refresh failed:', refreshError.message);
      }
    }
    
    // Handle other errors
    const errorResponse = handleApiError(error);
    return Promise.reject(errorResponse);
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
      case 429:
        errorMessage = ERROR_MESSAGES.IP_LIMIT;
        break;
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