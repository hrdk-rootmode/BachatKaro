// ============================================
// DEALHUNT APP - SEARCH API SERVICE
// ============================================

import { get, post } from './api';
import { API } from '../utils/constants';

const debugLog = (...args) => {
  if (__DEV__) {
    console.log(...args);
  }
};

const debugError = (...args) => {
  if (__DEV__) {
    console.error(...args);
  }
};

/**
 * Search API service
 * Handles all search-related API calls with proper request validation
 */
export const searchAPI = {
  /**
   * Search products by text query
   * @param {string} query - Search term (min 2 chars)
   * @param {Object} filters - Filter options
   * @param {number} page - Page number (default 1)
   * @returns {Promise} Search results with products array
   */
  searchProducts: async (query, filters = {}, page = 1, options = {}) => {
    try {
      // Validate query
      if (!query || query.trim().length < 2) {
        return {
          success: false,
          error: 'Search term must be at least 2 characters',
        };
      }

      // Build request payload (match backend SearchRequest schema)
      const payload = {
        query: query.trim(),
        platforms: filters.platforms || null, // null = all platforms
        min_price: filters.minPrice ? parseFloat(filters.minPrice) : null,
        max_price: filters.maxPrice ? parseFloat(filters.maxPrice) : null,
        sort_by: filters.sortBy || 'relevance',
        page: Math.max(1, parseInt(page) || 1),
        count_usage: options.countUsage !== false,
      };

      debugLog('Search API: Sending payload:', payload);

      // Call search endpoint
      const response = await post(API.ENDPOINTS.SEARCH, payload);

      if (!response.success) {
        return response;
      }

      // Response format from backend:
      // {
      //   "query": "iphone",
      //   "total_results": 150,
      //   "page": 1,
      //   "products": [...],
      //   "cache_hit": false,
      //   "search_time_ms": 245
      // }

      debugLog('Search API Response:', {
        query: response.data.query,
        product_count: response.data.products?.length || 0,
        first_product_has_id: !!response.data.products?.[0]?.id,
        first_product_id: response.data.products?.[0]?.id,
      });

      return {
        success: true,
        data: {
          query: response.data.query,
          products: response.data.products || [],
          totalResults: response.data.total_results || 0,
          page: response.data.page || 1,
          cacheHit: response.data.cache_hit || false,
          searchTimeMs: response.data.search_time_ms || 0,
        },
      };
    } catch (error) {
      debugError('Search API Error:', error);
      return {
        success: false,
        error: error.error || 'Search failed',
      };
    }
  },

  /**
   * Search products by URL
   * @param {string} url - Product URL (Amazon/Flipkart)
   * @returns {Promise} Product data extracted from URL
   */
  searchByUrl: async (url) => {
    try {
      if (!url || url.trim().length < 10) {
        return {
          success: false,
          error: 'Valid product URL required',
        };
      }

      const payload = { url: url.trim() };

      debugLog('URL Search API: Sending:', payload);

      const response = await post(API.ENDPOINTS.SEARCH_BY_URL, payload);

      debugLog('URL Search API: Full response:', response);

      if (!response.success) {
        debugError('URL Search failed:', response.error);
        return response;
      }

      debugLog('URL Search Success:', {
        source_platform: response.data?.source?.platform,
        alternatives: response.data?.alternatives?.length || 0,
        origin: response.data?.response_origin
      });

      return {
        success: true,
        data: response.data,
      };
    } catch (error) {
      debugError('URL Search API Error:', error);
      debugError('Error details:', {
        message: error.message,
        response: error.response?.data,
        status: error.response?.status
      });
      return {
        success: false,
        error: error.error || error.response?.data?.detail || 'URL search failed',
      };
    }
  },

  /**
   * Get trending products
   * @returns {Promise} List of trending products
   */
  getTrending: async () => {
    try {
      debugLog('Trending API: Fetching...');

      const response = await get(API.ENDPOINTS.TRENDING);

      if (!response.success) {
        return response;
      }

      // Response is directly an array:
      // [
      //   {
      //     "product_id": "uuid",
      //     "title": "iPhone 15 Pro",
      //     "best_price": 129900,
      //     "best_platform": "amazon",
      //     "discount_percentage": 13,
      //     "image_url": "https://...",
      //     "search_count": 1240,
      //     "rank": 1
      //   }
      // ]

      return {
        success: true,
        data: Array.isArray(response.data) ? response.data : [],
      };
    } catch (error) {
      debugError('Trending API Error:', error);
      return {
        success: false,
        error: error.error || 'Failed to fetch trending',
      };
    }
  },
};

/**
 * Product API service
 * Handles product detail and price history
 */
export const productAPI = {
  /**
   * Get product details by ID
   * @param {string} productId - Product UUID
   * @returns {Promise} Product details with all listings
   */
  getProductById: async (productId) => {
    try {
      if (!productId) {
        return {
          success: false,
          error: 'Product ID required',
        };
      }

      debugLog('Product API: Fetching details for:', productId);

      const endpoint = `${API.ENDPOINTS.PRODUCT_DETAIL}/${productId}`;
      const response = await get(endpoint);

      if (!response.success) {
        return response;
      }

      return {
        success: true,
        data: response.data,
      };
    } catch (error) {
      debugError('Product Detail API Error:', error);
      return {
        success: false,
        error: error.error || 'Failed to fetch product details',
      };
    }
  },

  /**
   * Get price history for product
   * @param {string} productId - Product UUID
   * @param {string} platform - Platform name ('amazon', 'flipkart', 'all')
   * @param {number} days - Number of days (default 120)
   * @returns {Promise} Price history data for charts
   */
  getPriceHistory: async (productId, platform = 'amazon', days = 120) => {
    try {
      if (!productId) {
        return {
          success: false,
          error: 'Product ID required',
        };
      }

      if (!platform) {
        return {
          success: false,
          error: 'Platform required',
        };
      }

      const endpoint = `${API.ENDPOINTS.PRICE_HISTORY}/${productId}/price-history`;
      const params = {
        platform,
        days: Math.min(120, Math.max(7, days)), // 7-120 days
      };

      const response = await get(endpoint, params);

      if (!response.success) {
        return response;
      }

      return {
        success: true,
        data: response.data,
      };
    } catch (error) {
      debugError('Price History API Error:', error);
      return {
        success: false,
        error: error.error || 'Failed to fetch price history',
      };
    }
  },

  /**
   * Trigger live scrape refresh for one product and return updated product payload
   * @param {string} productId - Product UUID
   * @returns {Promise} Updated product details
   */
  refreshProductPrice: async (productId, platform = null) => {
    try {
      if (!productId) {
        return {
          success: false,
          error: 'Product ID required',
        };
      }

      debugLog(`Product API: Live refresh for ${productId}`);

      const endpoint = `${API.ENDPOINTS.PRODUCT_DETAIL}/${productId}/refresh-price`;
      const endpointWithQuery = platform ? `${endpoint}?platform=${encodeURIComponent(platform)}` : endpoint;
      const response = await post(endpointWithQuery, {});

      if (!response.success) {
        return response;
      }

      return {
        success: true,
        data: response.data,
      };
    } catch (error) {
      debugError('Refresh Product Price API Error:', error);
      return {
        success: false,
        error: error.error || 'Failed to refresh product price',
      };
    }
  },
};

export default {
  searchAPI,
  productAPI,
};
