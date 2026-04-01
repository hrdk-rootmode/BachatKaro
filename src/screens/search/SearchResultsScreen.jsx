// ============================================
// DEALHUNT APP - SEARCH RESULTS SCREEN
// Part 3: Watchlist Integration Complete
// ============================================

import React, { useState, useEffect, useCallback, useMemo } from 'react';
import {
  View,
  Text,
  StyleSheet,
  FlatList,
  TouchableOpacity,
  ActivityIndicator,
  RefreshControl,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useNavigation, useRoute } from '@react-navigation/native';
import { useDispatch, useSelector } from 'react-redux';
import { Ionicons } from '@expo/vector-icons';

// Components
import SearchBar from '../../components/SearchBar';
import ProductCard from '../../components/ProductCard';
import EmptyState from '../../components/common/EmptyState';
import { SkeletonGrid } from '../../components/common/SkeletonCard';
import FilterModal from './FilterModal';

// Redux
import {
  searchProducts,
  setFilters,
  clearResults,
  selectResults,
  selectTotalResults,
  selectIsSearching,
  selectSearchError,
  selectFilters,
} from '../../store/searchSlice';

// Watchlist - batch check for performance
import { batchCheckWatchlist } from '../../store/watchlistSlice';

// Utils
import { COLORS } from '../../utils/constants';

// Sort options
const SORT_OPTIONS = [
  { key: 'relevance', label: 'Relevance' },
  { key: 'price_low', label: 'Price: Low to High' },
  { key: 'price_high', label: 'Price: High to Low' },
  { key: 'discount', label: 'Discount %' },
];

// --------------------------------------------
// SEARCH RESULTS SCREEN COMPONENT
// --------------------------------------------

