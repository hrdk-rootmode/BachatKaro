// ============================================
// DEALHUNT APP - WATCHLIST CUSTOM HOOK
// Part 3: Watchlist & Price Alerts
// ============================================

import { useCallback, useEffect, useMemo } from 'react';
import { useDispatch, useSelector } from 'react-redux';
import { useTopToast } from '../components/common/TopToastProvider';

import {
  fetchWatchlist,
  addToWatchlist,
  removeFromWatchlist,
  checkWatchlistStatus,
  batchCheckWatchlist,
  clearError,
  selectWatchlistItems,
  selectWatchlistCount,
  selectWatchlistLimit,
  selectIsWatchlistLoading,
  selectIsWatchlistRefreshing,
  selectWatchlistError,
  selectCheckCache,
  selectIsInWatchlist,
  selectIsAddingToWatchlist,
  selectIsRemovingFromWatchlist,
} from '../store/watchlistSlice';

const isNotFoundLikeError = (err) => {
  const msg = String(err?.error || err?.message || err || '').toLowerCase();
  const code = Number(err?.statusCode ?? err?.code ?? 0);
  return code === 404 || msg.includes('resource not found') || msg.includes('not found') || msg.includes('404');
};

const isUnauthorizedError = (err) => {
  const msg = String(err?.error || err?.message || err || '').toLowerCase();
  const status = Number(err?.statusCode ?? err?.status ?? err?.code ?? 0);
  return status === 401 || String(err?.code || '').toUpperCase() === 'UNAUTHORIZED' || msg.includes('please login');
};

const isLimitReachedLikeError = (err, isAtLimit) => {
  const msg = String(err?.error || err?.message || err || '').toLowerCase();
  const status = Number(err?.statusCode ?? err?.status ?? err?.code ?? 0);
  const code = String(err?.code || '').toUpperCase();

  if (code === 'LIMIT_REACHED') return true;
  if (msg.includes('watchlist full') || msg.includes('maximum') || msg.includes('limit reached')) return true;

  // Backend may return a generic 403 "Access denied" when limit is reached.
  if (isAtLimit && (status === 403 || msg.includes('access denied'))) {
    return true;
  }

  return false;
};

// --------------------------------------------
// MAIN HOOK
// --------------------------------------------

/**
 * Custom hook for watchlist functionality
 * Provides easy access to watchlist state and actions
 * 
 * @returns {Object} Watchlist state and methods
 */
