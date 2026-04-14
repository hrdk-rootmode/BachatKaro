// ============================================
// DEALHUNT APP - SUBSCRIPTION REDUX SLICE
// Part 5: Subscription & Payment State (Demo Version)
// ============================================

import { createSlice, createAsyncThunk } from '@reduxjs/toolkit';
import { subscriptionAPI } from '../services/subscriptionApi';
import {
  processMockPayment,
  validatePaymentResponse,
  formatPaymentError,
  isPaymentCancelled,
} from '../services/razorpayService';
import { refreshUserData } from './authSlice';
import { APP } from '../utils/constants';

// --------------------------------------------
// INITIAL STATE
// --------------------------------------------

const initialState = {
  // Available plans from backend (or fallback to local config)
  plans: [],
  plansLoaded: false,
  
  // Current user subscription status
  currentSubscription: null,
  
  // Payment flow state
  activeOrder: null,
  paymentInProgress: false,
  selectedPlanId: null,
  
  // Payment history
  paymentHistory: [],
  isDeletingHistoryItem: false,
  isClearingHistory: false,
  historyActionError: null,

  // Payment details for realistic transaction tracking in UI/debug
  paymentDetails: {
    lastAttempt: null,
    lastSuccess: null,
    lastFailure: null,
    attemptsCount: 0,
  },
  
  // Payment success modal state (for subscription purchase celebration)
  paymentStatus: {
    success: false,
    dismissed: false,
    planType: null,
    durationMonths: 1,
    amount: 0,
    transactionId: null,
  },
  
  // UI state for upgrade prompts
  showUpgradePrompt: false,
  upgradeReason: null,
  
  // Loading states
  isLoading: false,
  isCreatingOrder: false,
  isVerifying: false,
  isCancelling: false,
  
  // Error handling
  error: null,
  paymentError: null,
};

const fallbackPlans = Object.values(APP.PLANS);

const normalizePlanRecord = (plan) => {
  const id = String(plan?.plan_id || plan?.id || '').toLowerCase();
  const limits = plan?.limits || {};
  const features = plan?.features || {};

  const searchesPerDay =
    Number(limits?.searches_per_day ?? features?.daily_searches ?? plan?.searches_per_day ?? 0);
  const watchlistLimit =
    Number(limits?.watchlist_limit ?? features?.watchlist_limit ?? plan?.watchlist_limit ?? 0);

  const rawPrice = plan?.price ?? plan?.price_inr ?? 0;
  const normalizedPrice = Number(rawPrice);

  return {
    id,
    name: plan?.name || id.toUpperCase(),
    searches_per_day: Number.isFinite(searchesPerDay) ? searchesPerDay : 0,
    watchlist_limit: Number.isFinite(watchlistLimit) ? watchlistLimit : 0,
    price: Number.isFinite(normalizedPrice) ? normalizedPrice : 0,
    interval: id === 'free' ? null : 'month',
    duration_days: Number(plan?.duration_days || 30),
    popular: Boolean(plan?.popular),
    features,
    limits,
  };
};

const normalizePlans = (plans) => {
  if (!Array.isArray(plans)) {
    return fallbackPlans;
  }

  const normalized = plans
    .map(normalizePlanRecord)
    .filter((p) => Boolean(p.id));

  if (!normalized.length) {
    return fallbackPlans;
  }

  const byId = {};
  normalized.forEach((plan) => {
    byId[plan.id] = plan;
  });

  if (!byId.free) {
    byId.free = APP.PLANS.FREE;
  }

  const orderedIds = ['free', 'pro', 'premium'];
  const ordered = orderedIds
    .filter((id) => byId[id])
    .map((id) => byId[id]);

  const remaining = Object.values(byId)
    .filter((plan) => !orderedIds.includes(plan.id))
    .sort((a, b) => (a.price || 0) - (b.price || 0));

  return [...ordered, ...remaining];
};

// --------------------------------------------
// ASYNC THUNKS
// --------------------------------------------

