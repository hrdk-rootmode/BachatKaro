// ============================================
// DEALHUNT APP - SECURE STORAGE SERVICE
// ============================================

import * as SecureStore from 'expo-secure-store';
import { STORAGE_KEYS } from '../utils/constants';

// --------------------------------------------
// GENERIC SECURE STORAGE FUNCTIONS
// --------------------------------------------

/**
 * Store data securely (encrypted)
 * @param {string} key - Storage key
 * @param {string} value - Value to store (must be string)
 * @returns {Promise<boolean>} - Success status
 */
export const setSecureItem = async (key, value) => {
  try {
    if (!key || value === undefined || value === null) {
      console.warn('Storage: Invalid key or value');
      return false;
    }

    // Convert to string if not already
    const stringValue = typeof value === 'string' ? value : JSON.stringify(value);
    
    await SecureStore.setItemAsync(key, stringValue);
    return true;
  } catch (error) {
    console.error('Storage: Error storing data:', error.message);
    return false;
  }
};

/**
 * Get data from secure storage
 * @param {string} key - Storage key
 * @returns {Promise<string|null>} - Stored value or null
 */
export const getSecureItem = async (key) => {
  try {
    if (!key) {
      console.warn('Storage: Invalid key');
      return null;
    }

    const value = await SecureStore.getItemAsync(key);
    return value;
  } catch (error) {
    console.error('Storage: Error retrieving data:', error.message);
    return null;
  }
};

/**
 * Remove data from secure storage
 * @param {string} key - Storage key
 * @returns {Promise<boolean>} - Success status
 */
export const removeSecureItem = async (key) => {
  try {
    if (!key) {
      console.warn('Storage: Invalid key');
      return false;
    }

    await SecureStore.deleteItemAsync(key);
    return true;
  } catch (error) {
    console.error('Storage: Error removing data:', error.message);
    return false;
  }
};

// --------------------------------------------
// AUTH TOKEN HELPERS
// --------------------------------------------

/**
 * Store Firebase auth token
 */
export const storeAuthToken = async (token) => {
  return await setSecureItem(STORAGE_KEYS.AUTH_TOKEN, token);
};

/**
 * Get stored auth token
 */
export const getAuthToken = async () => {
  return await getSecureItem(STORAGE_KEYS.AUTH_TOKEN);
};

/**
 * Remove auth token
 */
export const removeAuthToken = async () => {
  return await removeSecureItem(STORAGE_KEYS.AUTH_TOKEN);
};

// --------------------------------------------
// USER DATA HELPERS
// --------------------------------------------

/**
 * Store user data
 * @param {Object} userData - User data object
 */
export const storeUserData = async (userData) => {
  try {
    const jsonString = JSON.stringify(userData);
    return await setSecureItem(STORAGE_KEYS.USER_DATA, jsonString);
  } catch (error) {
    console.error('Storage: Error storing user data:', error.message);
    return false;
  }
};

/**
 * Get stored user data
 * @returns {Promise<Object|null>} - User data object or null
 */
export const getUserData = async () => {
  try {
    const jsonString = await getSecureItem(STORAGE_KEYS.USER_DATA);
    if (!jsonString) return null;
    return JSON.parse(jsonString);
  } catch (error) {
    console.error('Storage: Error parsing user data:', error.message);
    return null;
  }
};

/**
 * Remove user data
 */
export const removeUserData = async () => {
  return await removeSecureItem(STORAGE_KEYS.USER_DATA);
};

// --------------------------------------------
// FIREBASE UID HELPERS
// --------------------------------------------

/**
 * Store Firebase UID
 */
export const storeFirebaseUid = async (uid) => {
  return await setSecureItem(STORAGE_KEYS.FIREBASE_UID, uid);
};

/**
 * Get stored Firebase UID
 */
export const getFirebaseUid = async () => {
  return await getSecureItem(STORAGE_KEYS.FIREBASE_UID);
};

// --------------------------------------------
// HARDWARE ID HELPERS
// --------------------------------------------

/**
 * Store device hardware ID
 */
export const storeHardwareId = async (hardwareId) => {
  return await setSecureItem(STORAGE_KEYS.HARDWARE_ID, hardwareId);
};

/**
 * Get stored hardware ID
 */
export const getHardwareId = async () => {
  return await getSecureItem(STORAGE_KEYS.HARDWARE_ID);
};

// --------------------------------------------
// CLEAR ALL AUTH DATA
// --------------------------------------------

/**
 * Clear all authentication related data
 * Used on logout
 */
export const clearAllAuthData = async () => {
  try {
    await removeAuthToken();
    await removeUserData();
    await removeSecureItem(STORAGE_KEYS.FIREBASE_UID);
    // Keep HARDWARE_ID - it's device specific, not user specific
    return true;
  } catch (error) {
    console.error('Storage: Error clearing auth data:', error.message);
    return false;
  }
};

// --------------------------------------------
// CHECK IF USER IS LOGGED IN
// --------------------------------------------

/**
 * Quick check if user has stored credentials
 * @returns {Promise<boolean>}
 */
export const hasStoredCredentials = async () => {
  try {
    const token = await getAuthToken();
    const userData = await getUserData();
    return !!(token && userData);
  } catch (error) {
    return false;
  }
};

export default {
  // Generic
  setSecureItem,
  getSecureItem,
  removeSecureItem,
  
  // Auth Token
  storeAuthToken,
  getAuthToken,
  removeAuthToken,
  
  // User Data
  storeUserData,
  getUserData,
  removeUserData,
  
  // Firebase
  storeFirebaseUid,
  getFirebaseUid,
  
  // Hardware
  storeHardwareId,
  getHardwareId,
  
  // Utilities
  clearAllAuthData,
  hasStoredCredentials,
};