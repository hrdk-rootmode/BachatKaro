// ============================================
// DEALHUNT APP - SEARCH SCREEN
// ============================================

import React, { useState, useEffect, useCallback } from 'react';
import {
  View,
  Text,
  StyleSheet,
  TextInput,
  ScrollView,
  TouchableOpacity,
  FlatList,
  ActivityIndicator,
  Image,
  Alert,
} from 'react-native';
import { useDispatch, useSelector } from 'react-redux';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';

import { 
  searchProducts, 
  searchByUrl,
  fetchTrending, 
  clearResults,
  selectSearchResults,
  selectSearchStatus,
  selectSearchError,
  selectIsSearching,
  selectTrendingProducts,
  selectTrendingStatus,
} from '../../store/searchSlice';
import { COLORS, APP } from '../../utils/constants';
import { 
  formatPrice, 
  getPlatformBadge,
  getDisplayListingForPrice,
  formatVariantInfo,
  getVariantBadge,
} from '../../utils/formatters';

const URL_PLATFORM_PATTERN = /(amazon\.(in|com)|flipkart\.com|meesho\.com|myntra\.com|nykaa\.com|croma\.com)/i;

const normalizePotentialProductUrl = (value) => {
  const trimmed = String(value || '').trim();
  if (!trimmed || !URL_PLATFORM_PATTERN.test(trimmed)) {
    return null;
  }

  if (/^https?:\/\//i.test(trimmed)) {
    return trimmed;
  }

  return `https://${trimmed}`;
};

const extractProductIdFromUrlResult = (result) => {
  return (
    result?.product_id ||
    result?.source?.product_id ||
    result?.product?.product_id ||
    result?.product?.id ||
    null
  );
};

// ============================================
// SEARCH SCREEN
// ============================================