/**
 * Fetch available subscription plans
 */
export const fetchPlans = createAsyncThunk(
  'subscription/fetchPlans',
  async (_, { rejectWithValue }) => {
    try {
      const result = await subscriptionAPI.getPlans();
      
      if (!result.success) {
        // Fallback to local config if backend fails
        console.warn('[SubscriptionSlice] Using local plan config as fallback');
        return fallbackPlans;
      }

      const rawPlans = Array.isArray(result.data)
        ? result.data
        : Array.isArray(result.data?.plans)
          ? result.data.plans
          : [];

      return normalizePlans(rawPlans);
    } catch (error) {
      console.error('[SubscriptionSlice] fetchPlans error:', error);
      // Return local fallback
      return fallbackPlans;
    }
  }
);

/**
 * Fetch current subscription status
 */
export const fetchSubscriptionStatus = createAsyncThunk(
  'subscription/fetchStatus',
  async (_, { rejectWithValue }) => {
    try {
      const result = await subscriptionAPI.getStatus();
      
      if (!result.success) {
        return rejectWithValue(result.error || 'Failed to fetch status');
      }
      
      return result.data;
    } catch (error) {
      console.error('[SubscriptionSlice] fetchStatus error:', error);
      return rejectWithValue(error.message);
    }
  }
);

/**
 * Fetch payment history
 */
export const fetchPaymentHistory = createAsyncThunk(
  'subscription/fetchHistory',
  async ({ limit = 100 } = {}, { rejectWithValue }) => {
    try {
      const result = await subscriptionAPI.getHistory(limit);
      
      if (!result.success) {
        return rejectWithValue(result.error || 'Failed to fetch history');
      }
      
      return result.data;
    } catch (error) {
      console.error('[SubscriptionSlice] fetchHistory error:', error);
      return rejectWithValue(error.message);
    }
  }
);

/**
 * Delete a single payment history item in development
 */
export const deletePaymentHistoryItem = createAsyncThunk(
  'subscription/deleteHistoryItem',
  async ({ transactionId }, { rejectWithValue }) => {
    try {
      const result = await subscriptionAPI.deleteHistoryItem(transactionId);

      if (!result.success) {
        return rejectWithValue(result.error || 'Failed to delete transaction');
      }

      return { transactionId };
    } catch (error) {
      console.error('[SubscriptionSlice] deleteHistoryItem error:', error);
      return rejectWithValue(error.message || 'Failed to delete transaction');
    }
  }
);

/**
 * Clear all payment history and reset demo subscription state
 */
export const clearPaymentHistory = createAsyncThunk(
  'subscription/clearHistory',
  async (_, { dispatch, rejectWithValue }) => {
    try {
      const result = await subscriptionAPI.clearHistory();

      if (!result.success) {
        return rejectWithValue(result.error || 'Failed to clear history');
      }

      await dispatch(refreshUserData());

      return result.data || { deleted_count: 0 };
    } catch (error) {
      console.error('[SubscriptionSlice] clearHistory error:', error);
      return rejectWithValue(error.message || 'Failed to clear history');
    }
  }
);

/**
 * Create order and process mock payment
 * For demo: calls backend create-order, then simulates payment
 */
