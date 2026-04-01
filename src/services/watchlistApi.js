// ============================================
// DEALHUNT APP - WATCHLIST API SERVICE
// Part 3: Watchlist & Price Alerts
// ============================================

import { del, get, post } from './api';
import { API } from '../utils/constants';

const toNumber = (value) => {
  const n = Number(value);
  return Number.isFinite(n) ? n : null;
};

const normalizeWatchlistItem = (rawItem = {}) => {
  const nestedProduct = rawItem?.product && typeof rawItem.product === 'object' ? rawItem.product : {};
  const productId =
    rawItem?.product_id ||
    nestedProduct?.product_id ||
    nestedProduct?.id ||
    null;

  const firstListing = Array.isArray(nestedProduct?.listings) ? nestedProduct.listings[0] : null;

  const currentPrice =
    toNumber(nestedProduct?.current_price) ??
    toNumber(rawItem?.current_price) ??
    toNumber(nestedProduct?.best_price) ??
    toNumber(rawItem?.best_price) ??
    toNumber(nestedProduct?.price) ??
    toNumber(rawItem?.price) ??
    toNumber(firstListing?.current_price) ??
    toNumber(firstListing?.price);

  const originalPrice =
    toNumber(nestedProduct?.original_price) ??
    toNumber(rawItem?.original_price) ??
    toNumber(nestedProduct?.mrp) ??
    toNumber(rawItem?.mrp) ??
    toNumber(firstListing?.original_price);

  const normalizedProduct = {
    ...nestedProduct,
    id: nestedProduct?.id || productId,
    product_id: productId,
    title:
      nestedProduct?.title ||
      nestedProduct?.product_title ||
      rawItem?.product_title ||
      rawItem?.title ||
      rawItem?.name ||
      'Product',
    product_title:
      nestedProduct?.product_title ||
      rawItem?.product_title ||
      nestedProduct?.title ||
      rawItem?.title ||
      null,
    image_url:
      nestedProduct?.image_url ||
      rawItem?.image_url ||
      firstListing?.image_url ||
      null,
    best_platform:
      nestedProduct?.best_platform ||
      rawItem?.best_platform ||
      nestedProduct?.platform ||
      rawItem?.platform ||
      firstListing?.platform ||
      null,
    platform:
      nestedProduct?.platform ||
      rawItem?.platform ||
      nestedProduct?.best_platform ||
      rawItem?.best_platform ||
      firstListing?.platform ||
      null,
    best_price:
      toNumber(nestedProduct?.best_price) ??
      toNumber(rawItem?.best_price) ??
      currentPrice,
    current_price: currentPrice,
    original_price: originalPrice,
    price_change_7d:
      toNumber(nestedProduct?.price_change_7d) ??
      toNumber(rawItem?.price_change_7d) ??
      toNumber(nestedProduct?.price_change) ??
      toNumber(rawItem?.price_change) ??
      0,
    price_change_percentage:
      toNumber(nestedProduct?.price_change_percentage) ??
      toNumber(rawItem?.price_change_percentage) ??
      toNumber(nestedProduct?.discount_percentage) ??
      toNumber(rawItem?.discount_percentage) ??
      0,
    product_url:
      nestedProduct?.product_url ||
      rawItem?.product_url ||
      firstListing?.product_url ||
      null,
    in_stock:
      nestedProduct?.in_stock ??
      rawItem?.in_stock ??
      firstListing?.in_stock ??
      true,
  };

  return {
    id: rawItem?.id || `watch_${productId || Date.now()}`,
    product_id: productId,
    added_at: rawItem?.added_at || rawItem?.created_at || new Date().toISOString(),
    target_price: rawItem?.target_price ?? null,
    notify_any_drop: rawItem?.notify_any_drop ?? true,
    product: normalizedProduct,
  };
};

const mapApiError = (response, fallbackMessage) => {
  const status = Number(response?.statusCode ?? response?.status ?? response?.code ?? 0);
  const errorText = response?.error || fallbackMessage;
  return { status, errorText };
};

const isNotFoundError = (status, errorText) => {
  const msg = String(errorText || '').toLowerCase();
  return status === 404 || msg.includes('resource not found') || msg.includes('not found') || msg.includes('404');
};

// --------------------------------------------
// WATCHLIST API METHODS
// --------------------------------------------

