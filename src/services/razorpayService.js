// ============================================
// DEALHUNT APP - RAZORPAY SERVICE (MOCK VERSION)
// Part 5: Demo Payment Flow for College Presentation
// ============================================
// 
// This is a MOCK implementation for demo purposes.
// It simulates the Razorpay checkout flow without 
// requiring native modules, making it fully compatible
// with Expo Go.
//
// For production, replace with real Razorpay integration.
// ============================================

import { RAZORPAY } from '../utils/constants';

/**
 * Generate mock payment response
 * Simulates successful Razorpay payment response
 */
const generateMockPayment = (orderId) => {
  const timestamp = Date.now();
  return {
    razorpay_payment_id: `pay_demo_${timestamp}`,
    razorpay_order_id: orderId,
    razorpay_signature: `sig_demo_${timestamp}_mock`,
  };
};

/**
 * Process mock payment
 * This simulates the payment flow for demo purposes
 * 
 * @param {Object} orderData - Order data from backend
 * @param {string} orderData.order_id - Order ID
 * @param {number} orderData.amount - Amount in paise
 * @param {string} orderData.currency - Currency code
 * @param {Object} userInfo - User information
 * @param {string} planName - Name of the plan
 * @param {boolean} simulateSuccess - Whether to simulate success (default: true)
 * 
 * @returns {Promise<Object>} Mock payment response
 */
export const processMockPayment = async (orderData, userInfo, planName, simulateSuccess = true) => {
  console.log('[RazorpayService] Processing mock payment:', {
    order_id: orderData.order_id,
    amount: orderData.amount,
    plan: planName,
  });

  // Simulate processing delay (makes demo look realistic)
  await new Promise(resolve => setTimeout(resolve, 1500));

  if (simulateSuccess) {
    const mockResponse = generateMockPayment(orderData.order_id);
    console.log('[RazorpayService] Mock payment success:', mockResponse);
    return mockResponse;
  } else {
    throw {
      code: 'PAYMENT_FAILED',
      description: 'Simulated payment failure for testing',
    };
  }
};

/**
 * Validate payment response structure
 * @param {Object} response - Payment response to validate
 * @returns {boolean} Whether the response has required fields
 */
export const validatePaymentResponse = (response) => {
  if (!response) return false;
  
  const hasPaymentId = !!response.razorpay_payment_id;
  const hasOrderId = !!response.razorpay_order_id;
  const hasSignature = !!response.razorpay_signature;
  
  return hasPaymentId && hasOrderId && hasSignature;
};

/**
 * Format payment error for user display
 * @param {Object} error - Error object
 * @returns {string} User-friendly error message
 */
export const formatPaymentError = (error) => {
  if (!error) return 'Payment failed. Please try again.';
  
  const code = error.code || error.error?.code;
  const description = error.description || error.error?.description || error.message;
  
  switch (code) {
    case 'PAYMENT_CANCELLED':
      return 'Payment was cancelled. No charges were made.';
    case 'BAD_REQUEST_ERROR':
      return 'Invalid payment request. Please try again.';
    case 'GATEWAY_ERROR':
      return 'Payment gateway error. Please try again later.';
    case 'SERVER_ERROR':
      return 'Server error. Please try again later.';
    case 'NETWORK_ERROR':
      return 'Network error. Please check your connection.';
    case 'PAYMENT_FAILED':
      return description || 'Payment failed. Please try again.';
    default:
      return description || 'Payment failed. Please try again.';
  }
};

/**
 * Check if error is a user cancellation
 * @param {Object} error - Error object
 * @returns {boolean} Whether user cancelled the payment
 */
export const isPaymentCancelled = (error) => {
  const code = error?.code || error?.error?.code;
  return code === 'PAYMENT_CANCELLED' || code === 0;
};

/**
 * Get Razorpay/Payment service status
 * Useful for UI to show appropriate messaging
 */
export const getPaymentServiceStatus = () => {
  return {
    isNativeAvailable: false, // Always false for mock version
    mode: 'DEMO',
    isDemo: true,
    message: 'Demo mode (Simulated payments)',
    testCard: RAZORPAY.TEST_CARD,
  };
};

/**
 * Format amount from paise to rupees display string
 * @param {number} amountInPaise - Amount in paise
 * @returns {string} Formatted amount string (e.g., "₹99.00")
 */
export const formatAmountDisplay = (amountInPaise) => {
  const rupees = (amountInPaise / 100).toFixed(2);
  return `₹${rupees}`;
};

export default {
  processMockPayment,
  validatePaymentResponse,
  formatPaymentError,
  isPaymentCancelled,
  getPaymentServiceStatus,
  formatAmountDisplay,
};