export const useWatchlist = () => {
  const dispatch = useDispatch();
  const { showToast } = useTopToast();
  
  // Selectors
  const items = useSelector(selectWatchlistItems);
  const totalCount = useSelector(selectWatchlistCount);
  const limit = useSelector(selectWatchlistLimit);
  const isLoading = useSelector(selectIsWatchlistLoading);
  const isRefreshing = useSelector(selectIsWatchlistRefreshing);
  const error = useSelector(selectWatchlistError);
  const checkCache = useSelector(selectCheckCache);
  
  // Derived state
  const isAtLimit = useMemo(() => totalCount >= limit, [totalCount, limit]);
  const remainingSlots = useMemo(() => Math.max(0, limit - totalCount), [limit, totalCount]);
  
  // --------------------------------------------
  // ACTIONS
  // --------------------------------------------
  
  /**
   * Fetch watchlist items from API
   * @param {boolean} forceRefresh - Force refresh even if recently fetched
   */
  const fetch = useCallback(
    (forceRefresh = false) => {
      return dispatch(fetchWatchlist({ forceRefresh }));
    },
    [dispatch]
  );
  
  /**
   * Refresh watchlist (for pull-to-refresh)
   */
  const refresh = useCallback(() => {
    return dispatch(fetchWatchlist({ forceRefresh: true }));
  }, [dispatch]);
  
  /**
   * Add a product to watchlist
   * @param {Object} product - Product object to add
   * @returns {Promise<boolean>} Success status
   */
  const add = useCallback(
    async (product) => {
      if (isAtLimit) {
        showToast({
          type: 'warning',
          title: 'Watchlist Full',
          message: `Your watchlist is full (${totalCount}/${limit}). Remove one item to add a new product.`,
          duration: 3800,
        });
        return false;
      }

      try {
        await dispatch(addToWatchlist(product)).unwrap();
        showToast({
          type: 'success',
          title: 'Added',
          message: 'Product added to your watchlist.',
          duration: 3000,
        });
        return true;
      } catch (err) {
        if (isLimitReachedLikeError(err, isAtLimit)) {
          showToast({
            type: 'warning',
            title: 'Watchlist Full',
            message: `Your watchlist is full (${totalCount}/${limit}). Remove one item to add a new product.`,
            duration: 4200,
          });
          return false;
        }

        if (isUnauthorizedError(err)) {
          showToast({
            type: 'error',
            title: 'Login Required',
            message: 'Please login to manage your watchlist.',
            duration: 3400,
          });
          return false;
        }

        showToast({
          type: 'error',
          title: 'Could Not Add',
          message: err?.error || 'Failed to add product to watchlist.',
          duration: 3400,
        });
        return false;
      }
    },
    [dispatch, isAtLimit, limit, showToast, totalCount]
  );
  
  /**
   * Remove a product from watchlist
   * @param {string} productId - Product ID to remove
   * @returns {Promise<boolean>} Success status
   */
  const remove = useCallback(
    async (productId) => {
      try {
        await dispatch(removeFromWatchlist(productId)).unwrap();
        showToast({
          type: 'info',
          title: 'Removed',
          message: 'Product removed from your watchlist.',
          duration: 2800,
        });
        return true;
      } catch (err) {
        if (isNotFoundLikeError(err)) {
          return true;
        }

        if (isUnauthorizedError(err)) {
          showToast({
            type: 'error',
            title: 'Login Required',
            message: 'Please login to manage your watchlist.',
            duration: 3400,
          });
          return false;
        }

        showToast({
          type: 'error',
          title: 'Could Not Remove',
          message: err?.error || 'Failed to remove from watchlist.',
          duration: 3400,
        });
        return false;
      }
    },
    [dispatch, showToast]
  );
  
  /**
   * Toggle product in watchlist (add if not present, remove if present)
   * @param {Object} product - Product object
   * @returns {Promise<{success: boolean, action: 'added'|'removed'}>}
   */
  const toggle = useCallback(
    async (product) => {
      const productId = product?.product_id || product?.id;
      const isInList = checkCache[productId] || false;
      
      if (isInList) {
        const success = await remove(productId);
        return { success, action: 'removed' };
      } else {
        const success = await add(product);
        return { success, action: 'added' };
      }
    },
    [checkCache, add, remove]
  );
  
  /**
   * Check if a specific product is in watchlist
   * @param {string} productId - Product ID to check
   */
  const checkStatus = useCallback(
    (productId) => {
      return dispatch(checkWatchlistStatus(productId));
    },
    [dispatch]
  );
  
  /**
   * Batch check multiple products
   * @param {string[]} productIds - Array of product IDs
   */
  const batchCheck = useCallback(
    (productIds) => {
      return dispatch(batchCheckWatchlist(productIds));
    },
    [dispatch]
  );
  
  /**
   * Clear any watchlist errors
   */
  const clearWatchlistError = useCallback(() => {
    dispatch(clearError());
  }, [dispatch]);
  
  // --------------------------------------------
  // RETURN
  // --------------------------------------------
  
  return {
    // State
    items,
    totalCount,
    limit,
    isLoading,
    isRefreshing,
    error,
    checkCache,
    
    // Derived state
    isAtLimit,
    remainingSlots,
    isEmpty: items.length === 0,
    
    // Actions
    fetch,
    refresh,
    add,
    remove,
    toggle,
    checkStatus,
    batchCheck,
    clearError: clearWatchlistError,
  };
};

// --------------------------------------------
// PRODUCT-SPECIFIC HOOK
// --------------------------------------------

