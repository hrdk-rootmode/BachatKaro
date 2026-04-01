// ============================================
// DEALHUNT APP - USE SEARCH HOOK
// Part 3: Fixed AsyncStorage Import
// ============================================

import { useCallback, useEffect, useRef, useState } from 'react';
import { useDispatch, useSelector } from 'react-redux';

// ✅ FIX: Correct AsyncStorage import
import AsyncStorage from '@react-native-async-storage/async-storage';

import {
  searchProducts,
  searchByUrl,
  fetchTrending,
  fetchProductDetails,
  fetchPriceHistory,
  clearResults,
  clearProductDetails,
  clearPriceHistory,
  selectSearchResults,
  selectSearchStatus,
  selectSearchError,
  selectTrendingProducts,
  selectTrendingStatus,
  selectSelectedProduct,
  selectProductDetailStatus,
  selectPriceHistory,
  selectPriceHistoryStatus,
} from '../store/searchSlice';

const RECENT_SEARCHES_KEY = '@dealhunt_recent_searches';
const MAX_RECENT_SEARCHES = 10;

// ============================================
// USE SEARCH RESULTS HOOK
// ============================================

export const useSearchResults = (query, filters = {}, page = 1) => {
  const dispatch = useDispatch();
  const debounceTimer = useRef(null);

  const results = useSelector(selectSearchResults);
  const status = useSelector(selectSearchStatus);
  const error = useSelector(selectSearchError);

  // Debounced search
  const performSearch = useCallback(
    (searchQuery, searchFilters = {}, searchPage = 1) => {
      // Clear previous timeout
      if (debounceTimer.current) {
        clearTimeout(debounceTimer.current);
      }

      // Set new timeout for debounced search
      debounceTimer.current = setTimeout(() => {
        if (searchQuery && searchQuery.trim().length >= 2) {
          dispatch(
            searchProducts({
              query: searchQuery,
              filters: searchFilters,
              page: searchPage,
            })
          );

          // Save to recent searches
          saveRecentSearch(searchQuery);
        }
      }, 300); // 300ms debounce
    },
    [dispatch]
  );

  // Auto-search when query changes
  useEffect(() => {
    if (query && query.trim().length >= 2) {
      performSearch(query, filters, page);
    }
  }, [query, filters, page, performSearch]);

  return {
    results,
    status,
    error,
    isLoading: status === 'loading',
    isEmpty: status === 'succeeded' && results.length === 0,
  };
};

// ============================================
// USE TRENDING HOOK
// ============================================

export const useTrendingProducts = () => {
  const dispatch = useDispatch();

  const trendingProducts = useSelector(selectTrendingProducts);
  const status = useSelector(selectTrendingStatus);

  // Load trending on mount
  useEffect(() => {
    if (!trendingProducts || trendingProducts.length === 0) {
      dispatch(fetchTrending());
    }
  }, [dispatch, trendingProducts]);

  return {
    products: trendingProducts,
    status,
    isLoading: status === 'loading',
    isEmpty: status === 'succeeded' && trendingProducts.length === 0,
  };
};

// ============================================
// USE PRODUCT DETAIL HOOK
// ============================================

export const useProductDetail = (productId) => {
  const dispatch = useDispatch();

  const product = useSelector(selectSelectedProduct);
  const status = useSelector(selectProductDetailStatus);
  const priceHistory = useSelector(selectPriceHistory);
  const priceHistoryStatus = useSelector(selectPriceHistoryStatus);

  // Load product details
  const loadProduct = useCallback(
    (id) => {
      if (id) {
        dispatch(fetchProductDetails({ productId: id }));
      }
    },
    [dispatch]
  );

  // Load price history
  const loadPriceHistory = useCallback(
    (id, platform, days = 120) => {
      if (id) {
        dispatch(
          fetchPriceHistory({
            productId: id,
            platform,
            days,
          })
        );
      }
    },
    [dispatch]
  );

  // Auto-load product on mount
  useEffect(() => {
    if (productId) {
      loadProduct(productId);
    }
  }, [productId, loadProduct]);

  // Clear on unmount
  useEffect(() => {
    return () => {
      dispatch(clearProductDetails());
      dispatch(clearPriceHistory());
    };
  }, [dispatch]);

  return {
    product,
    status,
    isLoading: status === 'loading',
    priceHistory,
    priceHistoryStatus,
    isPriceHistoryLoading: priceHistoryStatus === 'loading',
    loadProduct,
    loadPriceHistory,
  };
};

// ============================================
// USE RECENT SEARCHES HOOK
// ============================================

