// ============================================
// DEALHUNT APP - SUBSCRIPTION API SERVICE
// Part 5: Subscription & Payments (Demo Version)
// ============================================

import { get, post, del } from './api';
import { API } from '../utils/constants';

/**
 * Subscription API Service
 * Handles all subscription-related backend communication
 */
export const subscriptionAPI = {
  /**
   * Get available subscription plans
   * @returns {Promise<{success: boolean, data?: Array, error?: string}>}
   */
  getPlans: async () => {
    try {
      const response = await get(API.ENDPOINTS.SUBSCRIPTION_PLANS);
      return response;
    } catch (error) {
      console.error('[SubscriptionAPI] getPlans error:', error);
      return {
        success: false,
        error: error.message || 'Failed to fetch plans',
      };
    }
  },

  /**
   * Get current user's subscription status
   * @returns {Promise<{success: boolean, data?: Object, error?: string}>}
   */
  getStatus: async () => {
    try {
      const response = await get(API.ENDPOINTS.SUBSCRIPTION_STATUS);
      return response;
    } catch (error) {
      console.error('[SubscriptionAPI] getStatus error:', error);
      return {
        success: false,
        error: error.message || 'Failed to fetch subscription status',
      };
    }
  },

  /**
   * Get subscription payment history
   * @returns {Promise<{success: boolean, data?: Array, error?: string}>}
   */
  getHistory: async (limit = 100) => {
    try {
      const response = await get(API.ENDPOINTS.SUBSCRIPTION_HISTORY, { limit });
      return response;
    } catch (error) {
      console.error('[SubscriptionAPI] getHistory error:', error);
      return {
        success: false,
        error: error.message || 'Failed to fetch payment history',
      };
    }
  },

  /**
   * Create a Razorpay order for subscription
   * @param {string} planId - The plan to subscribe to ('pro' or 'premium')
   * @returns {Promise<{success: boolean, data?: Object, error?: string}>}
   */
  createOrder: async (planId) => {
    try {
      const response = await post(API.ENDPOINTS.SUBSCRIPTION_CREATE_ORDER, {
        plan_id: planId,
        platform: 'web',
      });

      if (!response?.success) {
        return response;
      }

      // Normalize shape for UI layer compatibility.
      return {
        ...response,
        data: {
          ...response.data,
          order_id: response.data?.order_id || response.data?.id || null,
        },
      };
    } catch (error) {
      console.error('[SubscriptionAPI] createOrder error:', error);
      return {
        success: false,
        error: error.message || 'Failed to create order',
      };
    }
  },

  /**
   * Verify payment and activate subscription
   * @param {Object} paymentData - Payment verification data
   * @param {string} paymentData.order_id - Razorpay order ID
   * @param {string} paymentData.payment_id - Razorpay payment ID
   * @param {string} paymentData.signature - Razorpay signature for verification
   * @param {string} paymentData.plan_id - Plan that was purchased
   * @returns {Promise<{success: boolean, data?: Object, error?: string}>}
   */
  verifyPayment: async (paymentData) => {
    try {
      const response = await post(API.ENDPOINTS.SUBSCRIPTION_VERIFY_PAYMENT, {
        razorpay_order_id: paymentData.order_id,
        razorpay_payment_id: paymentData.payment_id,
        razorpay_signature: paymentData.signature,
      });
      return response;
    } catch (error) {
      console.error('[SubscriptionAPI] verifyPayment error:', error);
      return {
        success: false,
        error: error.message || 'Failed to verify payment',
      };
    }
  },

  /**
   * Cancel subscription (stops auto-renewal)
   * @returns {Promise<{success: boolean, data?: Object, error?: string}>}
   */
  cancelSubscription: async () => {
    try {
      const response = await post(API.ENDPOINTS.SUBSCRIPTION_CANCEL, {});
      return response;
    } catch (error) {
      console.error('[SubscriptionAPI] cancelSubscription error:', error);
      return {
        success: false,
        error: error.message || 'Failed to cancel subscription',
      };
    }
  },

  /**
   * Delete a single payment history item in development
   * @param {string} transactionId
   */
  deleteHistoryItem: async (transactionId) => {
    try {
      const response = await del(`${API.ENDPOINTS.SUBSCRIPTION_HISTORY}/${transactionId}`);
      return response;
    } catch (error) {
      console.error('[SubscriptionAPI] deleteHistoryItem error:', error);
      return {
        success: false,
        error: error.message || 'Failed to delete transaction',
      };
    }
  },

  /**
   * Clear all demo payment history and reset the demo subscription state
   */
  clearHistory: async () => {
    try {
      const response = await del(API.ENDPOINTS.SUBSCRIPTION_HISTORY);
      return response;
    } catch (error) {
      console.error('[SubscriptionAPI] clearHistory error:', error);
      return {
        success: false,
        error: error.message || 'Failed to clear payment history',
      };
    }
  },
};

export default subscriptionAPI;