const SearchResultsScreen = () => {
  const navigation = useNavigation();
  const route = useRoute();
  const dispatch = useDispatch();

  // Get query from navigation params
  const initialQuery = route.params?.query || '';

  // Redux state
  const results = useSelector(selectResults);
  const totalResults = useSelector(selectTotalResults);
  const isSearching = useSelector(selectIsSearching);
  const searchError = useSelector(selectSearchError);
  const filters = useSelector(selectFilters);

  // Local state
  const [searchText, setSearchText] = useState(initialQuery);
  const [currentPage, setCurrentPage] = useState(1);
  const [refreshing, setRefreshing] = useState(false);
  const [showFilterModal, setShowFilterModal] = useState(false);
  const [sortBy, setSortBy] = useState('relevance');
  const [showSortMenu, setShowSortMenu] = useState(false);

  // Initial search
  useEffect(() => {
    if (initialQuery) {
      dispatch(searchProducts({ query: initialQuery, filters, page: 1 }));
    }
  }, [initialQuery]);

  // ✅ NEW: Batch check watchlist status when results change
  useEffect(() => {
    if (results && results.length > 0) {
      const productIds = results
        .map(p => p?.id || p?.product_id)
        .filter(Boolean);
      
      if (productIds.length > 0) {
        dispatch(batchCheckWatchlist(productIds));
      }
    }
  }, [results, dispatch]);

  // Handle search
  const handleSearch = useCallback(() => {
    if (!searchText || searchText.length < 2) return;
    
    dispatch(clearResults());
    setCurrentPage(1);
    dispatch(searchProducts({ query: searchText, filters, page: 1 }));
  }, [searchText, filters, dispatch]);

  // Handle refresh
  const handleRefresh = useCallback(async () => {
    setRefreshing(true);
    setCurrentPage(1);
    await dispatch(searchProducts({ query: searchText, filters, page: 1 }));
    setRefreshing(false);
  }, [searchText, filters, dispatch]);

  // Handle load more
  const handleLoadMore = useCallback(() => {
    if (isSearching || results.length >= totalResults) return;
    
    const nextPage = currentPage + 1;
    setCurrentPage(nextPage);
    dispatch(searchProducts({ query: searchText, filters, page: nextPage }));
  }, [isSearching, results.length, totalResults, currentPage, searchText, filters, dispatch]);

  // Handle product tap
  const handleProductPress = useCallback((product) => {
    const pid = product?.id || product?.product_id;
    if (!pid) return;
    navigation.navigate('ProductDetail', { productId: pid });
  }, [navigation]);

  // ✅ REMOVED: handleWishlistPress - now handled internally by ProductCard
  // The ProductCard component uses useProductWatchlist hook directly

  // Handle filter apply
  const handleApplyFilters = useCallback((newFilters) => {
    dispatch(setFilters(newFilters));
    dispatch(clearResults());
    setCurrentPage(1);
    dispatch(searchProducts({ query: searchText, filters: newFilters, page: 1 }));
  }, [searchText, dispatch]);

  // Handle sort change
  const handleSortChange = useCallback((sortKey) => {
    setSortBy(sortKey);
    setShowSortMenu(false);
  }, []);

  // Sort results locally
  const sortedResults = useMemo(() => {
    if (!results || sortBy === 'relevance') return results;
    
    return [...results].sort((a, b) => {
      const priceA = parseFloat(a.best_price) || 0;
      const priceB = parseFloat(b.best_price) || 0;
      const discountA = a.listings?.[0]?.discount_percentage || 0;
      const discountB = b.listings?.[0]?.discount_percentage || 0;

      switch (sortBy) {
        case 'price_low':
          return priceA - priceB;
        case 'price_high':
          return priceB - priceA;
        case 'discount':
          return discountB - discountA;
        default:
          return 0;
      }
    });
  }, [results, sortBy]);

  // Render product card
  // ✅ UPDATED: Removed onWishlistPress - ProductCard handles it internally
  const renderProductCard = useCallback(({ item, index }) => (
    <View style={[styles.productCardContainer, index % 2 === 0 ? styles.leftCard : styles.rightCard]}>
      <ProductCard
        product={item}
        onPress={handleProductPress}
      />
    </View>
  ), [handleProductPress]);

  // Render header
  const renderHeader = useCallback(() => (
    <View style={styles.resultsInfo}>
      <Text style={styles.resultsCount}>
        {totalResults} {totalResults === 1 ? 'result' : 'results'} found
      </Text>
    </View>
  ), [totalResults]);

  // Render footer
  const renderFooter = useCallback(() => {
    if (!isSearching || currentPage === 1) return null;
    
    return (
      <View style={styles.loadingFooter}>
        <ActivityIndicator size="small" color={COLORS.primary} />
        <Text style={styles.loadingText}>Loading more...</Text>
      </View>
    );
  }, [isSearching, currentPage]);

  // Render empty state
  const renderEmptyState = () => {
    if (isSearching && currentPage === 1) {
      return <SkeletonGrid count={6} />;
    }

    if (searchError) {
      return (
        <EmptyState
          icon="alert-circle-outline"
          title="Something went wrong"
          subtitle={searchError}
          buttonTitle="Retry"
          onButtonPress={handleSearch}
        />
      );
    }

    return (
      <EmptyState
        emoji="🔍"
        title="No products found"
        subtitle={`We couldn't find any products matching "${searchText}". Try different keywords.`}
        buttonTitle="Clear Search"
        onButtonPress={() => {
          setSearchText('');
          navigation.goBack();
        }}
      />
    );
  };

  // Key extractor - memoized
  const keyExtractor = useCallback((item, index) => {
    const baseId = item?.product_id ?? item?.id ?? 'product';
    return `${String(baseId)}-${index}`;
  }, []);

  return (
    <SafeAreaView style={styles.container} edges={['top']}>
      {/* Header */}
      <View style={styles.header}>
        {/* Back Button + Search Bar */}
        <View style={styles.searchRow}>
          <TouchableOpacity
            style={styles.backButton}
            onPress={() => navigation.goBack()}
          >
            <Ionicons name="arrow-back" size={24} color={COLORS.textPrimary} />
          </TouchableOpacity>
          
          <View style={styles.searchBarWrapper}>
            <SearchBar
              value={searchText}
              onChangeText={setSearchText}
              onSubmit={handleSearch}
              isLoading={isSearching && currentPage === 1}
              placeholder="Search..."
            />
          </View>
        </View>

        {/* Sort & Filter Bar */}
        <View style={styles.actionBar}>
          {/* Sort Button */}
          <TouchableOpacity
            style={styles.actionButton}
            onPress={() => setShowSortMenu(!showSortMenu)}
          >
            <Ionicons name="swap-vertical" size={18} color={COLORS.gray600} />
            <Text style={styles.actionButtonText}>
              {SORT_OPTIONS.find(o => o.key === sortBy)?.label || 'Sort'}
            </Text>
            <Ionicons 
              name={showSortMenu ? "chevron-up" : "chevron-down"} 
              size={16} 
              color={COLORS.gray600} 
            />
          </TouchableOpacity>

          {/* Filter Button */}
          <TouchableOpacity
            style={styles.actionButton}
            onPress={() => setShowFilterModal(true)}
          >
            <Ionicons name="filter-outline" size={18} color={COLORS.gray600} />
            <Text style={styles.actionButtonText}>Filter</Text>
          </TouchableOpacity>
        </View>

        {/* Sort Dropdown */}
        {showSortMenu && (
          <View style={styles.sortDropdown}>
            {SORT_OPTIONS.map((option) => (
              <TouchableOpacity
                key={option.key}
                style={[
                  styles.sortOption,
                  sortBy === option.key && styles.sortOptionActive,
                ]}
                onPress={() => handleSortChange(option.key)}
              >
                <Text
                  style={[
                    styles.sortOptionText,
                    sortBy === option.key && styles.sortOptionTextActive,
                  ]}
                >
                  {option.label}
                </Text>
                {sortBy === option.key && (
                  <Ionicons name="checkmark" size={18} color={COLORS.primary} />
                )}
              </TouchableOpacity>
            ))}
          </View>
        )}
      </View>

      {/* Results Grid */}
      {sortedResults.length > 0 ? (
        <FlatList
          data={sortedResults}
          renderItem={renderProductCard}
          keyExtractor={keyExtractor}
          numColumns={2}
          columnWrapperStyle={styles.gridRow}
          contentContainerStyle={styles.gridContent}
          ListHeaderComponent={renderHeader}
          ListFooterComponent={renderFooter}
          onEndReached={handleLoadMore}
          onEndReachedThreshold={0.3}
          refreshControl={
            <RefreshControl
              refreshing={refreshing}
              onRefresh={handleRefresh}
              colors={[COLORS.primary]}
              tintColor={COLORS.primary}
            />
          }
          showsVerticalScrollIndicator={false}
          nestedScrollEnabled
          keyboardShouldPersistTaps="handled"
          // Performance optimizations
          removeClippedSubviews={true}
          maxToRenderPerBatch={10}
          windowSize={10}
          initialNumToRender={6}
        />
      ) : (
        renderEmptyState()
      )}

      {/* Filter Modal */}
      <FilterModal
        visible={showFilterModal}
        onClose={() => setShowFilterModal(false)}
        filters={filters}
        onApply={handleApplyFilters}
      />
    </SafeAreaView>
  );
};

