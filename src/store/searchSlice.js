import { createSlice, createAsyncThunk } from '@reduxjs/toolkit';
import { searchAPI, productAPI } from '../services/searchApi';

// ============================================
// ASYNC THUNKS
// ============================================

export const searchProducts = createAsyncThunk(
  'search/searchProducts',
  async ({ query, filters = {}, page = 1 }, { rejectWithValue }) => {
    try {
      const result = await searchAPI.searchProducts(query, filters, page);
      if (!result.success) return rejectWithValue(result.error);
      return result.data;
    } catch (error) {
      return rejectWithValue(error.message || 'Search failed.');
    }
  }
);

export const searchByUrl = createAsyncThunk(
  'search/searchByUrl',
  async (payload, { rejectWithValue }) => {
    try {
      const url = typeof payload === 'string' ? payload : payload?.url;
      const result = await searchAPI.searchByUrl(url);
      if (!result.success) return rejectWithValue(result.error);
      return result.data;
    } catch (error) {
      return rejectWithValue(error.message || 'URL search failed.');
    }
  }
);

export const fetchTrending = createAsyncThunk(
  'search/fetchTrending',
  async (_, { rejectWithValue }) => {
    try {
      const result = await searchAPI.getTrending();
      if (!result.success) return rejectWithValue(result.error);
      return result.data;
    } catch (error) {
      return rejectWithValue(error.message || 'Failed to fetch trending.');
    }
  }
);

export const fetchProductDetails = createAsyncThunk(
  'search/fetchProductDetails',
  async ({ productId }, { rejectWithValue }) => {
    try {
      const result = await productAPI.getProductById(productId);
      if (!result.success) return rejectWithValue(result.error);
      return result.data;
    } catch (error) {
      return rejectWithValue(error.message || 'Failed to fetch product.');
    }
  }
);

export const fetchPriceHistory = createAsyncThunk(
  'search/fetchPriceHistory',
  async ({ productId, platform = 'amazon', days = 120 }, { rejectWithValue }) => {
    try {
      const result = await productAPI.getPriceHistory(productId, platform, days);
      if (!result.success) return rejectWithValue(result.error);
      return result.data;
    } catch (error) {
      return rejectWithValue(error.message || 'Failed to fetch price history.');
    }
  }
);

export const refreshProductPrice = createAsyncThunk(
  'search/refreshProductPrice',
  async ({ productId, platform = null }, { rejectWithValue }) => {
    try {
      const result = await productAPI.refreshProductPrice(productId, platform);
      if (!result.success) return rejectWithValue(result.error);
      return result.data;
    } catch (error) {
      return rejectWithValue(error.message || 'Failed to refresh product price.');
    }
  }
);

// ============================================
// NORMALIZE HELPERS
// ============================================

const normalizeProduct = (product) => {
  if (!product) return null;
  
  // Normalize listings array - ensure all listings have required fields
  const normalizedListings = (product.listings || []).map(listing => ({
    ...listing,
    id: listing.id || listing.listing_id,
    listing_id: listing.listing_id || listing.id,
    // ✅ CRITICAL: Map current_price to price field for backwards compatibility
    current_price: listing.current_price || listing.price,
    price: listing.current_price || listing.price,
    original_price: listing.original_price || listing.originalPrice,
    platform: listing.platform || 'amazon',
    in_stock: listing.in_stock !== undefined ? listing.in_stock : true,
    // ✅ Handle discount field variations
    discount_percentage: listing.discount_percentage || listing.discount_percent || 0,
    discount_percent: listing.discount_percentage || listing.discount_percent || 0,
    rating: listing.rating || null,
    review_count: listing.review_count || 0,
    url: listing.url || listing.product_url,
    product_url: listing.product_url || listing.url,
  }));
  
  return {
    ...product,
    id: product.id || product.product_id,
    product_id: product.product_id || product.id,
    // ✅ Ensure listings is always an array
    listings: normalizedListings.filter(l => l && l.id),
  };
};

const normalizeTrending = (item) => ({
  ...item,
  id: item.product_id || item.id,
  product_id: item.product_id || item.id,
});

// ============================================
// INITIAL STATE
// ============================================

