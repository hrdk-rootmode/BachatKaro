import React, { useState, useEffect, useCallback, useMemo } from 'react';
import {
  View, Text, StyleSheet, FlatList, TouchableOpacity,
  ActivityIndicator, RefreshControl, StatusBar,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useNavigation, useRoute } from '@react-navigation/native';
import { Ionicons } from '@expo/vector-icons';
import { useSelector } from 'react-redux';

import ProductCard from '../components/ProductCard';
import { selectThemePalette } from '../store/themeSlice';
import { homeAPI } from '../services/homeApi';
import { searchAPI } from '../services/searchApi';
import { COLORS } from '../utils/constants';

const CategoryProductsScreen = () => {
  const navigation = useNavigation();
  const route = useRoute();
  const themePalette = useSelector(selectThemePalette);

  const { categoryId, categoryTitle, categoryEmoji, categoryQuery, categoryKeywords } = route.params || {};

  const [products, setProducts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState(null);
  const [retryCount, setRetryCount] = useState(0);
  const [sortBy, setSortBy] = useState('relevance'); // relevance, discount, price_low, price_high, newest

  const fetchCategoryProducts = useCallback(async (isRetry = false) => {
    try {
      if (!isRetry) {
        setLoading(true);
        setError(null);
      }
      
      let response = null;

      if (homeAPI && typeof homeAPI.getCategoryProducts === 'function') {
        response = await homeAPI.getCategoryProducts(categoryId);
        const isEmptyCategory = response?.success && Array.isArray(response?.data) && response.data.length === 0;
        if (isEmptyCategory) {
          const fallbackQuery = categoryQuery || categoryTitle || categoryId;
          const fallbackSearch = await searchAPI.searchProducts(
            fallbackQuery,
            {},
            1
          );
          if (fallbackSearch?.success) {
            response = {
              success: true,
              data: Array.isArray(fallbackSearch?.data?.products) ? fallbackSearch.data.products : [],
            };
          }
        }
      } else {
        // Fallback for stale bundles where homeAPI object is missing this method.
        const fallbackQuery = categoryQuery || categoryTitle || categoryId;
        const fallbackSearch = await searchAPI.searchProducts(
          fallbackQuery,
          {},
          1
        );
        if (fallbackSearch?.success) {
          response = {
            success: true,
            data: Array.isArray(fallbackSearch?.data?.products) ? fallbackSearch.data.products : [],
          };
        } else {
          response = fallbackSearch;
        }
      }
      
      if (response?.success && Array.isArray(response.data)) {
        setProducts(response.data);
        setError(null);
        setRetryCount(0);
        
        // Log analytics
        console.log(`Category View: ${categoryTitle} (${response.data.length} products)`);
      } else {
        setProducts([]);
        setError(response?.error || 'Failed to load products');
      }
    } catch (err) {
      console.error('Error fetching category products:', err);
      setProducts([]);
      setError(err?.message || 'Network error. Please try again.');
    } finally {
      setLoading(false);
    }
  }, [categoryId, categoryTitle, categoryQuery]);

  useEffect(() => {
    fetchCategoryProducts();
  }, [fetchCategoryProducts]);

  const onRefresh = useCallback(async () => {
    setRefreshing(true);
    await fetchCategoryProducts();
    setRefreshing(false);
  }, [fetchCategoryProducts]);

  const handleRetry = useCallback(() => {
    setRetryCount(prev => prev + 1);
    fetchCategoryProducts(true);
  }, [fetchCategoryProducts]);

  const sortedProducts = useMemo(() => {
    const sorted = [...products];
    
    switch (sortBy) {
      case 'discount':
        return sorted.sort((a, b) => (b.discount_percentage || 0) - (a.discount_percentage || 0));
      case 'price_low':
        return sorted.sort((a, b) => (a.best_price || 0) - (b.best_price || 0));
      case 'price_high':
        return sorted.sort((a, b) => (b.best_price || 0) - (a.best_price || 0));
      case 'newest':
        return sorted.sort((a, b) => {
          const dateA = new Date(a.last_updated_at || a.created_at || 0).getTime();
          const dateB = new Date(b.last_updated_at || b.created_at || 0).getTime();
          return dateB - dateA;
        });
      case 'relevance':
      default:
        return sorted;
    }
  }, [products, sortBy]);

  const handleProductPress = useCallback((product) => {
    const pid = product?.id || product?.product_id;
    if (!pid) return;
    
    // Log analytics
    console.log(`Product Click: ${product?.title} from ${categoryTitle}`);
    
    navigation.navigate('ProductDetail', { productId: pid });
  }, [navigation, categoryTitle]);

  const handleSortChange = useCallback((newSort) => {
    setSortBy(newSort);
    // Log analytics
    console.log(`Sort Changed: ${newSort} in ${categoryTitle}`);
  }, [categoryTitle]);

  const renderSortOption = (value, label) => (
    <TouchableOpacity
      key={value}
      style={[
        styles.sortOption,
        sortBy === value && styles.sortOptionActive,
        { borderColor: sortBy === value ? (themePalette.primary || COLORS.primary) : COLORS.gray200 }
      ]}
      onPress={() => handleSortChange(value)}
      activeOpacity={0.7}
    >
      <Text style={[
        styles.sortOptionText,
        sortBy === value && styles.sortOptionTextActive,
        { color: sortBy === value ? (themePalette.primary || COLORS.primary) : COLORS.textSecondary }
      ]}>
        {label}
      </Text>
    </TouchableOpacity>
  );

  const renderProduct = ({ item }) => (
    <ProductCard product={item} onPress={() => handleProductPress(item)} />
  );

  const renderHeader = () => (
    <View style={styles.headerContent}>
      <View style={styles.sortContainer}>
        <Text style={styles.sortLabel}>Sort by:</Text>
        <View style={styles.sortOptions}>
          {renderSortOption('relevance', 'Relevance')}
          {renderSortOption('discount', 'Discount')}
          {renderSortOption('price_low', 'Price: Low to High')}
          {renderSortOption('price_high', 'Price: High to Low')}
          {renderSortOption('newest', 'Newest')}
        </View>
      </View>
      <Text style={styles.resultCount}>
        {sortedProducts.length} {sortedProducts.length === 1 ? 'product' : 'products'} found
      </Text>
    </View>
  );

  const renderEmpty = () => {
    if (error) {
      return (
        <View style={styles.emptyContainer}>
          <Ionicons name="alert-circle-outline" size={64} color={COLORS.error} />
          <Text style={styles.emptyTitle}>Oops! Something went wrong</Text>
          <Text style={styles.emptySubtitle}>{error}</Text>
          <TouchableOpacity 
            style={[styles.retryButton, { backgroundColor: themePalette.primary || COLORS.primary }]}
            onPress={handleRetry}
            activeOpacity={0.8}
          >
            <Ionicons name="refresh" size={20} color={COLORS.white} />
            <Text style={styles.retryButtonText}>Retry</Text>
          </TouchableOpacity>
          {retryCount > 0 && (
            <Text style={styles.retryCount}>Retry attempt: {retryCount}</Text>
          )}
        </View>
      );
    }

    return (
      <View style={styles.emptyContainer}>
        <Ionicons name="search-outline" size={64} color={COLORS.gray300} />
        <Text style={styles.emptyTitle}>No products found</Text>
        <Text style={styles.emptySubtitle}>
          We couldn't find any products in this category right now.
          {'\n'}Try refreshing or check back later!
        </Text>
        <TouchableOpacity 
          style={[styles.retryButton, { backgroundColor: themePalette.primary || COLORS.primary }]}
          onPress={onRefresh}
          activeOpacity={0.8}
        >
          <Ionicons name="refresh" size={20} color={COLORS.white} />
          <Text style={styles.retryButtonText}>Refresh</Text>
        </TouchableOpacity>
      </View>
    );
  };

  return (
    <SafeAreaView 
      style={[styles.container, { backgroundColor: themePalette.background || COLORS.gray50 }]} 
      edges={['top']}
    >
      <StatusBar barStyle="dark-content" backgroundColor={themePalette.surface || COLORS.white} />
      
      {/* Header */}
      <View style={[styles.header, { backgroundColor: themePalette.surface || COLORS.white, borderBottomColor: themePalette.border || COLORS.gray100 }]}>
        <TouchableOpacity onPress={() => navigation.goBack()} style={styles.backButton}>
          <Ionicons name="arrow-back" size={24} color={themePalette.text || COLORS.textPrimary} />
        </TouchableOpacity>
        <View style={styles.headerTitleContainer}>
          <Text style={[styles.headerTitle, { color: themePalette.text || COLORS.textPrimary }]}>
            {categoryEmoji} {categoryTitle}
          </Text>
        </View>
        <View style={styles.headerRight} />
      </View>

      {loading && !refreshing ? (
        <View style={styles.loadingContainer}>
          <ActivityIndicator size="large" color={themePalette.primary || COLORS.primary} />
          <Text style={styles.loadingText}>Loading {categoryTitle.toLowerCase()}...</Text>
          <Text style={styles.loadingSubtext}>Finding the best deals for you</Text>
        </View>
      ) : (
        <FlatList
          data={sortedProducts}
          renderItem={renderProduct}
          keyExtractor={(item, index) => `${item?.id || item?.product_id || index}`}
          ListHeaderComponent={renderHeader}
          ListEmptyComponent={renderEmpty}
          contentContainerStyle={styles.listContent}
          showsVerticalScrollIndicator={false}
          refreshControl={
            <RefreshControl
              refreshing={refreshing}
              onRefresh={onRefresh}
              colors={[themePalette.primary || COLORS.primary]}
              tintColor={themePalette.primary || COLORS.primary}
            />
          }
        />
      )}
    </SafeAreaView>
  );
};

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: COLORS.gray50,
  },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 16,
    paddingVertical: 12,
    backgroundColor: COLORS.white,
    borderBottomWidth: 1,
    borderBottomColor: COLORS.gray100,
  },
  backButton: {
    padding: 4,
  },
  headerTitleContainer: {
    flex: 1,
    alignItems: 'center',
  },
  headerTitle: {
    fontSize: 18,
    fontWeight: '700',
    color: COLORS.textPrimary,
  },
  headerRight: {
    width: 32,
  },
  loadingContainer: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    paddingHorizontal: 40,
  },
  loadingText: {
    marginTop: 16,
    fontSize: 16,
    fontWeight: '600',
    color: COLORS.textPrimary,
  },
  loadingSubtext: {
    marginTop: 8,
    fontSize: 13,
    color: COLORS.textSecondary,
    textAlign: 'center',
  },
  listContent: {
    paddingBottom: 20,
  },
  headerContent: {
    padding: 16,
    backgroundColor: COLORS.white,
    marginBottom: 8,
  },
  sortContainer: {
    marginBottom: 12,
  },
  sortLabel: {
    fontSize: 14,
    fontWeight: '600',
    color: COLORS.textPrimary,
    marginBottom: 8,
  },
  sortOptions: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 8,
  },
  sortOption: {
    paddingHorizontal: 12,
    paddingVertical: 6,
    borderRadius: 16,
    borderWidth: 1,
    borderColor: COLORS.gray200,
    backgroundColor: COLORS.white,
  },
  sortOptionActive: {
    backgroundColor: COLORS.primary + '10',
  },
  sortOptionText: {
    fontSize: 12,
    fontWeight: '500',
    color: COLORS.textSecondary,
  },
  sortOptionTextActive: {
    fontWeight: '600',
    color: COLORS.primary,
  },
  resultCount: {
    fontSize: 13,
    color: COLORS.textSecondary,
    fontWeight: '500',
  },
  emptyContainer: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    paddingVertical: 60,
    paddingHorizontal: 40,
  },
  emptyTitle: {
    fontSize: 18,
    fontWeight: '600',
    color: COLORS.textPrimary,
    marginTop: 16,
  },
  emptySubtitle: {
    fontSize: 14,
    color: COLORS.textSecondary,
    marginTop: 8,
    textAlign: 'center',
    lineHeight: 20,
  },
  retryButton: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    backgroundColor: COLORS.primary,
    paddingHorizontal: 24,
    paddingVertical: 12,
    borderRadius: 8,
    marginTop: 20,
  },
  retryButtonText: {
    color: COLORS.white,
    fontSize: 15,
    fontWeight: '600',
  },
  retryCount: {
    fontSize: 12,
    color: COLORS.textSecondary,
    marginTop: 8,
  },
});

export default CategoryProductsScreen;
