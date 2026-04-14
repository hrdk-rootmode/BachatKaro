// ============================================
// DEALHUNT APP - WATCHLIST REDUX SLICE
// Part 3: Watchlist & Price Alerts
// ============================================

import { createSlice, createAsyncThunk } from '@reduxjs/toolkit';
import { watchlistAPI } from '../services/watchlistApi';

// --------------------------------------------
// INITIAL STATE
// --------------------------------------------

const initialState = {
  // Data
  items: [],
  totalItems: 0,
  limit: 5, // Default free plan limit
  isGracePeriod: false,
  graceDaysRemaining: null,
  overLimitCount: 0,
  warningMessage: null,
  prunedCount: 0,
  
  // UI State
  isLoading: false,
  isRefreshing: false,
  error: null,
  
  // Optimistic update tracking
  addingIds: [],      // Product IDs currently being added
  removingIds: [],    // Product IDs currently being removed
  
  // Check status cache (productId -> boolean)
  checkCache: {},
  
  // Last fetch timestamp for stale data check
  lastFetched: null,
};

const resolveRemovePayload = (payload) => {
  if (payload && typeof payload === 'object') {
    const productId = payload.productId || payload.product_id || payload.id || null;
    const watchlistItemId = payload.watchlistItemId || payload.watchlist_item_id || payload.itemId || null;
    return {
      productId: productId ? String(productId) : null,
      watchlistItemId: watchlistItemId ? String(watchlistItemId) : null,
    };
  }

  return {
    productId: payload ? String(payload) : null,
    watchlistItemId: null,
  };
};

// --------------------------------------------
// ASYNC THUNKS
// --------------------------------------------

/**
 * Fetch all watchlist items
 */
export const fetchWatchlist = createAsyncThunk(
  'watchlist/fetchWatchlist',
  async ({ forceRefresh = false } = {}, { getState, rejectWithValue }) => {
    try {
      const { watchlist } = getState();
      
      // Skip if recently fetched (within 30 seconds) unless force refresh
      if (
        !forceRefresh &&
        watchlist.lastFetched &&
        Date.now() - watchlist.lastFetched < 30000 &&
        watchlist.items.length > 0
      ) {
        return {
          items: watchlist.items,
          total: watchlist.totalItems,
          limit: watchlist.limit,
          fromCache: true,
        };
      }
      
      const result = await watchlistAPI.getWatchlist();
      
      if (!result.success) {
        return rejectWithValue(result.error);
      }
      
      return {
        ...result.data,
        fromCache: false,
      };
    } catch (error) {
      return rejectWithValue(error.message || 'Failed to fetch watchlist');
    }
  }
);

/**
 * Add product to watchlist with optimistic update
 */
export const addToWatchlist = createAsyncThunk(
  'watchlist/addToWatchlist',
  async (product, { dispatch, rejectWithValue }) => {
    const productId = product.product_id || product.id;
    
    try {
      // API call (optimistic update happens in reducer via pending action)
      const result = await watchlistAPI.addToWatchlist(productId);
      
      if (!result.success) {
        return rejectWithValue({
          error: result.error,
          code: result.code,
          productId,
          limit: result.limit,
          currentPlan: result.currentPlan,
        });
      }
      
      return {
        watchlistItem: result.data,
        product,
        productId,
      };
    } catch (error) {
      return rejectWithValue({
        error: error.message || 'Failed to add to watchlist',
        productId,
      });
    }
  }
);

/**
 * Remove product from watchlist with optimistic update
 */