const initialState = {
  // Search
  statusSearch: 'idle',
  results: [],
  totalResults: 0,
  currentPage: 1,
  hasMore: false,
  lastQuery: '',
  filters: {
    minPrice: null,
    maxPrice: null,
    platforms: null,
    sortBy: 'relevance',
    inStockOnly: false,
  },
  searchError: null,
  cacheHit: false,
  searchTimeMs: 0,
  isSearching: false,
  urlSearchResult: null,

  // Trending
  statusTrending: 'idle',
  trending: [],
  trendingError: null,

  // Product Detail
  statusProductDetail: 'idle',
  selectedProduct: null,
  productError: null,
  activeProductId: null,

  // Price History
  statusPriceHistory: 'idle',
  priceHistory: null,
  priceHistoryError: null,
  activePriceHistoryKey: null,

  // UI
  selectedTab: 'search',
};

// ============================================
// SLICE
// ============================================

const searchSlice = createSlice({
  name: 'search',
  initialState,

  reducers: {
    clearResults: (state) => {
      state.results = [];
      state.totalResults = 0;
      state.currentPage = 1;
      state.hasMore = false;
      state.lastQuery = '';
      state.searchError = null;
      state.statusSearch = 'idle';
    },
    clearProductDetails: (state) => {
      state.selectedProduct = null;
      state.productError = null;
      state.statusProductDetail = 'idle';
      state.activeProductId = null;
    },
    clearPriceHistory: (state) => {
      state.priceHistory = null;
      state.priceHistoryError = null;
      state.statusPriceHistory = 'idle';
      state.activePriceHistoryKey = null;
    },
    setSelectedTab: (state, action) => {
      state.selectedTab = action.payload;
    },
    setFilters: (state, action) => {
      state.filters = { ...state.filters, ...action.payload };
    },
    resetFilters: (state) => {
      state.filters = initialState.filters;
    },
  },

  extraReducers: (builder) => {
    // SEARCH PRODUCTS
    builder
      .addCase(searchProducts.pending, (state) => {
        state.statusSearch = 'loading';
        state.isSearching = true;
        state.searchError = null;
      })
      .addCase(searchProducts.fulfilled, (state, action) => {
        state.statusSearch = 'succeeded';
        state.isSearching = false;
        const raw = action.payload.products || [];
        const normalized = raw.map(normalizeProduct);
        
        // If page > 1, append. Otherwise replace.
        if ((action.payload.page || 1) > 1) {
          state.results = [...state.results, ...normalized];
        } else {
          state.results = normalized;
        }
        
        state.totalResults = action.payload.totalResults || 0;
        state.currentPage = action.payload.page || 1;
        state.hasMore = normalized.length >= 20;
        state.lastQuery = action.payload.query;
        state.cacheHit = action.payload.cacheHit || false;
        state.searchTimeMs = action.payload.searchTimeMs || 0;
      })
      .addCase(searchProducts.rejected, (state, action) => {
        state.statusSearch = 'failed';
        state.isSearching = false;
        state.searchError = action.payload;
      });

    // FETCH TRENDING
    builder
      .addCase(fetchTrending.pending, (state) => {
        state.statusTrending = 'loading';
        state.trendingError = null;
      })
      .addCase(fetchTrending.fulfilled, (state, action) => {
        state.statusTrending = 'succeeded';
        state.trending = (action.payload || []).map(normalizeTrending);
      })
      .addCase(fetchTrending.rejected, (state, action) => {
        state.statusTrending = 'failed';
        state.trendingError = action.payload;
      });

    // SEARCH BY URL
    builder
      .addCase(searchByUrl.pending, (state) => {
        state.statusSearch = 'loading';
        state.isSearching = true;
        state.searchError = null;
        state.urlSearchResult = null;
        state.results = [];
        state.totalResults = 0;
      })
      .addCase(searchByUrl.fulfilled, (state, action) => {
        state.statusSearch = 'succeeded';
        state.isSearching = false;
        state.urlSearchResult = action.payload || null;
      })
      .addCase(searchByUrl.rejected, (state, action) => {
        state.statusSearch = 'failed';
        state.isSearching = false;
        state.searchError = action.payload;
      });

    // PRODUCT DETAILS
    builder
      .addCase(fetchProductDetails.pending, (state, action) => {
        state.statusProductDetail = 'loading';
        state.productError = null;
        state.activeProductId = String(action.meta?.arg?.productId || '');
        state.selectedProduct = null;
      })
      .addCase(fetchProductDetails.fulfilled, (state, action) => {
        const requestedProductId = String(action.meta?.arg?.productId || '');
        if (state.activeProductId && requestedProductId !== state.activeProductId) {
          return;
        }
        state.statusProductDetail = 'succeeded';
        state.selectedProduct = action.payload
          ? normalizeProduct(action.payload)
          : null;
      })
      .addCase(fetchProductDetails.rejected, (state, action) => {
        const requestedProductId = String(action.meta?.arg?.productId || '');
        if (state.activeProductId && requestedProductId !== state.activeProductId) {
          return;
        }
        state.statusProductDetail = 'failed';
        state.productError = action.payload;
        state.selectedProduct = null;
      });

    // PRICE HISTORY
    builder
      .addCase(fetchPriceHistory.pending, (state, action) => {
        state.statusPriceHistory = 'loading';
        state.priceHistoryError = null;
        state.activePriceHistoryKey = `${String(action.meta?.arg?.productId || '')}:${String(action.meta?.arg?.platform || 'amazon')}`;
        state.priceHistory = null;
      })
      .addCase(fetchPriceHistory.fulfilled, (state, action) => {
        const requestedKey = `${String(action.meta?.arg?.productId || '')}:${String(action.meta?.arg?.platform || 'amazon')}`;
        if (state.activePriceHistoryKey && requestedKey !== state.activePriceHistoryKey) {
          return;
        }
        state.statusPriceHistory = 'succeeded';
        state.priceHistory = action.payload;
      })
      .addCase(fetchPriceHistory.rejected, (state, action) => {
        const requestedKey = `${String(action.meta?.arg?.productId || '')}:${String(action.meta?.arg?.platform || 'amazon')}`;
        if (state.activePriceHistoryKey && requestedKey !== state.activePriceHistoryKey) {
          return;
        }
        state.statusPriceHistory = 'failed';
        state.priceHistoryError = action.payload;
      })

      // LIVE PRODUCT REFRESH
      .addCase(refreshProductPrice.pending, (state) => {
        state.productError = null;
      })
      .addCase(refreshProductPrice.fulfilled, (state, action) => {
        const refreshedProductId = String(action.payload?.id || action.payload?.product_id || '');
        if (state.activeProductId && refreshedProductId && refreshedProductId !== state.activeProductId) {
          return;
        }
        state.statusProductDetail = 'succeeded';
        state.selectedProduct = action.payload
          ? normalizeProduct(action.payload)
          : state.selectedProduct;
      })
      .addCase(refreshProductPrice.rejected, (state, action) => {
        state.statusProductDetail = 'failed';
        state.productError = action.payload;
      });
  },
});