export const createOrderAndPay = createAsyncThunk(
  'subscription/createOrderAndPay',
  async ({ planId, userInfo, simulateSuccess = true }, { dispatch, rejectWithValue }) => {
    try {
      // Step 1: Create order on backend
      console.log('[SubscriptionSlice] Creating order for plan:', planId);
      const orderResult = await subscriptionAPI.createOrder(planId);
      
      if (!orderResult.success) {
        return rejectWithValue(orderResult.error || 'Failed to create order');
      }
      
      const orderData = orderResult.data;
      const normalizedOrderId = orderData?.order_id || orderData?.id;
      if (!normalizedOrderId) {
        return rejectWithValue('Order ID missing from create-order response');
      }
      console.log('[SubscriptionSlice] Order created:', normalizedOrderId);
      
      // Step 2: Get plan name for display
      const planNames = { pro: 'Pro', premium: 'Premium' };
      const planName = planNames[planId] || planId;
      
      // Step 3: Process mock payment (simulated checkout)
      const paymentResponse = await processMockPayment(
        { ...orderData, order_id: normalizedOrderId },
        userInfo,
        planName,
        simulateSuccess
      );
      
      // Step 4: Validate payment response
      if (!validatePaymentResponse(paymentResponse)) {
        return rejectWithValue('Invalid payment response');
      }
      
      // Step 5: Return order + payment data for verification
      return {
        order: { ...orderData, order_id: normalizedOrderId },
        payment: paymentResponse,
        planId,
      };
    } catch (error) {
      console.error('[SubscriptionSlice] createOrderAndPay error:', error);
      
      if (isPaymentCancelled(error)) {
        return rejectWithValue('PAYMENT_CANCELLED');
      }
      
      return rejectWithValue(formatPaymentError(error));
    }
  }
);

/**
 * Verify payment and activate subscription
 */
export const verifyPayment = createAsyncThunk(
  'subscription/verifyPayment',
  async (paymentData, { dispatch, rejectWithValue }) => {
    try {
      console.log('[SubscriptionSlice] Verifying payment:', paymentData.payment.razorpay_payment_id);
      
      const verifyResult = await subscriptionAPI.verifyPayment({
        order_id: paymentData.payment.razorpay_order_id,
        payment_id: paymentData.payment.razorpay_payment_id,
        signature: paymentData.payment.razorpay_signature,
        plan_id: paymentData.planId,
      });
      
      if (!verifyResult.success) {
        return rejectWithValue(verifyResult.error || 'Payment verification failed');
      }
      
      // Refresh user data to get updated plan
      console.log('[SubscriptionSlice] Payment verified, refreshing user data...');
      await dispatch(refreshUserData());
      
      return verifyResult.data;
    } catch (error) {
      console.error('[SubscriptionSlice] verifyPayment error:', error);
      return rejectWithValue(error.message || 'Verification failed');
    }
  }
);

/**
 * Cancel subscription (stops auto-renewal)
 */
export const cancelSubscription = createAsyncThunk(
  'subscription/cancel',
  async (_, { dispatch, rejectWithValue }) => {
    try {
      const result = await subscriptionAPI.cancelSubscription();
      
      if (!result.success) {
        return rejectWithValue(result.error || 'Failed to cancel subscription');
      }
      
      // Refresh user data
      await dispatch(refreshUserData());
      
      return result.data;
    } catch (error) {
      console.error('[SubscriptionSlice] cancel error:', error);
      return rejectWithValue(error.message);
    }
  }
);

/**
 * Complete subscription flow: create order → mock payment → verify
 * This is the main thunk to call from UI
 */
export const subscribeToPlan = createAsyncThunk(
  'subscription/subscribeToPlan',
  async ({ planId, userInfo }, { dispatch, rejectWithValue }) => {
    try {
      // Step 1: Create order and process mock payment
      const orderResult = await dispatch(
        createOrderAndPay({ planId, userInfo, simulateSuccess: true })
      ).unwrap();
      
      // Step 2: Verify payment with backend
      const verifyResult = await dispatch(verifyPayment(orderResult)).unwrap();

      const planNameMap = {
        pro: APP.PLANS.PRO.name,
        premium: APP.PLANS.PREMIUM.name,
      };
      const planPriceMap = {
        pro: APP.PLANS.PRO.price,
        premium: APP.PLANS.PREMIUM.price,
      };

      const normalizedPlanId = String(planId || '').toLowerCase();
      
      return {
        success: true,
        planId,
        subscription: verifyResult,
        paymentStatus: {
          planType: planNameMap[normalizedPlanId] || normalizedPlanId || 'Pro',
          durationMonths: 1,
          amount: Number(planPriceMap[normalizedPlanId] || 0),
          transactionId:
            verifyResult?.transaction_id ||
            orderResult?.payment?.razorpay_payment_id ||
            null,
        },
      };
    } catch (error) {
      console.error('[SubscriptionSlice] subscribeToPlan error:', error);
      return rejectWithValue(error);
    }
  }
);