// --------------------------------------------
// STYLES
// --------------------------------------------

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: COLORS.background,
  },

  header: {
    backgroundColor: COLORS.white,
    borderBottomWidth: 1,
    borderBottomColor: COLORS.gray100,
    paddingBottom: 8,
  },

  searchRow: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 16,
    paddingTop: 8,
  },

  backButton: {
    padding: 8,
    marginRight: 8,
  },

  searchBarWrapper: {
    flex: 1,
  },

  actionBar: {
    flexDirection: 'row',
    paddingHorizontal: 16,
    paddingTop: 12,
    gap: 12,
  },

  actionButton: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 14,
    paddingVertical: 8,
    backgroundColor: COLORS.gray50,
    borderRadius: 20,
    borderWidth: 1,
    borderColor: COLORS.gray200,
  },

  actionButtonText: {
    fontSize: 13,
    color: COLORS.gray600,
    marginLeft: 6,
    marginRight: 4,
    fontWeight: '500',
  },

  sortDropdown: {
    position: 'absolute',
    top: 110,
    left: 16,
    right: 16,
    backgroundColor: COLORS.white,
    borderRadius: 12,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.15,
    shadowRadius: 12,
    elevation: 8,
    zIndex: 1000,
  },

  sortOption: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingHorizontal: 16,
    paddingVertical: 14,
    borderBottomWidth: 1,
    borderBottomColor: COLORS.gray100,
  },

  sortOptionActive: {
    backgroundColor: COLORS.primaryLight + '10',
  },

  sortOptionText: {
    fontSize: 14,
    color: COLORS.textPrimary,
  },

  sortOptionTextActive: {
    color: COLORS.primary,
    fontWeight: '600',
  },

  resultsInfo: {
    paddingHorizontal: 8,
    paddingVertical: 12,
  },

  resultsCount: {
    fontSize: 14,
    color: COLORS.textSecondary,
  },

  gridContent: {
    padding: 8,
    paddingBottom: 20,
    flexGrow: 1,
  },

  gridRow: {
    justifyContent: 'space-between',
  },

  productCardContainer: {
    width: '48.5%',
    paddingVertical: 8,
  },

  leftCard: {
    paddingRight: 4,
  },

  rightCard: {
    paddingLeft: 4,
  },

  loadingFooter: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: 20,
  },

  loadingText: {
    fontSize: 14,
    color: COLORS.textSecondary,
    marginLeft: 8,
  },
});

export default SearchResultsScreen;