/**
 * Hook for managing watchlist status of a specific product
 * Useful in ProductCard, ProductDetail, etc.
 * 
 * @param {string} productId - Product ID to track
 * @param {Object} product - Full product object (for adding)
 * @returns {Object} Product watchlist state and toggle function
 */
export const useProductWatchlist = (productId, product = null) => {
  const dispatch = useDispatch();
  const { showToast } = useTopToast();
  
  // Selectors
  const isInWatchlist = useSelector(selectIsInWatchlist(productId));
  const isAdding = useSelector(selectIsAddingToWatchlist(productId));
  const isRemoving = useSelector(selectIsRemovingFromWatchlist(productId));
  const limit = useSelector(selectWatchlistLimit);
  const totalCount = useSelector(selectWatchlistCount);
  const checkCache = useSelector(selectCheckCache);
  
  // Derived state
  const isProcessing = isAdding || isRemoving;
  const isAtLimit = totalCount >= limit;
  
  // Check status on mount if not cached
  useEffect(() => {
    if (productId && !(productId in checkCache)) {
      dispatch(checkWatchlistStatus(productId));
    }
  }, [productId, checkCache, dispatch]);
  
  /**
   * Toggle this product's watchlist status
   */
  const toggle = useCallback(async () => {
    if (isProcessing) return { success: false, action: null };
    
    const productData = product || { product_id: productId, id: productId };
    
    if (isInWatchlist) {
      // Remove from watchlist
      try {
        await dispatch(removeFromWatchlist(productId)).unwrap();
        showToast({
          type: 'info',
          title: 'Removed',
          message: 'Product removed from your watchlist.',
          duration: 2800,
        });
        return { success: true, action: 'removed' };
      } catch (err) {
        if (isNotFoundLikeError(err)) {
          return { success: true, action: 'removed' };
        }

        if (isUnauthorizedError(err)) {
          showToast({
            type: 'error',
            title: 'Login Required',
            message: 'Please login to manage your watchlist.',
            duration: 3400,
          });
          return { success: false, action: null };
        }

        showToast({
          type: 'error',
          title: 'Could Not Remove',
          message: err?.error || 'Failed to remove from watchlist.',
          duration: 3400,
        });
        return { success: false, action: null };
      }
    } else {
      // Add to watchlist
      if (isAtLimit) {
        showToast({
          type: 'warning',
          title: 'Watchlist Full',
          message: `Your watchlist is full (${totalCount}/${limit}). Remove one item to add a new product.`,
          duration: 4200,
        });
        return { success: false, action: null };
      }

      try {
        await dispatch(addToWatchlist(productData)).unwrap();
        showToast({
          type: 'success',
          title: 'Added',
          message: 'Product added to your watchlist.',
          duration: 3000,
        });
        return { success: true, action: 'added' };
      } catch (err) {
        if (isLimitReachedLikeError(err, isAtLimit)) {
          showToast({
            type: 'warning',
            title: 'Watchlist Full',
            message: `Your watchlist is full (${totalCount}/${limit}). Remove one item to add a new product.`,
            duration: 4200,
          });
          return { success: false, action: null };
        }

        if (isUnauthorizedError(err)) {
          showToast({
            type: 'error',
            title: 'Login Required',
            message: 'Please login to manage your watchlist.',
            duration: 3400,
          });
          return { success: false, action: null };
        }

        showToast({
          type: 'error',
          title: 'Could Not Add',
          message: err?.error || 'Failed to add product to watchlist.',
          duration: 3400,
        });
        return { success: false, action: null };
      }
    }
  }, [dispatch, productId, product, isInWatchlist, isProcessing, isAtLimit, limit, showToast, totalCount]);
  
  return {
    isInWatchlist,
    isAdding,
    isRemoving,
    isProcessing,
    isAtLimit: isAtLimit && !isInWatchlist, // Only relevant if not already in list
    toggle,
  };
};

// --------------------------------------------
// EXPORTS
// --------------------------------------------

export default useWatchlist;