// --------------------------------------------
// SUBSCRIPTION SLICE
// --------------------------------------------

const subscriptionSlice = createSlice({
  name: 'subscription',
  initialState,
  
  reducers: {
    // Set payment success modal state (for subscription purchase celebration)
    setPaymentSuccess: (state, action) => {
      const { planType, durationMonths, amount, transactionId } = action.payload;
      state.paymentStatus = {
        success: true,
        dismissed: false,
        planType: planType || 'pro',
        durationMonths: durationMonths || 1,
        amount: amount || 0,
        transactionId: transactionId || null,
      };
    },

    // Clear payment success modal state
    clearPaymentStatus: (state) => {
      state.paymentStatus = {
        success: false,
        dismissed: true,
        planType: null,
        durationMonths: 1,
        amount: 0,
        transactionId: null,
      };
    },

    // Dismiss payment success modal (mark as dismissed but keep data)
    dismissPaymentSuccess: (state) => {
      state.paymentStatus.dismissed = true;
    },

    // Clear error states
    clearError: (state) => {
      state.error = null;
      state.paymentError = null;
    },

    // Clear only payment detail snapshots while preserving plans/subscription state
    clearPaymentDetails: (state) => {
      state.paymentDetails = {
        lastAttempt: null,
        lastSuccess: null,
        lastFailure: null,
        attemptsCount: 0,
      };
    },
    
    // Show upgrade prompt with reason
    showUpgradePrompt: (state, action) => {
      state.showUpgradePrompt = true;
      state.upgradeReason = action.payload?.reason || null;
    },
    
    // Hide upgrade prompt
    hideUpgradePrompt: (state) => {
      state.showUpgradePrompt = false;
      state.upgradeReason = null;
    },
    
    // Set selected plan (for pre-selection on PlansScreen)
    setSelectedPlan: (state, action) => {
      state.selectedPlanId = action.payload;
    },
    
    // Clear selected plan
    clearSelectedPlan: (state) => {
      state.selectedPlanId = null;
    },

    clearHistoryActionError: (state) => {
      state.historyActionError = null;
    },
    
    // Reset payment flow state
    resetPaymentFlow: (state) => {
      state.activeOrder = null;
      state.paymentInProgress = false;
      state.paymentError = null;
    },
    
    // Reset entire subscription state (for logout)
    resetSubscription: () => initialState,
  },
  
  extraReducers: (builder) => {
    // --------------------------------------------
    // FETCH PLANS
    // --------------------------------------------
    builder.addCase(fetchPlans.pending, (state) => {
      state.isLoading = true;
      state.error = null;
    });
    
    builder.addCase(fetchPlans.fulfilled, (state, action) => {
      state.isLoading = false;
      state.plans = action.payload;
      state.plansLoaded = true;
    });
    
    builder.addCase(fetchPlans.rejected, (state, action) => {
      state.isLoading = false;
      state.error = action.payload;
      state.plansLoaded = true;
    });
    
    // --------------------------------------------
    // FETCH STATUS
    // --------------------------------------------
    builder.addCase(fetchSubscriptionStatus.pending, (state) => {
      state.isLoading = true;
    });
    
    builder.addCase(fetchSubscriptionStatus.fulfilled, (state, action) => {
      state.isLoading = false;
      state.currentSubscription = action.payload;
    });
    
    builder.addCase(fetchSubscriptionStatus.rejected, (state, action) => {
      state.isLoading = false;
      state.error = action.payload;
    });
    
    // --------------------------------------------
    // FETCH HISTORY
    // --------------------------------------------
    builder.addCase(fetchPaymentHistory.fulfilled, (state, action) => {
      state.paymentHistory = action.payload;
    });

    // --------------------------------------------
    // DELETE PAYMENT HISTORY ITEM
    // --------------------------------------------
    builder.addCase(deletePaymentHistoryItem.pending, (state) => {
      state.isDeletingHistoryItem = true;
      state.historyActionError = null;
    });

    builder.addCase(deletePaymentHistoryItem.fulfilled, (state, action) => {
      state.isDeletingHistoryItem = false;
      const transactionId = action.payload?.transactionId;
      const transactions = Array.isArray(state.paymentHistory?.transactions)
        ? state.paymentHistory.transactions.filter((item) => String(item?.id) !== String(transactionId))
        : [];

      state.paymentHistory = {
        ...(state.paymentHistory || {}),
        transactions,
        total_count: transactions.length,
      };
    });

    builder.addCase(deletePaymentHistoryItem.rejected, (state, action) => {
      state.isDeletingHistoryItem = false;
      state.historyActionError = action.payload || action.error?.message || 'Failed to delete transaction';
    });

    // --------------------------------------------
    // CLEAR PAYMENT HISTORY
    // --------------------------------------------
    builder.addCase(clearPaymentHistory.pending, (state) => {
      state.isClearingHistory = true;
      state.historyActionError = null;
    });

    builder.addCase(clearPaymentHistory.fulfilled, (state) => {
      state.isClearingHistory = false;
      state.paymentHistory = {
        transactions: [],
        total_count: 0,
        payment_services: state.paymentHistory?.payment_services || null,
      };
      state.currentSubscription = {
        plan: 'free',
        expires_at: null,
        days_remaining: null,
        auto_renew: false,
        next_billing_date: null,
      };
      state.activeOrder = null;
      state.paymentInProgress = false;
      state.paymentError = null;
    });

    builder.addCase(clearPaymentHistory.rejected, (state, action) => {
      state.isClearingHistory = false;
      state.historyActionError = action.payload || action.error?.message || 'Failed to clear history';
    });
    
    // --------------------------------------------
    // CREATE ORDER AND PAY
    // --------------------------------------------
    builder.addCase(createOrderAndPay.pending, (state, action) => {
      state.isCreatingOrder = true;
      state.paymentInProgress = true;
      state.paymentError = null;
      state.paymentDetails.attemptsCount += 1;
      state.paymentDetails.lastAttempt = {
        at: new Date().toISOString(),
        planId: action.meta?.arg?.planId || null,
      };
    });
    
    builder.addCase(createOrderAndPay.fulfilled, (state, action) => {
      state.isCreatingOrder = false;
      state.activeOrder = action.payload.order;
      state.paymentDetails.lastAttempt = {
        at: new Date().toISOString(),
        planId: action.payload.planId,
        orderId: action.payload.order?.order_id || null,
        amount: action.payload.order?.amount || null,
        currency: action.payload.order?.currency || 'INR',
      };
    });
    
    builder.addCase(createOrderAndPay.rejected, (state, action) => {
      state.isCreatingOrder = false;
      state.paymentInProgress = false;
      state.activeOrder = null;
      
      // Don't show error for user cancellation
      if (action.payload !== 'PAYMENT_CANCELLED') {
        state.paymentError = action.payload;
      }

      state.paymentDetails.lastFailure = {
        at: new Date().toISOString(),
        stage: 'create_order_or_checkout',
        error: action.payload || 'Unknown payment error',
      };
    });
    
    // --------------------------------------------
    // VERIFY PAYMENT
    // --------------------------------------------
    builder.addCase(verifyPayment.pending, (state) => {
      state.isVerifying = true;
    });
    
    builder.addCase(verifyPayment.fulfilled, (state, action) => {
      state.isVerifying = false;
      state.paymentInProgress = false;
      state.activeOrder = null;
      state.currentSubscription = action.payload;
      state.showUpgradePrompt = false;
      state.upgradeReason = null;
      state.paymentDetails.lastSuccess = {
        at: new Date().toISOString(),
        transactionId: action.payload?.transaction_id || null,
        plan: action.payload?.plan || null,
        expiresAt: action.payload?.expires_at || null,
      };
      state.paymentDetails.lastFailure = null;
    });
    
    builder.addCase(verifyPayment.rejected, (state, action) => {
      state.isVerifying = false;
      state.paymentInProgress = false;
      state.paymentError = action.payload;
      state.paymentDetails.lastFailure = {
        at: new Date().toISOString(),
        stage: 'verify_payment',
        error: action.payload || 'Verification failed',
      };
    });
    
    // --------------------------------------------
    // SUBSCRIBE TO PLAN (FULL FLOW)
    // --------------------------------------------
    builder.addCase(subscribeToPlan.pending, (state) => {
      state.paymentInProgress = true;
      state.paymentError = null;
    });
    
    builder.addCase(subscribeToPlan.fulfilled, (state, action) => {
      state.paymentInProgress = false;
      state.showUpgradePrompt = false;
      state.upgradeReason = null;

      const paymentStatus = action.payload?.paymentStatus || {};
      state.paymentStatus = {
        success: true,
        dismissed: false,
        planType: paymentStatus.planType || 'Pro',
        durationMonths: paymentStatus.durationMonths || 1,
        amount: Number(paymentStatus.amount || 0),
        transactionId: paymentStatus.transactionId || null,
      };
    });
    
    builder.addCase(subscribeToPlan.rejected, (state, action) => {
      state.paymentInProgress = false;
      if (action.payload !== 'PAYMENT_CANCELLED') {
        state.paymentError = action.payload;
      }
    });
    
    // --------------------------------------------
    // CANCEL SUBSCRIPTION
    // --------------------------------------------
    builder.addCase(cancelSubscription.pending, (state) => {
      state.isCancelling = true;
    });
    
    builder.addCase(cancelSubscription.fulfilled, (state, action) => {
      state.isCancelling = false;
      state.currentSubscription = action.payload;
    });
    
    builder.addCase(cancelSubscription.rejected, (state, action) => {
      state.isCancelling = false;
      state.error = action.payload;
    });
  },
});