// ============================================
// SELECTORS
// ============================================

export const selectSearchResults = (s) => s.search.results;
export const selectResults = (s) => s.search.results;
export const selectSearchStatus = (s) => s.search.statusSearch;
export const selectSearchError = (s) => s.search.searchError;
export const selectIsSearching = (s) => s.search.isSearching;
export const selectTotalResults = (s) => s.search.totalResults;
export const selectFilters = (s) => s.search.filters;
export const selectTrendingProducts = (s) => s.search.trending;
export const selectTrendingStatus = (s) => s.search.statusTrending;
export const selectSelectedProduct = (s) => s.search.selectedProduct;
export const selectProductDetailStatus = (s) => s.search.statusProductDetail;
export const selectProductError = (s) => s.search.productError;
export const selectPriceHistory = (s) => s.search.priceHistory;
export const selectPriceHistoryStatus = (s) => s.search.statusPriceHistory;
export const selectPriceHistoryError = (s) => s.search.priceHistoryError;
export const selectHasMore = (s) => s.search.hasMore;
export const selectCurrentPage = (s) => s.search.currentPage;
export const selectCacheHit = (s) => s.search.cacheHit;
export const selectLastSearchQuery = (s) => s.search.lastQuery;
// URL Search aliases
export const selectIsUrlSearching = (s) => s.search.isSearching;
export const selectUrlSearchError = (s) => s.search.searchError;

// ============================================
// EXPORTS
// ============================================

export const {
  clearResults,
  clearProductDetails,
  clearPriceHistory,
  setSelectedTab,
  setFilters,
  resetFilters,
} = searchSlice.actions;

export default searchSlice.reducer;