export const removeFromWatchlist = createAsyncThunk(
  'watchlist/removeFromWatchlist',
  async (payload, { getState, rejectWithValue }) => {
    const { productId, watchlistItemId } = resolveRemovePayload(payload);

    if (!productId && !watchlistItemId) {
      return rejectWithValue({
        error: 'Invalid product id',
        productId: null,
      });
    }

    const removeKey = productId || watchlistItemId;

    try {
      // Store item for potential rollback
      const { watchlist } = getState();
      const itemToRemove = watchlist.items.find(
        item =>
          item.product_id === removeKey ||
          item.product?.product_id === removeKey ||
          item.id === watchlistItemId ||
          item.product?.id === removeKey
      );
      
      // API call (optimistic update happens in reducer via pending action)
      const result = await watchlistAPI.removeFromWatchlist(productId || watchlistItemId, watchlistItemId);
      
      if (!result.success) {
        return rejectWithValue({
          error: result.error,
          productId: removeKey,
          itemToRestore: itemToRemove,
        });
      }
      
      return {
        productId: removeKey,
        watchlistItemId,
        message: result.data.message,
      };
    } catch (error) {
      return rejectWithValue({
        error: error.message || 'Failed to remove from watchlist',
        productId: removeKey,
      });
    }
  }
);

/**
 * Check if a product is in watchlist
 */
export const checkWatchlistStatus = createAsyncThunk(
  'watchlist/checkStatus',
  async (productId, { getState, rejectWithValue }) => {
    try {
      const { watchlist } = getState();
      
      // Return cached result if available
      if (productId in watchlist.checkCache) {
        return {
          productId,
          inWatchlist: watchlist.checkCache[productId],
          fromCache: true,
        };
      }
      
      const result = await watchlistAPI.checkWatchlist(productId);
      
      if (!result.success) {
        return rejectWithValue(result.error);
      }
      
      return {
        productId,
        inWatchlist: result.data.inWatchlist,
        fromCache: false,
      };
    } catch (error) {
      return rejectWithValue(error.message || 'Failed to check watchlist status');
    }
  }
);

/**
 * Batch check multiple products
 */
export const batchCheckWatchlist = createAsyncThunk(
  'watchlist/batchCheck',
  async (productIds, { getState, rejectWithValue }) => {
    try {
      const { watchlist } = getState();
      
      const result = await watchlistAPI.batchCheckWatchlist(productIds, watchlist.checkCache);
      
      if (!result.success) {
        return rejectWithValue(result.error);
      }
      
      return result.data;
    } catch (error) {
      return rejectWithValue(error.message || 'Failed to batch check watchlist');
    }
  }
);

// --------------------------------------------
// SLICE
// --------------------------------------------

