import { get } from './api';

export const homeAPI = {
  getFeatured: async (limit = 6) => {
    try {
      const response = await get('/home/featured', { limit });
      if (!response.success) return response;

      return {
        success: true,
        data: Array.isArray(response.data) ? response.data : [],
      };
    } catch (error) {
      return {
        success: false,
        error: error?.error || 'Failed to fetch featured products',
      };
    }
  },

  getDeals: async (limit = 20) => {
    try {
      const response = await get('/home/deals', { limit });
      if (!response.success) return response;

      return {
        success: true,
        data: Array.isArray(response.data) ? response.data : [],
      };
    } catch (error) {
      return {
        success: false,
        error: error?.error || 'Failed to fetch home deals',
      };
    }
  },

  getCrossPlatformHighlights: async (limit = 24, minPlatforms = 2) => {
    try {
      const response = await get('/home/cross-platform', {
        limit,
        min_platforms: minPlatforms,
      });
      if (!response.success) return response;

      return {
        success: true,
        data: Array.isArray(response.data) ? response.data : [],
      };
    } catch (error) {
      return {
        success: false,
        error: error?.error || 'Failed to fetch cross-platform highlights',
      };
    }
  },

  getCategories: async () => {
    try {
      const response = await get('/home/categories');
      if (!response.success) return response;

      return {
        success: true,
        data: response.data && typeof response.data === 'object' ? response.data : {},
      };
    } catch (error) {
      return {
        success: false,
        error: error?.error || 'Failed to fetch home categories',
      };
    }
  },

  // ✅ NEW: Cross-platform comparison
  getCrossPlatformVariants: async (productId) => {
    try {
      const response = await get(`/products/${productId}/cross-platform-variants`);
      if (!response.success) return response;

      return {
        success: true,
        data: response.data || {
          product_id: productId,
          title: '',
          brand: '',
          category: '',
          total_platforms: 0,
          total_listings: 0,
          variants: [],
        },
      };
    } catch (error) {
      return {
        success: false,
        error: error?.error || 'Failed to fetch cross-platform comparison',
      };
    }
  },
};

export default homeAPI;