const SearchScreen = ({ navigation, route }) => {
  const dispatch = useDispatch();

  // Redux state
  const results = useSelector(selectSearchResults) || [];
  const searchStatus = useSelector(selectSearchStatus) || 'idle';
  const searchError = useSelector(selectSearchError);
  const isSearching = useSelector(selectIsSearching) || false;
  const trendingProducts = useSelector(selectTrendingProducts) || [];
  const trendingStatus = useSelector(selectTrendingStatus) || 'idle';

  // Local state - ✅ Initialize from route params if available (category click)
  const [searchQuery, setSearchQuery] = useState(route.params?.initialQuery || '');
  const [showResults, setShowResults] = useState(!!route.params?.initialQuery);
  const [filters, setFilters] = useState({
    minPrice: null,
    maxPrice: null,
    platforms: null,
  });

  const upgradeImageUrl = useCallback((rawUrl) => {
    if (!rawUrl || typeof rawUrl !== 'string') return rawUrl;

    let url = rawUrl;
    url = url.replace(/\._[^.]+_\./g, '._SL500_.');
    url = url.replace(/\/128\/128\//g, '/832/832/');
    url = url.replace(/([?&])q=\d+/g, '$1q=100');
    return url;
  }, []);

  // Load trending products on mount (only once)
  useEffect(() => {
    // Only fetch if we haven't loaded yet (status is 'idle')
    if (trendingStatus === 'idle') {
      dispatch(fetchTrending());
    }
  }, []); // Empty dependency array - run once on mount only

  // ✅ NEW: Auto-search when category query is passed (category click from HomeScreen)
  useEffect(() => {
    const initialQuery = route.params?.initialQuery;
    if (initialQuery && initialQuery.trim().length > 0) {
      setSearchQuery(initialQuery);
      setShowResults(true);
      
      // Automatically trigger search
      dispatch(searchProducts({
        query: initialQuery.trim(),
        filters,
        page: 1,
      }));
    }
  }, [route.params?.initialQuery]);

  // Handle search
  const handleSearch = useCallback(async () => {
    const rawQuery = searchQuery.trim();
    if (!rawQuery || rawQuery.length < 2) {
      Alert.alert('Error', 'Please enter at least 2 characters');
      return;
    }

    setShowResults(true);
    const normalizedUrl = normalizePotentialProductUrl(rawQuery);

    if (normalizedUrl) {
      try {
        const result = await dispatch(searchByUrl(normalizedUrl)).unwrap();
        const productId = extractProductIdFromUrlResult(result);

        if (productId) {
          navigation.navigate('ProductDetail', { productId });
          return;
        }

        Alert.alert(
          'URL Processed',
          'Product was extracted, but details are still syncing. Please retry in a few seconds.'
        );
      } catch (error) {
        const message =
          typeof error === 'string'
            ? error
            : error?.message || 'Unable to fetch product from URL.';
        Alert.alert('URL Search Failed', message);
      }
      return;
    }

    console.log('🔍 Dispatching search for:', rawQuery);
    dispatch(searchProducts({
      query: rawQuery,
      filters,
      page: 1,
    }));
  }, [searchQuery, filters, dispatch, navigation]);

  // Handle product tap
  const handleProductTap = (product) => {
    const pid = product?.id || product?.product_id;
    if (!pid) return;
    navigation.navigate('ProductDetail', { productId: pid });
  };

  // Handle clear search
  const handleClear = () => {
    setSearchQuery('');
    setShowResults(false);
    dispatch(clearResults());
  };

  // Render product card
  const renderProductCard = ({ item }) => {
    // 🔍 DEBUG: Check item structure for key errors
    if (!item?.id) {
      console.error('❌ MISSING ITEM ID:', { 
        item_keys: Object.keys(item || {}),
        item: item 
      });
      // Return empty view if item is invalid
      return <View style={styles.productCard} />;
    }
    
    const displayListing = getDisplayListingForPrice(item) || item.listings?.[0];
    const displayCurrentPrice = displayListing?.current_price || item.best_price;
    const displayOriginalPrice =
      Number(displayListing?.original_price || 0) > Number(displayCurrentPrice || 0)
        ? displayListing?.original_price
        : null;
    const platformBadge = getPlatformBadge(displayListing?.platform || item.best_platform || 'amazon');
    const discount = displayOriginalPrice
      ? Math.round(((displayOriginalPrice - displayCurrentPrice) / displayOriginalPrice) * 100)
      : 0;

    return (
      <TouchableOpacity
        style={styles.productCard}
        onPress={() => handleProductTap(item)}
        activeOpacity={0.7}
      >
        {/* Product Image */}
        <View style={styles.imageContainer}>
          {item.listings?.[0]?.image_url ? (
            <Image
              source={{ uri: upgradeImageUrl(item.listings[0].image_url) }}
              style={styles.productImage}
              resizeMode="cover"
            />
          ) : (
            <View style={styles.placeholderImage}>
              <Ionicons name="image-outline" size={40} color={COLORS.gray400} />
            </View>
          )}

          {/* Discount Badge */}
          {discount > 0 && (
            <View style={styles.discountBadge}>
              <Text style={styles.discountText}>{discount}% OFF</Text>
            </View>
          )}
        </View>

        {/* Product Info */}
        <View style={styles.productInfo}>
          <Text style={styles.productTitle} numberOfLines={2}>
            {item.listings?.[0]?.title || item.title}
          </Text>

          {/* ✅ NEW: Variant Type Badge */}
          {item.variant_type && (
            <View style={styles.variantBadgeSmall}>
              <Text style={[
                styles.variantBadgeTextSmall,
                { color: getVariantBadge(item.variant_type).color }
              ]}>
                {getVariantBadge(item.variant_type).label.split(' ')[0]} {item.variant_type.toUpperCase()}
              </Text>
            </View>
          )}

          {/* ✅ NEW: Variant Info (Storage, Color) */}
          {(item.storage_gb || item.color) && (
            <Text style={styles.variantInfoText} numberOfLines={1}>
              {[
                item.storage_gb ? `${item.storage_gb}GB` : null,
                item.color ? item.color : null,
              ].filter(Boolean).join(' • ')}
            </Text>
          )}

          {/* Rating */}
          {item.listings?.[0]?.rating !== null && item.listings?.[0]?.rating !== undefined && (
            <View style={styles.ratingContainer}>
              <Ionicons name="star" size={14} color="#FFC107" />
              <Text style={styles.rating}>
                {typeof item.listings[0].rating === 'number' ? item.listings[0].rating.toFixed(1) : item.listings[0].rating}
              </Text>
              <Text style={styles.reviewCount}>
                ({item.listings[0].review_count || 0})
              </Text>
            </View>
          )}

          {/* Price */}
          <View style={styles.priceContainer}>
            <Text style={styles.currentPrice}>
              {formatPrice(displayCurrentPrice)}
            </Text>
            {displayOriginalPrice && (
              <Text style={styles.originalPrice}>
                {formatPrice(displayOriginalPrice)}
              </Text>
            )}
          </View>

          {/* Platform Badge */}
          <View style={styles.platformContainer}>
            <View
              style={[
                styles.platformBadge,
                { backgroundColor: platformBadge.color + '20' },
              ]}
            >
              <Text style={{ color: platformBadge.color, fontSize: 12 }}>
                {platformBadge.icon} {platformBadge.name}
              </Text>
            </View>
          </View>
        </View>
      </TouchableOpacity>
    );
  };

  // Render trending carousel
  const renderTrendingItem = ({ item }) => (
    <TouchableOpacity
      style={styles.trendingCard}
      onPress={() => handleProductTap(item)}
      activeOpacity={0.7}
    >
      {item.image_url ? (
        <Image
          source={{ uri: upgradeImageUrl(item.image_url) }}
          style={styles.trendingImage}
          resizeMode="cover"
        />
      ) : (
        <View style={styles.trendingPlaceholder}>
          <Ionicons name="image-outline" size={30} color={COLORS.gray400} />
        </View>
      )}
      <View style={styles.trendingInfo}>
        <Text style={styles.trendingTitle} numberOfLines={2}>
          {item.title}
        </Text>
        <Text style={styles.trendingPrice}>{formatPrice(item.best_price)}</Text>
      </View>
    </TouchableOpacity>
  );

  return (
    <SafeAreaView style={styles.container}>
      {/* Header */}
      <View style={styles.header}>
        <Text style={styles.headerTitle}>🔍 {APP.NAME} Search</Text>
      </View>

      {showResults ? (
        // Results View
        <View style={styles.resultsContainer}>
          {/* Back Button */}
          <TouchableOpacity
            style={styles.backButton}
            onPress={handleClear}
          >
            <Ionicons name="arrow-back" size={24} color={COLORS.primary} />
            <Text style={styles.backButtonText}>Back</Text>
          </TouchableOpacity>

          {/* Search Status */}
          {searchStatus === 'loading' && (
            <View style={styles.loadingContainer}>
              <ActivityIndicator size="large" color={COLORS.primary} />
              <Text style={styles.loadingText}>Searching...</Text>
            </View>
          )}

          {searchError && (
            <View style={styles.errorContainer}>
              <Ionicons name="alert-circle" size={48} color={COLORS.error} />
              <Text style={styles.errorText}>{searchError}</Text>
              <TouchableOpacity
                style={styles.retryButton}
                onPress={handleSearch}
              >
                <Text style={styles.retryButtonText}>Try Again</Text>
              </TouchableOpacity>
            </View>
          )}

          {Array.isArray(results) && results.length > 0 && (
            <>
              <Text style={styles.resultsCount}>
                Found {results.length} products
              </Text>
              <FlatList
                data={results.filter(item => item && item.id)} // 🛡️ Filter out invalid items
                renderItem={renderProductCard}
                keyExtractor={(item, index) => {
                  const key = `product-${item?.id || `index-${index}`}`;
                  console.log(`🔑 Generating key: ${key} for product:`, item?.id);
                  return key;
                }}
                contentContainerStyle={styles.resultsList}
                scrollEnabled
                nestedScrollEnabled
                keyboardShouldPersistTaps="handled"
                ListEmptyComponent={
                  <View style={styles.emptyContainer}>
                    <Text style={styles.emptyText}>No valid products to display</Text>
                  </View>
                }
              />
            </>
          )}

          {searchStatus === 'succeeded' &&
            results.length === 0 &&
            !searchError && (
              <View style={styles.emptyContainer}>
                <Ionicons
                  name="search-outline"
                  size={64}
                  color={COLORS.gray400}
                />
                <Text style={styles.emptyText}>No products found</Text>
                <Text style={styles.emptySubtext}>
                  Try adjusting your search terms
                </Text>
              </View>
            )}
        </View>
      ) : (
        // Search View
        <ScrollView
          style={styles.searchContainer}
          showsVerticalScrollIndicator={false}
        >
          {/* Search Input */}
          <View style={styles.searchInputContainer}>
            <Ionicons name="search" size={20} color={COLORS.gray500} />
            <TextInput
              placeholder="Search products or paste a product URL..."
              placeholderTextColor={COLORS.gray500}
              style={styles.searchInput}
              value={searchQuery}
              onChangeText={setSearchQuery}
              onSubmitEditing={handleSearch}
              returnKeyType="search"
            />
            {searchQuery.length > 0 && (
              <TouchableOpacity onPress={() => setSearchQuery('')}>
                <Ionicons name="close" size={20} color={COLORS.gray500} />
              </TouchableOpacity>
            )}
          </View>

          {/* Search Button */}
          <TouchableOpacity
            style={[
              styles.searchButton,
              !searchQuery.trim() && styles.searchButtonDisabled,
            ]}
            onPress={handleSearch}
            disabled={!searchQuery.trim() || isSearching}
          >
            {isSearching ? (
              <ActivityIndicator color={COLORS.white} />
            ) : (
              <>
                <Ionicons name="search" size={20} color={COLORS.white} />
                <Text style={styles.searchButtonText}>Search</Text>
              </>
            )}
          </TouchableOpacity>

          {/* Trending Section */}
          <View style={styles.trendingSection}>
            <View style={styles.sectionHeader}>
              <Text style={styles.sectionTitle}>🔥 Trending Now</Text>
              {trendingStatus === 'loading' && (
                <ActivityIndicator
                  color={COLORS.primary}
                  size="small"
                />
              )}
            </View>

            {Array.isArray(trendingProducts) && trendingProducts.length > 0 ? (
              <FlatList
                data={trendingProducts.slice(0, 6).filter(item => item && (item.product_id || item.id))} // 🛡️ Filter out invalid items
                renderItem={renderTrendingItem}
                keyExtractor={(item, index) => {
                  const key = `trending-${item?.product_id || item?.id || `index-${index}`}`;
                  return key;
                }}
                horizontal
                scrollEnabled
                showsHorizontalScrollIndicator={false}
                contentContainerStyle={styles.trendingList}
              />
            ) : trendingStatus === 'idle' || trendingStatus === 'loading' ? (
              <View style={styles.trendingLoading}>
                <ActivityIndicator color={COLORS.primary} />
                <Text style={{ marginTop: 8, color: COLORS.textSecondary }}>Loading trending...</Text>
              </View>
            ) : (
              <Text style={styles.noTrendingText}>
                No trending products available
              </Text>
            )}
          </View>

          {/* Tips Section */}
          <View style={styles.tipsSection}>
            <Text style={styles.tipsTitle}>💡 Search Tips</Text>
            <Text style={styles.tipItem}>
              • Be specific: "iPhone 15 Pro" vs "phone"
            </Text>
            <Text style={styles.tipItem}>
              • Use brand names for better results
            </Text>
            <Text style={styles.tipItem}>
              • Include features like "5G" or "256GB"
            </Text>
          </View>
        </ScrollView>
      )}
    </SafeAreaView>
  );
};

// ============================================
// STYLES
// ============================================

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: COLORS.background,
  },

  header: {
    paddingHorizontal: 16,
    paddingVertical: 12,
    borderBottomWidth: 1,
    borderBottomColor: COLORS.gray200,
  },

  headerTitle: {
    fontSize: 20,
    fontWeight: 'bold',
    color: COLORS.textPrimary,
  },

  searchContainer: {
    flex: 1,
    paddingHorizontal: 16,
    paddingVertical: 16,
  },

  searchInputContainer: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: COLORS.gray100,
    borderRadius: 12,
    paddingHorizontal: 12,
    marginBottom: 12,
  },

  searchInput: {
    flex: 1,
    paddingVertical: 12,
    paddingHorizontal: 8,
    fontSize: 16,
    color: COLORS.textPrimary,
  },

  searchButton: {
    flexDirection: 'row',
    backgroundColor: COLORS.primary,
    borderRadius: 12,
    paddingVertical: 14,
    paddingHorizontal: 24,
    justifyContent: 'center',
    alignItems: 'center',
    marginBottom: 24,
  },

  searchButtonDisabled: {
    backgroundColor: COLORS.gray300,
  },

  searchButtonText: {
    color: COLORS.white,
    fontSize: 16,
    fontWeight: '600',
    marginLeft: 8,
  },

  trendingSection: {
    marginBottom: 24,
  },

  sectionHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 12,
  },

  sectionTitle: {
    fontSize: 18,
    fontWeight: '600',
    color: COLORS.textPrimary,
  },

  trendingList: {
    paddingRight: 16,
  },

  trendingCard: {
    width: 150,
    marginRight: 12,
    borderRadius: 12,
    overflow: 'hidden',
    backgroundColor: COLORS.gray100,
  },

  trendingImage: {
    width: '100%',
    height: 100,
  },

  trendingPlaceholder: {
    width: '100%',
    height: 100,
    backgroundColor: COLORS.gray200,
    justifyContent: 'center',
    alignItems: 'center',
  },

  trendingInfo: {
    padding: 8,
  },

  trendingTitle: {
    fontSize: 12,
    fontWeight: '500',
    color: COLORS.textPrimary,
    marginBottom: 4,
  },

  trendingPrice: {
    fontSize: 14,
    fontWeight: '600',
    color: COLORS.primary,
  },

  trendingLoading: {
    paddingVertical: 20,
    justifyContent: 'center',
    alignItems: 'center',
  },

  noTrendingText: {
    color: COLORS.textSecondary,
    textAlign: 'center',
    paddingVertical: 20,
  },

  tipsSection: {
    backgroundColor: COLORS.infoLight,
    borderRadius: 12,
    padding: 12,
    marginBottom: 20,
  },

  tipsTitle: {
    fontSize: 14,
    fontWeight: '600',
    color: COLORS.info,
    marginBottom: 8,
  },

  tipItem: {
    fontSize: 12,
    color: COLORS.info,
    marginVertical: 4,
    lineHeight: 18,
  },

  resultsContainer: {
    flex: 1,
    paddingHorizontal: 16,
  },

  backButton: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingVertical: 12,
  },

  backButtonText: {
    color: COLORS.primary,
    fontSize: 16,
    fontWeight: '600',
    marginLeft: 8,
  },

  loadingContainer: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
  },

  loadingText: {
    marginTop: 12,
    fontSize: 16,
    color: COLORS.textSecondary,
  },

  errorContainer: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    paddingHorizontal: 20,
  },

  errorText: {
    marginTop: 12,
    fontSize: 16,
    color: COLORS.error,
    textAlign: 'center',
    lineHeight: 24,
  },

  retryButton: {
    marginTop: 20,
    backgroundColor: COLORS.primary,
    borderRadius: 8,
    paddingVertical: 10,
    paddingHorizontal: 20,
  },

  retryButtonText: {
    color: COLORS.white,
    fontSize: 14,
    fontWeight: '600',
  },

  resultsCount: {
    fontSize: 14,
    color: COLORS.textSecondary,
    marginBottom: 12,
    marginTop: 12,
  },

  resultsList: {
    paddingBottom: 20,
    flexGrow: 1,
  },

  productCard: {
    backgroundColor: COLORS.white,
    borderRadius: 12,
    marginBottom: 12,
    marginHorizontal: 2,
    overflow: 'hidden',
    elevation: 2,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.1,
    shadowRadius: 4,
  },

  imageContainer: {
    position: 'relative',
    width: '100%',
    height: 132,
  },

  productImage: {
    width: '100%',
    height: '100%',
  },

  placeholderImage: {
    width: '100%',
    height: '100%',
    backgroundColor: COLORS.gray100,
    justifyContent: 'center',
    alignItems: 'center',
  },

  discountBadge: {
    position: 'absolute',
    top: 8,
    right: 8,
    backgroundColor: COLORS.error,
    borderRadius: 6,
    paddingHorizontal: 8,
    paddingVertical: 4,
  },

  discountText: {
    color: COLORS.white,
    fontSize: 12,
    fontWeight: '600',
  },

  productInfo: {
    padding: 12,
  },

  productTitle: {
    fontSize: 14,
    fontWeight: '600',
    color: COLORS.textPrimary,
    marginBottom: 6,
    lineHeight: 20,
  },

  ratingContainer: {
    flexDirection: 'row',
    alignItems: 'center',
    marginBottom: 8,
  },

  rating: {
    marginLeft: 4,
    fontSize: 12,
    fontWeight: '500',
    color: COLORS.textPrimary,
  },

  reviewCount: {
    marginLeft: 4,
    fontSize: 12,
    color: COLORS.textSecondary,
  },

  priceContainer: {
    flexDirection: 'row',
    alignItems: 'center',
    marginBottom: 8,
  },

  currentPrice: {
    fontSize: 16,
    fontWeight: '700',
    color: COLORS.primary,
  },

  originalPrice: {
    marginLeft: 8,
    fontSize: 12,
    color: COLORS.textSecondary,
    textDecorationLine: 'line-through',
  },

  platformContainer: {
    flexDirection: 'row',
  },

  platformBadge: {
    borderRadius: 6,
    paddingHorizontal: 8,
    paddingVertical: 4,
  },

  emptyContainer: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
  },

  emptyText: {
    marginTop: 12,
    fontSize: 18,
    fontWeight: '600',
    color: COLORS.textPrimary,
  },

  emptySubtext: {
    marginTop: 8,
    fontSize: 14,
    color: COLORS.textSecondary,
  },

  // ✅ NEW: Variant Display Styles for Search Cards
  variantBadgeSmall: {
    marginBottom: 6,
    alignSelf: 'flex-start',
  },

  variantBadgeTextSmall: {
    fontSize: 11,
    fontWeight: '600',
  },

  variantInfoText: {
    fontSize: 11,
    color: COLORS.textSecondary,
    marginBottom: 8,
  },
});

export default SearchScreen;