const watchlistSlice = createSlice({
  name: 'watchlist',
  initialState,
  
  reducers: {
    // Clear error state
    clearError: (state) => {
      state.error = null;
    },
    
    // Clear entire watchlist state (on logout)
    clearWatchlist: (state) => {
      return { ...initialState };
    },
    
    // Update check cache directly (useful for optimistic updates)
    updateCheckCache: (state, action) => {
      const { productId, inWatchlist } = action.payload;
      state.checkCache[productId] = inWatchlist;
    },
    
    // Bulk update check cache from items
    syncCheckCacheFromItems: (state) => {
      state.items.forEach(item => {
        const productId = item.product_id || item.product?.product_id;
        if (productId) {
          state.checkCache[productId] = true;
        }
      });
    },
  },
  
  extraReducers: (builder) => {
    // ============================================
    // FETCH WATCHLIST
    // ============================================
    builder.addCase(fetchWatchlist.pending, (state, action) => {
      // Use isRefreshing for pull-to-refresh, isLoading for initial load
      if (state.items.length === 0) {
        state.isLoading = true;
      } else {
        state.isRefreshing = true;
      }
      state.error = null;
    });
    
    builder.addCase(fetchWatchlist.fulfilled, (state, action) => {
      state.isLoading = false;
      state.isRefreshing = false;
      
      if (!action.payload.fromCache) {
        state.items = action.payload.items || [];
        state.totalItems = action.payload.total || action.payload.items?.length || 0;
        state.limit = action.payload.limit || 5;
        state.isGracePeriod = Boolean(action.payload.is_grace_period);
        state.graceDaysRemaining = action.payload.grace_days_remaining ?? null;
        state.overLimitCount = action.payload.over_limit_count || 0;
        state.warningMessage = action.payload.warning_message || null;
        state.prunedCount = action.payload.pruned_count || 0;
        state.lastFetched = Date.now();
        
        // Sync check cache with fetched items
        state.checkCache = {};
        state.items.forEach(item => {
          const productId = item.product_id || item.product?.product_id;
          if (productId) {
            state.checkCache[productId] = true;
          }
        });
      }
    });
    
    builder.addCase(fetchWatchlist.rejected, (state, action) => {
      state.isLoading = false;
      state.isRefreshing = false;
      state.error = action.payload || 'Failed to fetch watchlist';
    });
    
    // ============================================
    // ADD TO WATCHLIST (Optimistic)
    // ============================================
    builder.addCase(addToWatchlist.pending, (state, action) => {
      const product = action.meta.arg;
      const productId = product.product_id || product.id;
      
      // Track that this product is being added
      if (!state.addingIds.includes(productId)) {
        state.addingIds.push(productId);
      }
      
      // Optimistic update: Add to items immediately
      const optimisticItem = {
        id: `temp_${productId}`,
        product_id: productId,
        added_at: new Date().toISOString(),
        product: product,
        _isOptimistic: true,
      };
      
      // Check if not already in items
      const exists = state.items.some(
        item => item.product_id === productId || item.product?.product_id === productId
      );
      
      if (!exists) {
        state.items.unshift(optimisticItem);
        state.totalItems += 1;
      }
      
      // Update check cache
      state.checkCache[productId] = true;
      state.error = null;
    });
    
    builder.addCase(addToWatchlist.fulfilled, (state, action) => {
      const { productId, watchlistItem, product } = action.payload;
      
      // Remove from adding tracker
      state.addingIds = state.addingIds.filter(id => id !== productId);
      
      // Replace optimistic item with real item
      const index = state.items.findIndex(
        item => item.product_id === productId || item.id === `temp_${productId}`
      );
      
      if (index !== -1) {
        state.items[index] = {
          id: watchlistItem.id,
          product_id: productId,
          added_at: watchlistItem.added_at,
          product: product,
          _isOptimistic: false,
        };
      }
      
      // Ensure check cache is updated
      state.checkCache[productId] = true;
    });
    
    builder.addCase(addToWatchlist.rejected, (state, action) => {
      const { productId, error, code, limit, currentPlan } = action.payload || {};
      
      // Remove from adding tracker
      state.addingIds = state.addingIds.filter(id => id !== productId);
      
      // Rollback: Remove optimistic item
      state.items = state.items.filter(
        item => item.product_id !== productId && item.id !== `temp_${productId}`
      );
      state.totalItems = Math.max(0, state.totalItems - 1);
      
      // Update check cache
      state.checkCache[productId] = false;
      
      // Set error with additional context for limit errors
      if (code === 'LIMIT_REACHED') {
        state.error = {
          message: error,
          type: 'LIMIT_REACHED',
          limit,
          currentPlan,
        };
      } else if (code === 'DUPLICATE') {
        // Not really an error, product is already in watchlist
        state.checkCache[productId] = true;
        state.error = null;
      } else {
        state.error = error || 'Failed to add to watchlist';
      }
    });
    
    // ============================================
    // REMOVE FROM WATCHLIST (Optimistic)
    // ============================================
    builder.addCase(removeFromWatchlist.pending, (state, action) => {
      const { productId, watchlistItemId } = resolveRemovePayload(action.meta.arg);
      const removeKey = productId || watchlistItemId;
      if (!removeKey) return;
      
      // Track that this product is being removed
      if (!state.removingIds.includes(removeKey)) {
        state.removingIds.push(removeKey);
      }
      
      // Optimistic update: Remove from items immediately
      const initialLength = state.items.length;
      state.items = state.items.filter(
        item =>
          item.product_id !== productId &&
          item.product?.product_id !== productId &&
          item.id !== watchlistItemId &&
          item.product?.id !== removeKey
      );
      
      if (state.items.length < initialLength) {
        state.totalItems = Math.max(0, state.totalItems - 1);
      }
      
      // Update check cache
      state.checkCache[removeKey] = false;
      if (watchlistItemId && productId) {
        state.checkCache[productId] = false;
      }
      state.error = null;
    });
    
    builder.addCase(removeFromWatchlist.fulfilled, (state, action) => {
      const { productId, watchlistItemId } = action.payload;
      const removeKey = productId || watchlistItemId;
      if (!removeKey) return;
      
      // Remove from removing tracker
      state.removingIds = state.removingIds.filter(id => id !== removeKey);
      
      // Ensure removed (in case pending didn't catch it)
      state.items = state.items.filter(
        item =>
          item.product_id !== productId &&
          item.product?.product_id !== productId &&
          item.id !== watchlistItemId &&
          item.product?.id !== removeKey
      );
      
      // Ensure check cache is updated
      state.checkCache[removeKey] = false;
      if (watchlistItemId && productId) {
        state.checkCache[productId] = false;
      }
    });
    
    builder.addCase(removeFromWatchlist.rejected, (state, action) => {
      const { productId, watchlistItemId, error, itemToRestore } = action.payload || {};
      const removeKey = productId || watchlistItemId;
      if (!removeKey) {
        state.error = error || 'Failed to remove from watchlist';
        return;
      }
      
      // Remove from removing tracker
      state.removingIds = state.removingIds.filter(id => id !== removeKey);
      
      // Rollback: Restore the item if we have it
      if (itemToRestore) {
        const exists = state.items.some(
          item => item.product_id === productId || item.id === watchlistItemId
        );
        
        if (!exists) {
          state.items.push(itemToRestore);
          state.totalItems += 1;
        }
      }
      
      // Update check cache (restore to true since removal failed)
      state.checkCache[removeKey] = true;
      if (watchlistItemId && productId) {
        state.checkCache[productId] = true;
      }
      
      state.error = error || 'Failed to remove from watchlist';
    });
    
    // ============================================
    // CHECK WATCHLIST STATUS
    // ============================================
    builder.addCase(checkWatchlistStatus.fulfilled, (state, action) => {
      const { productId, inWatchlist } = action.payload;
      state.checkCache[productId] = inWatchlist;
    });
    
    // ============================================
    // BATCH CHECK WATCHLIST
    // ============================================
    builder.addCase(batchCheckWatchlist.fulfilled, (state, action) => {
      const { results } = action.payload;
      state.checkCache = {
        ...state.checkCache,
        ...results,
      };
    });
  },
});