export const useRecentSearches = () => {
  const [recentSearches, setRecentSearches] = useState([]);

  // Load recent searches on mount
  useEffect(() => {
    const loadSearches = async () => {
      try {
        const searches = await AsyncStorage.getItem(RECENT_SEARCHES_KEY);
        const searchList = searches ? JSON.parse(searches) : [];
        setRecentSearches(searchList);
      } catch (error) {
        console.error('Error loading recent searches:', error);
        setRecentSearches([]);
      }
    };
    
    loadSearches();
  }, []);

  // Reload function
  const reload = useCallback(async () => {
    try {
      const searches = await AsyncStorage.getItem(RECENT_SEARCHES_KEY);
      const searchList = searches ? JSON.parse(searches) : [];
      setRecentSearches(searchList);
    } catch (error) {
      console.error('Error reloading recent searches:', error);
    }
  }, []);

  return {
    recentSearches,
    addSearch: (query) => saveRecentSearch(query),
    clearAll: clearRecentSearches,
    reload,
  };
};

// ============================================
// HELPER FUNCTIONS
// ============================================

/**
 * Save search query to recent searches
 */
const saveRecentSearch = async (query) => {
  try {
    if (!query || query.trim().length < 2) return;

    const trimmedQuery = query.trim();
    const searches = await AsyncStorage.getItem(RECENT_SEARCHES_KEY);
    let searchList = searches ? JSON.parse(searches) : [];

    // Remove duplicate if exists
    searchList = searchList.filter((s) => s.toLowerCase() !== trimmedQuery.toLowerCase());

    // Add to beginning
    searchList.unshift(trimmedQuery);

    // Keep only max items
    searchList = searchList.slice(0, MAX_RECENT_SEARCHES);

    await AsyncStorage.setItem(RECENT_SEARCHES_KEY, JSON.stringify(searchList));
  } catch (error) {
    console.error('Error saving recent search:', error);
  }
};

/**
 * Load recent searches from storage
 */
const loadRecentSearches = async () => {
  try {
    const searches = await AsyncStorage.getItem(RECENT_SEARCHES_KEY);
    return searches ? JSON.parse(searches) : [];
  } catch (error) {
    console.error('Error loading recent searches:', error);
    return [];
  }
};

/**
 * Clear all recent searches
 */
const clearRecentSearches = async () => {
  try {
    await AsyncStorage.removeItem(RECENT_SEARCHES_KEY);
  } catch (error) {
    console.error('Error clearing recent searches:', error);
  }
};

/**
 * Search by URL - extracts product from URL
 */
export const useSearchByUrl = () => {
  const dispatch = useDispatch();
  const status = useSelector(selectSearchStatus);
  const results = useSelector(selectSearchResults);

  const searchUrl = useCallback(
    (url) => {
      if (url) {
        dispatch(searchByUrl({ url }));
      }
    },
    [dispatch]
  );

  return {
    searchUrl,
    results,
    status,
    isLoading: status === 'loading',
  };
};

// ============================================
// EXPORT GROUP HOOKS
// ============================================

/**
 * Complete search functionality hook
 * Includes: search, trending, product detail, recent searches
 */
export const useSearch = () => {
  const dispatch = useDispatch();

  // Search results
  const results = useSelector(selectSearchResults);
  const searchStatus = useSelector(selectSearchStatus);
  const searchError = useSelector(selectSearchError);

  // Trending
  const trendingProducts = useSelector(selectTrendingProducts);
  const trendingStatus = useSelector(selectTrendingStatus);

  // Product detail
  const selectedProduct = useSelector(selectSelectedProduct);
  const productDetailStatus = useSelector(selectProductDetailStatus);
  const priceHistory = useSelector(selectPriceHistory);
  const priceHistoryStatus = useSelector(selectPriceHistoryStatus);

  // Actions
  const performSearch = useCallback(
    (query, filters = {}, page = 1) => {
      if (query && query.trim().length >= 2) {
        dispatch(searchProducts({ query, filters, page }));
        saveRecentSearch(query);
      }
    },
    [dispatch]
  );

  const loadTrending = useCallback(() => {
    dispatch(fetchTrending());
  }, [dispatch]);

  const loadProductDetail = useCallback((productId) => {
    if (productId) {
      dispatch(fetchProductDetails({ productId }));
    }
  }, [dispatch]);

  const loadPriceHistoryData = useCallback(
    (productId, platform, days = 120) => {
      if (productId) {
        dispatch(fetchPriceHistory({ productId, platform, days }));
      }
    },
    [dispatch]
  );

  const clearSearch = useCallback(() => {
    dispatch(clearResults());
  }, [dispatch]);

  const clearDetail = useCallback(() => {
    dispatch(clearProductDetails());
    dispatch(clearPriceHistory());
  }, [dispatch]);

  return {
    // Search
    searchResults: results,
    searchStatus,
    searchError,
    performSearch,
    clearSearch,

    // Trending
    trendingProducts,
    trendingStatus,
    loadTrending,

    // Product Detail
    selectedProduct,
    productDetailStatus,
    loadProductDetail,

    // Price History
    priceHistory,
    priceHistoryStatus,
    loadPriceHistory: loadPriceHistoryData,

    // Helpers
    clearDetail,
    isSearchLoading: searchStatus === 'loading',
    isTrendingLoading: trendingStatus === 'loading',
    isProductLoading: productDetailStatus === 'loading',
    isPriceHistoryLoading: priceHistoryStatus === 'loading',
  };
};