// --------------------------------------------
// EXPORTS
// --------------------------------------------

export const {
  setPaymentSuccess,
  clearPaymentStatus,
  dismissPaymentSuccess,
  clearError,
  clearPaymentDetails,
  clearHistoryActionError,
  showUpgradePrompt,
  hideUpgradePrompt,
  setSelectedPlan,
  clearSelectedPlan,
  resetPaymentFlow,
  resetSubscription,
} = subscriptionSlice.actions;

// Selectors
export const selectPlans = (state) => state.subscription.plans;
export const selectPlansLoaded = (state) => state.subscription.plansLoaded;
export const selectCurrentSubscription = (state) => state.subscription.currentSubscription;
export const selectPaymentHistory = (state) => state.subscription.paymentHistory;
export const selectIsDeletingHistoryItem = (state) => state.subscription.isDeletingHistoryItem;
export const selectIsClearingHistory = (state) => state.subscription.isClearingHistory;
export const selectHistoryActionError = (state) => state.subscription.historyActionError;
export const selectIsLoading = (state) => state.subscription.isLoading;
export const selectIsCreatingOrder = (state) => state.subscription.isCreatingOrder;
export const selectIsVerifying = (state) => state.subscription.isVerifying;
export const selectIsCancelling = (state) => state.subscription.isCancelling;
export const selectPaymentInProgress = (state) => state.subscription.paymentInProgress;
export const selectError = (state) => state.subscription.error;
export const selectPaymentError = (state) => state.subscription.paymentError;
export const selectPaymentStatus = (state) => state.subscription.paymentStatus;
export const selectShowUpgradePrompt = (state) => state.subscription.showUpgradePrompt;
export const selectUpgradeReason = (state) => state.subscription.upgradeReason;
export const selectSelectedPlanId = (state) => state.subscription.selectedPlanId;
export const selectPaymentDetails = (state) => state.subscription.paymentDetails;

export default subscriptionSlice.reducer;