// --------------------------------------------
// EXPORTS
// --------------------------------------------

export const {
  clearError,
  clearWatchlist,
  updateCheckCache,
  syncCheckCacheFromItems,
} = watchlistSlice.actions;

// Selectors
export const selectWatchlistItems = (state) => state.watchlist.items;
export const selectWatchlistCount = (state) => state.watchlist.totalItems;
export const selectWatchlistLimit = (state) => state.watchlist.limit;
export const selectWatchlistGracePeriod = (state) => state.watchlist.isGracePeriod;
export const selectWatchlistGraceDaysRemaining = (state) => state.watchlist.graceDaysRemaining;
export const selectWatchlistOverLimitCount = (state) => state.watchlist.overLimitCount;
export const selectWatchlistWarningMessage = (state) => state.watchlist.warningMessage;
export const selectWatchlistPrunedCount = (state) => state.watchlist.prunedCount;
export const selectIsWatchlistLoading = (state) => state.watchlist.isLoading;
export const selectIsWatchlistRefreshing = (state) => state.watchlist.isRefreshing;
export const selectWatchlistError = (state) => state.watchlist.error;
export const selectCheckCache = (state) => state.watchlist.checkCache;

// Check if specific product is in watchlist
export const selectIsInWatchlist = (productId) => (state) => {
  // First check cache
  if (productId in state.watchlist.checkCache) {
    return state.watchlist.checkCache[productId];
  }
  
  // Fallback to checking items array
  return state.watchlist.items.some(
    item => item.product_id === productId || item.product?.product_id === productId
  );
};

// Check if product is being added/removed
export const selectIsAddingToWatchlist = (productId) => (state) => 
  state.watchlist.addingIds.includes(productId);

export const selectIsRemovingFromWatchlist = (productId) => (state) => 
  state.watchlist.removingIds.includes(productId);

export default watchlistSlice.reducer;