export const watchlistAPI = {
  /**
   * Get all watchlist items for current user
   * @returns {Promise<{success: boolean, data?: Object, error?: string}>}
   */
  getWatchlist: async () => {
    try {
      const response = await get(`${API.ENDPOINTS.WATCHLIST}/`);

      if (!response.success) {
        const { status, errorText } = mapApiError(response, 'Failed to fetch watchlist');

        if (status === 401) {
          return {
            success: false,
            error: 'Please login to view your watchlist',
            code: 'UNAUTHORIZED',
          };
        }

        return {
          success: false,
          error: errorText,
          code: status || 'UNKNOWN',
        };
      }

      const payload = response?.data;
      const rawItems =
        payload?.items ||
        payload?.watchlist ||
        (Array.isArray(payload) ? payload : []);

      const normalizedItems = rawItems
        .map(normalizeWatchlistItem)
        .filter((item) => Boolean(item?.product_id));

      const total =
        toNumber(payload?.total) ??
        toNumber(payload?.count) ??
        normalizedItems.length;

      const limit =
        toNumber(payload?.limit) ??
        toNumber(payload?.watchlist_limit) ??
        5;
      
      return {
        success: true,
        data: {
          items: normalizedItems,
          total,
          limit,
        },
      };
    } catch (error) {
      console.error('[WatchlistAPI] Get watchlist error:', error);
      
      // Handle specific error cases
      if (error.response?.status === 401) {
        return {
          success: false,
          error: 'Please login to view your watchlist',
          code: 'UNAUTHORIZED',
        };
      }
      
      return {
        success: false,
        error: error.response?.data?.detail || error.message || 'Failed to fetch watchlist',
        code: error.response?.status || 'UNKNOWN',
      };
    }
  },

  /**
   * Add a product to watchlist
   * @param {string} productId - Product UUID to add
   * @returns {Promise<{success: boolean, data?: Object, error?: string}>}
   */
  addToWatchlist: async (productId) => {
    try {
      const response = await post(`${API.ENDPOINTS.WATCHLIST}/`, {
        product_id: productId,
      });

      if (!response.success) {
        const { status, errorText } = mapApiError(response, 'Failed to add to watchlist');
        const detail = String(errorText || '');
        const lowerDetail = detail.toLowerCase();

        if ((status === 400 || status === 403) && lowerDetail.includes('limit')) {
          return {
            success: false,
            error: detail,
            code: 'LIMIT_REACHED',
          };
        }

        if (status === 403 && lowerDetail.includes('access denied')) {
          return {
            success: false,
            error: 'Watchlist limit reached. Remove one item to add a new product.',
            code: 'LIMIT_REACHED',
          };
        }

        if ((status === 400 || status === 409) && (lowerDetail.includes('already') || lowerDetail.includes('duplicate'))) {
          return {
            success: false,
            error: 'Product is already in your watchlist',
            code: 'DUPLICATE',
          };
        }

        if (status === 401) {
          return {
            success: false,
            error: 'Please login to add to watchlist',
            code: 'UNAUTHORIZED',
          };
        }

        if (status === 404) {
          return {
            success: false,
            error: 'Product not found',
            code: 'NOT_FOUND',
          };
        }

        return {
          success: false,
          error: detail,
          code: status || 'UNKNOWN',
        };
      }

      const payload = response?.data || {};
      const normalizedItem = normalizeWatchlistItem({
        ...(payload?.item || {}),
        ...payload,
        product_id: payload?.product_id || productId,
      });
      
      return {
        success: true,
        data: {
          id: normalizedItem.id,
          product_id: normalizedItem.product_id || productId,
          added_at: normalizedItem.added_at,
          message: payload?.message || 'Product added to watchlist',
        },
      };
    } catch (error) {
      console.error('[WatchlistAPI] Add to watchlist error:', error);

      return {
        success: false,
        error: error?.message || 'Failed to add to watchlist',
        code: 'UNKNOWN',
      };
    }
  },

  /**
   * Remove a product from watchlist
   * @param {string} productId - Product UUID to remove
   * @returns {Promise<{success: boolean, data?: Object, error?: string}>}
   */
  removeFromWatchlist: async (productId, watchlistItemId = null) => {
    try {
      const candidateIds = [productId, watchlistItemId]
        .filter(Boolean)
        .map((id) => String(id).trim())
        .filter(Boolean)
        .filter((id, index, arr) => arr.indexOf(id) === index);

      if (candidateIds.length === 0) {
        return {
          success: false,
          error: 'Invalid product id',
          code: 'INVALID_ID',
        };
      }

      let lastNotFound = false;

      for (const id of candidateIds) {
        const response = await del(`${API.ENDPOINTS.WATCHLIST}/${id}`);

        if (response?.success) {
          return {
            success: true,
            data: {
              message: response?.data?.message || 'Product removed from watchlist',
              product_id: String(productId || id),
            },
          };
        }

        const { status, errorText } = mapApiError(response, 'Failed to remove from watchlist');

        if (status === 401) {
          return {
            success: false,
            error: 'Please login to modify watchlist',
            code: 'UNAUTHORIZED',
          };
        }

        if (isNotFoundError(status, errorText)) {
          lastNotFound = true;
          continue;
        }

        return {
          success: false,
          error: errorText,
          code: status || 'UNKNOWN',
        };
      }

      if (lastNotFound) {
        return {
          success: true,
          data: {
            message: 'Product was not in watchlist',
            product_id: String(productId || candidateIds[0]),
          },
        };
      }

      return {
        success: false,
        error: 'Failed to remove from watchlist',
        code: 'UNKNOWN',
      };
    } catch (error) {
      console.error('[WatchlistAPI] Remove from watchlist error:', error);

      const status = Number(error?.statusCode ?? error?.response?.status ?? 0);
      const errText = error?.response?.data?.detail || error?.error || error?.message || 'Failed to remove from watchlist';

      if (status === 401) {
        return {
          success: false,
          error: 'Please login to modify watchlist',
          code: 'UNAUTHORIZED',
        };
      }

      if (isNotFoundError(status, errText)) {
        // Product not in watchlist - treat as success (idempotent)
        return {
          success: true,
          data: {
            message: 'Product was not in watchlist',
            product_id: String(productId || watchlistItemId || ''),
          },
        };
      }

      return {
        success: false,
        error: errText,
        code: status || 'UNKNOWN',
      };
    }
  },

  /**
   * Check if a product is in user's watchlist
   * @param {string} productId - Product UUID to check
   * @returns {Promise<{success: boolean, data?: Object, error?: string}>}
   */
  checkWatchlist: async (productId) => {
    try {
      const response = await get(`${API.ENDPOINTS.WATCHLIST_CHECK}/${productId}`);

      if (!response.success) {
        const { status, errorText } = mapApiError(response, 'Failed to check watchlist');

        if (status === 404) {
          return {
            success: true,
            data: {
              inWatchlist: false,
              productId: productId,
            },
          };
        }

        if (status === 401) {
          return {
            success: false,
            error: 'Please login to check watchlist',
            code: 'UNAUTHORIZED',
          };
        }

        return {
          success: false,
          error: errorText,
          code: status || 'UNKNOWN',
        };
      }

      const inWatchlist = Boolean(
        response?.data?.in_watchlist ?? response?.data?.inWatchlist ?? false
      );
      
      return {
        success: true,
        data: {
          inWatchlist,
          productId: productId,
        },
      };
    } catch (error) {
      console.error('[WatchlistAPI] Check watchlist error:', error);
      
      // For check errors, default to false (not in watchlist)
      if (error.response?.status === 404) {
        return {
          success: true,
          data: {
            inWatchlist: false,
            productId: productId,
          },
        };
      }
      
      if (error.response?.status === 401) {
        return {
          success: false,
          error: 'Please login to check watchlist',
          code: 'UNAUTHORIZED',
        };
      }
      
      return {
        success: false,
        error: error.response?.data?.detail || error.message || 'Failed to check watchlist',
        code: error.response?.status || 'UNKNOWN',
      };
    }
  },

  /**
   * Batch check multiple products against watchlist
   * Uses checkCache to avoid duplicate calls
   * @param {string[]} productIds - Array of product UUIDs
   * @param {Object} existingCache - Current cache from Redux state
   * @returns {Promise<{success: boolean, data?: Object, error?: string}>}
   */
  batchCheckWatchlist: async (productIds, existingCache = {}) => {
    try {
      // Filter out already cached products
      const uncachedIds = productIds.filter(id => !(id in existingCache));
      
      if (uncachedIds.length === 0) {
        // All products already cached
        return {
          success: true,
          data: {
            results: productIds.reduce((acc, id) => {
              acc[id] = existingCache[id] || false;
              return acc;
            }, {}),
            fromCache: true,
          },
        };
      }
      
      // Check uncached products in parallel (with concurrency limit)
      const BATCH_SIZE = 5;
      const results = { ...existingCache };
      
      for (let i = 0; i < uncachedIds.length; i += BATCH_SIZE) {
        const batch = uncachedIds.slice(i, i + BATCH_SIZE);
        const batchResults = await Promise.all(
          batch.map(async (id) => {
            const result = await watchlistAPI.checkWatchlist(id);
            return {
              id,
              inWatchlist: result.success ? result.data.inWatchlist : false,
            };
          })
        );
        
        batchResults.forEach(({ id, inWatchlist }) => {
          results[id] = inWatchlist;
        });
      }
      
      return {
        success: true,
        data: {
          results,
          fromCache: false,
          checkedCount: uncachedIds.length,
        },
      };
    } catch (error) {
      console.error('[WatchlistAPI] Batch check error:', error);
      
      return {
        success: false,
        error: error.message || 'Failed to batch check watchlist',
        code: 'BATCH_ERROR',
      };
    }
  },
};

export default watchlistAPI;