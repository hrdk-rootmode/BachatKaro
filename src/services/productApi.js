// ============================================
// DEALHUNT APP - PRODUCT API SERVICE
// ============================================

import api from './api';
import { API } from '../utils/constants';

const isValidUuid = (value) => {
  if (!value) return false;
  return /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(String(value).trim());
};

// --------------------------------------------
// PRODUCT API METHODS
// --------------------------------------------

export const productAPI = {
  /**
   * Get product details by ID
   * 
   * @param {string} productId - Product UUID
   * @returns {Promise<Object>} API response
   */
  getProductById: async (productId) => {
    try {
      if (!productId) {
        return {
          success: false,
          error: 'Product ID is required',
        };
      }

      if (!isValidUuid(productId)) {
        return {
          success: false,
          error: 'Invalid product reference',
        };
      }
      
      // Make API call
      const response = await api.get(`${API.ENDPOINTS.PRODUCT_DETAIL}/${productId}`);
      
      // Backend returns full product object with listings array
      return {
        success: true,
        data: response.data,
      };
    } catch (error) {
      console.error('Product API error:', error);
      
      if (error.response) {
        const status = error.response.status;
        const message = error.response.data?.detail || error.response.data?.message;
        
        switch (status) {
          case 404:
            return { success: false, error: 'Product not found' };
          case 401:
            return { success: false, error: 'Please login again' };
          default:
            return { success: false, error: message || 'Failed to load product' };
        }
      }
      
      return {
        success: false,
        error: error.message || 'Network error. Check your connection.',
      };
    }
  },
  
  /**
   * Get price history for a product
   * 
   * @param {string} productId - Product UUID
   * @param {string} platform - Platform name (REQUIRED: amazon, flipkart, etc.)
   * @returns {Promise<Object>} API response
   */
  getPriceHistory: async (productId, platform = 'amazon') => {
    try {
      if (!productId) {
        return {
          success: false,
          error: 'Product ID is required',
        };
      }

      if (!isValidUuid(productId)) {
        return {
          success: false,
          error: 'Invalid product reference',
        };
      }
      
      if (!platform) {
        return {
          success: false,
          error: 'Platform is required',
        };
      }
      
      // Validate platform
      const validPlatforms = ['amazon', 'flipkart', 'meesho', 'myntra', 'nykaa', 'croma'];
      const normalizedPlatform = platform.toLowerCase();
      
      if (!validPlatforms.includes(normalizedPlatform)) {
        return {
          success: false,
          error: 'Invalid platform',
        };
      }
      
      // Make API call with platform query param
      const response = await api.get(
        `${API.ENDPOINTS.PRICE_HISTORY}/${productId}/price-history`,
        {
          params: { platform: normalizedPlatform },
        }
      );
      
      // Backend returns: { product_id, platform, history: [...], stats: {...} }
      return {
        success: true,
        data: response.data,
      };
    } catch (error) {
      console.error('Price History API error:', error);
      
      if (error.response) {
        const status = error.response.status;
        const message = error.response.data?.detail || error.response.data?.message;
        
        switch (status) {
          case 404:
            return { success: false, error: 'Price history not available' };
          case 400:
            return { success: false, error: message || 'Invalid request' };
          default:
            return { success: false, error: message || 'Failed to load price history' };
        }
      }
      
      return {
        success: false,
        error: error.message || 'Network error. Check your connection.',
      };
    }
  },
  
  /**
   * Get price history for all platforms (helper method)
   * Makes multiple API calls
   * 
   * @param {string} productId - Product UUID
   * @param {Array<string>} platforms - Array of platform names
   * @returns {Promise<Object>} Combined price history
   */
  getAllPriceHistories: async (productId, platforms = ['amazon', 'flipkart']) => {
    try {
      const promises = platforms.map(platform => 
        productAPI.getPriceHistory(productId, platform)
      );
      
      const results = await Promise.allSettled(promises);
      
      const histories = {};
      results.forEach((result, index) => {
        if (result.status === 'fulfilled' && result.value.success) {
          histories[platforms[index]] = result.value.data;
        }
      });
      
      return {
        success: true,
        data: histories,
      };
    } catch (error) {
      console.error('Get all price histories error:', error);
      return {
        success: false,
        error: 'Failed to load price histories',
      };
    }
  },

  /**
   * Get cross-platform same-product variants and availability.
   *
   * @param {string} productId - Product UUID
   * @returns {Promise<Object>} API response
   */
  getCrossPlatformVariants: async (productId) => {
    try {
      if (!productId) {
        return {
          success: false,
          error: 'Product ID is required',
        };
      }

      const response = await api.get(`${API.ENDPOINTS.PRODUCT_DETAIL}/${productId}/cross-platform-variants`);

      return {
        success: true,
        data: response.data,
      };
    } catch (error) {
      console.error('Cross-platform variants API error:', error);

      if (error.response) {
        const status = error.response.status;
        const message = error.response.data?.detail || error.response.data?.message;

        switch (status) {
          case 404:
            return { success: false, error: 'Cross-platform data not available' };
          case 401:
            return { success: false, error: 'Please login again' };
          default:
            return { success: false, error: message || 'Failed to load cross-platform data' };
        }
      }

      return {
        success: false,
        error: error.message || 'Network error. Check your connection.',
      };
    }
  },
};

export default productAPI;