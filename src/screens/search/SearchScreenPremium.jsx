// ============================================
// DEALHUNT APP - PREMIUM SEARCH SCREEN
// Clean, Luxury Design with New Products & Price Changes
// ============================================

import React, { useState, useEffect, useCallback, useMemo } from 'react';
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
  KeyboardAvoidingView,
  Platform,
  Dimensions,
  Alert,
} from 'react-native';
import { useDispatch, useSelector } from 'react-redux';
import { SafeAreaView, useSafeAreaInsets } from 'react-native-safe-area-context';
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
import { selectUser } from '../../store/authSlice';
import { selectPlans } from '../../store/subscriptionSlice';
import { selectThemePalette } from '../../store/themeSlice';
import { COLORS, APP } from '../../utils/constants';
import { getSearchQuotaSnapshot } from '../../utils/searchQuota';
import { 
  formatPrice, 
  getPlatformBadge,
  getDisplayListingForPrice,
  formatVariantInfo,
  getVariantBadge,
} from '../../utils/formatters';

const { width: SCREEN_WIDTH } = Dimensions.get('window');
const URL_PATTERN = /(amazon\.(in|com)|flipkart\.com|meesho\.com|myntra\.com|nykaa\.com|croma\.com)/i;

// ============================================
// PREMIUM SEARCH SCREEN
// ============================================

const SearchScreenPremium = ({ navigation, route }) => {
  const dispatch = useDispatch();
  const insets = useSafeAreaInsets();
  const scrollViewRef = React.useRef(null);
  const inputRef = React.useRef(null);

  // Redux state
  const results = useSelector(selectSearchResults) || [];
  const searchStatus = useSelector(selectSearchStatus) || 'idle';
  const searchError = useSelector(selectSearchError);
  const isSearching = useSelector(selectIsSearching) || false;
  const trendingProducts = useSelector(selectTrendingProducts) || [];
  const trendingStatus = useSelector(selectTrendingStatus) || 'idle';
  const themePalette = useSelector(selectThemePalette);
  const user = useSelector(selectUser);
  const plans = useSelector(selectPlans);

  // Local state
  const [searchQuery, setSearchQuery] = useState(route.params?.initialQuery || '');
  const [showResults, setShowResults] = useState(!!route.params?.initialQuery);
  const [isInputFocused, setIsInputFocused] = useState(false);
  const lastAlertedErrorRef = React.useRef(null);

  const currentPlan = String(user?.plan || 'free').toLowerCase();
  const planInfo = useMemo(() => {
    const planMap = {};
    if (Array.isArray(plans)) {
      plans.forEach((plan) => {
        if (!plan?.id) return;
        planMap[String(plan.id).toLowerCase()] = plan;
      });
    }

    return planMap[currentPlan] || APP.PLANS[currentPlan.toUpperCase()] || APP.PLANS.FREE;
  }, [plans, currentPlan]);

  const searchQuota = useMemo(() => getSearchQuotaSnapshot({ user, planInfo }), [planInfo, user]);

  const searchErrorText = useMemo(() => {
    if (typeof searchError === 'string') return searchError;
    if (searchError && typeof searchError === 'object') {
      return searchError.message || searchError.detail || searchError.error || 'Search failed.';
    }
    return '';
  }, [searchError]);

  useEffect(() => {
    if (searchStatus === 'failed' && searchErrorText && lastAlertedErrorRef.current !== searchErrorText) {
      lastAlertedErrorRef.current = searchErrorText;
      Alert.alert('Search unavailable', searchErrorText);
    }

    if (searchStatus !== 'failed') {
      lastAlertedErrorRef.current = null;
    }
  }, [searchErrorText, searchStatus]);

  // ============================================
  // GET NEW PRODUCTS (Last 24h)
  // ============================================
  const newProducts = useMemo(() => {
    const now = new Date();
    return (trendingProducts || []).filter(p => {
      const created = p?.created_at ? new Date(p.created_at) : null;
      if (!created) return false;
      const hoursSinceCreated = (now - created) / (1000 * 60 * 60);
      return hoursSinceCreated < 24;
    }).slice(0, 8);
  }, [trendingProducts]);

  // ============================================
  // GET PRICE RECENTLY CHANGED
  // ============================================
  const priceChanged = useMemo(() => {
    return (results || [])
      .filter(p => {
        const change = parseFloat(p?.discount_percentage || 0);
        const updated = p?.last_price_change_at ? new Date(p.last_price_change_at) : null;
        if (!updated) return false;
        const hoursSinceChange = (new Date() - updated) / (1000 * 60 * 60);
        return change >= 5 && hoursSinceChange < 48;
      })
      .sort((a, b) => {
        const aTime = new Date(a?.last_price_change_at || 0);
        const bTime = new Date(b?.last_price_change_at || 0);
        return bTime - aTime;
      })
      .slice(0, 6);
  }, [results]);

  // ============================================
  // HANDLERS
  // ============================================

  const handleSearch = useCallback(() => {
    if (!searchQuery.trim()) return;

    const trimmed = searchQuery.trim();
    const isUrl = URL_PATTERN.test(trimmed);

    if (isUrl) {
      const url = /^https?:\/\//i.test(trimmed) ? trimmed : `https://${trimmed}`;
      dispatch(searchByUrl(url));
    } else {
      dispatch(searchProducts({ query: trimmed, limit: 50 }));
    }

    setShowResults(true);
  }, [searchQuery, dispatch]);

  const handleClear = useCallback(() => {
    setSearchQuery('');
    setShowResults(false);
    dispatch(clearResults());
  }, [dispatch]);

  const handleProductTap = useCallback((product) => {
    const productId = product?.id || product?.product_id;
    if (!productId) return;
    navigation.push('ProductDetail', { productId });
  }, [navigation]);

  const handleInputFocus = () => {
    setIsInputFocused(true);
    // KeyboardAvoidingView will handle positioning automatically
  };

  const handleInputBlur = () => {
    setIsInputFocused(false);
  };

  useEffect(() => {
    if (trendingStatus === 'idle') {
      dispatch(fetchTrending());
    }
  }, [trendingStatus, dispatch]);

  // ============================================
  // RENDER: NEW PRODUCT CARD
  // ============================================
  const renderNewProductCard = ({ item }) => (
    <TouchableOpacity
      style={[
        styles.productCard,
        {
          backgroundColor: themePalette.surface || COLORS.white,
          borderColor: themePalette.border || COLORS.gray200,
        },
      ]}
      onPress={() => handleProductTap(item)}
      activeOpacity={0.8}
    >
      {/* Image */}
      <View style={styles.cardImageContainer}>
        {item.image_url ? (
          <Image
            source={{ uri: item.image_url }}
            style={styles.cardImage}
            resizeMode="cover"
          />
        ) : (
          <View style={[styles.imagePlaceholder, { backgroundColor: themePalette.surfaceMuted || COLORS.gray100 }]}>
            <Ionicons name="image-outline" size={24} color={COLORS.gray400} />
          </View>
        )}
        {/* NEW BADGE */}
        <View style={styles.newBadge}>
          <Text style={styles.newBadgeText}>NEW</Text>
        </View>
      </View>

      {/* Info */}
      <View style={styles.cardInfo}>
        <Text style={[styles.productTitle, { color: themePalette.text || COLORS.textPrimary }]} numberOfLines={2}>
          {item.title}
        </Text>
        <Text style={[styles.productPrice, { color: themePalette.primary || COLORS.primary }]}>
          {formatPrice(item.best_price)}
        </Text>
      </View>
    </TouchableOpacity>
  );

  // ============================================
  // RENDER: PRICE CHANGED CARD
  // ============================================
  const renderPriceChangedCard = ({ item }) => (
    <TouchableOpacity
      style={[
        styles.priceChangeCard,
        {
          backgroundColor: themePalette.surface || COLORS.white,
          borderColor: themePalette.border || COLORS.gray200,
        },
      ]}
      onPress={() => handleProductTap(item)}
      activeOpacity={0.8}
    >
      {/* Image */}
      <View style={styles.smallImageContainer}>
        {item.image_url ? (
          <Image
            source={{ uri: item.image_url }}
            style={styles.smallImage}
            resizeMode="cover"
          />
        ) : (
          <View style={[styles.smallPlaceholder, { backgroundColor: themePalette.surfaceMuted || COLORS.gray100 }]}>
            <Ionicons name="image-outline" size={18} color={COLORS.gray400} />
          </View>
        )}
      </View>

      {/* Info */}
      <View style={styles.priceChangeInfo}>
        <Text style={[styles.priceChangeTitle, { color: themePalette.text || COLORS.textPrimary }]} numberOfLines={2}>
          {item.title}
        </Text>

        {/* Discount Badge */}
        <View style={styles.discountRow}>
          <View style={styles.discountBadge}>
            <Text style={styles.discountText}>
              {Math.round(item.discount_percentage || 0)}% OFF
            </Text>
          </View>
          <Text style={[styles.changedPrice, { color: themePalette.primary || COLORS.primary }]}>
            {formatPrice(item.best_price)}
          </Text>
        </View>
      </View>

      {/* Arrow */}
      <Ionicons name="chevron-forward" size={18} color={COLORS.gray400} />
    </TouchableOpacity>
  );

  // ============================================
  // RENDER: RESULT CARD (When searching)
  // ============================================
  const renderResultCard = ({ item }) => (
    <TouchableOpacity
      style={[
        styles.resultCard,
        {
          backgroundColor: themePalette.surface || COLORS.white,
          borderColor: themePalette.border || COLORS.gray200,
        },
      ]}
      onPress={() => handleProductTap(item)}
      activeOpacity={0.8}
    >
      {item.image_url && (
        <Image
          source={{ uri: item.image_url }}
          style={styles.resultImage}
          resizeMode="cover"
        />
      )}
      <View style={styles.resultInfo}>
        <Text style={[styles.resultTitle, { color: themePalette.text || COLORS.textPrimary }]} numberOfLines={2}>
          {item.title}
        </Text>
        <Text style={[styles.resultPrice, { color: themePalette.primary || COLORS.primary }]}>
          {formatPrice(item.best_price)}
        </Text>
      </View>
    </TouchableOpacity>
  );

  // ============================================
  // RENDER: URL SEARCH RESULT WITH CROSS-PLATFORM
  // ============================================
  const renderURLSearchResult = () => {
    // Check if this is a URL search result (has source and alternatives)
    if (!results || !results.source) return null;

    const urlResult = results;
    const { source, alternatives = [], best_deal = {}, response_origin = 'live_scrape', total_options = 1 } = urlResult;

    if (!source) return null;

    const isBestDeal = best_deal?.platform === source.platform;

    return (
      <View style={styles.section}>
        {/* HEADER WITH ORIGIN BADGE */}
        <View style={styles.urlSearchHeader}>
          <Text style={[styles.sectionHeader, { color: themePalette.text || COLORS.textPrimary }]}>
            Product Found
          </Text>
          <View style={[
            styles.originBadge,
            { backgroundColor: response_origin === 'database' ? '#E3F2FD' : '#F3E5F5' }
          ]}>
            <Ionicons 
              name={response_origin === 'database' ? 'cloud-download' : 'lightning'} 
              size={12} 
              color={response_origin === 'database' ? '#1976D2' : '#7B1FA2'}
            />
            <Text style={[
              styles.originBadgeText,
              { color: response_origin === 'database' ? '#1976D2' : '#7B1FA2' }
            ]}>
              {response_origin === 'database' ? 'From Database' : 'Fresh Scrape'}
            </Text>
          </View>
        </View>

        {/* SOURCE PRODUCT CARD */}
        <View style={[
          styles.sourceProductCard,
          {
            backgroundColor: themePalette.surface || COLORS.white,
            borderColor: isBestDeal ? COLORS.success : themePalette.border || COLORS.gray200,
            borderWidth: isBestDeal ? 2 : 1,
          },
        ]}>
          {/* Image + Badge */}
          <View style={styles.sourceImageContainer}>
            {source.image_url ? (
              <Image
                source={{ uri: source.image_url }}
                style={styles.sourceImage}
                resizeMode="cover"
              />
            ) : (
              <View style={[styles.imagePlaceholder, { backgroundColor: themePalette.surfaceMuted || COLORS.gray100 }]}>
                <Ionicons name="image-outline" size={32} color={COLORS.gray400} />
              </View>
            )}
            {isBestDeal && (
              <View style={styles.bestDealBadge}>
                <Ionicons name="star" size={14} color={COLORS.white} />
                <Text style={styles.bestDealText}>Best</Text>
              </View>
            )}
            <View style={[styles.platformBadge, { backgroundColor: themePalette.primary || COLORS.primary }]}>
              <Text style={styles.platformBadgeText}>{source.platform?.toUpperCase()}</Text>
            </View>
          </View>

          {/* Product Info */}
          <View style={styles.sourceProductInfo}>
            <Text style={[styles.sourceTitle, { color: themePalette.text || COLORS.textPrimary }]} numberOfLines={2}>
              {source.title}
            </Text>
            
            {source.brand && (
              <Text style={[styles.brandText, { color: themePalette.textSecondary || COLORS.textSecondary }]}>
                {source.brand}
              </Text>
            )}

            {/* Price Section */}
            <View style={styles.priceSection}>
              <Text style={[styles.sourcePrice, { color: themePalette.primary || COLORS.primary }]}>
                {formatPrice(source.price)}
              </Text>
              {source.original_price && source.original_price > source.price && (
                <Text style={[styles.originalPrice, { color: themePalette.textSecondary || COLORS.textSecondary }]}>
                  {formatPrice(source.original_price)}
                </Text>
              )}
            </View>

            {/* Rating */}
            {source.rating && (
              <View style={styles.ratingSection}>
                <View style={styles.rating}>
                  {[...Array(5)].map((_, i) => (
                    <Ionicons
                      key={i}
                      name={i < Math.round(source.rating) ? 'star' : 'star-outline'}
                      size={12}
                      color={i < Math.round(source.rating) ? COLORS.warning : COLORS.gray400}
                    />
                  ))}
                </View>
                <Text style={[styles.reviewCount, { color: themePalette.textSecondary || COLORS.textSecondary }]}>
                  {source.review_count} reviews
                </Text>
              </View>
            )}

            {/* Stock Status */}
            <View style={styles.stockStatus}>
              <View style={[styles.stockDot, { backgroundColor: source.in_stock ? COLORS.success : COLORS.error }]} />
              <Text style={[styles.stockText, { color: source.in_stock ? COLORS.success : COLORS.error }]}>
                {source.in_stock ? 'In Stock' : 'Out of Stock'}
              </Text>
            </View>
          </View>
        </View>

        {/* CROSS-PLATFORM ALTERNATIVES */}
        {alternatives && alternatives.length > 0 && (
          <View style={styles.alternativesSection}>
            <Text style={[styles.sectionHeader, { color: themePalette.text || COLORS.textPrimary, marginBottom: 12 }]}>
              Available on {alternatives.length} platform{alternatives.length !== 1 ? 's' : ''}
            </Text>

            {alternatives.map((alt, idx) => {
              const isBest = best_deal?.platform === alt.platform;
              return (
                <TouchableOpacity
                  key={`alt-${idx}`}
                  style={[
                    styles.alternativeCard,
                    {
                      backgroundColor: themePalette.surface || COLORS.white,
                      borderColor: isBest ? COLORS.success : themePalette.border || COLORS.gray200,
                      borderWidth: isBest ? 2 : 1,
                    },
                  ]}
                  activeOpacity={0.8}
                >
                  {/* Platform Badge */}
                  <View style={[styles.altPlatformBadge, { backgroundColor: themePalette.primary || COLORS.primary }]}>
                    <Text style={styles.altPlatformText}>{alt.platform?.toUpperCase()}</Text>
                    {isBest && <Ionicons name="star" size={12} color={COLORS.white} />}
                  </View>

                  {/* Price Info */}
                  <View style={styles.altPriceContainer}>
                    <Text style={[styles.altPrice, { color: themePalette.primary || COLORS.primary }]}>
                      {formatPrice(alt.price)}
                    </Text>
                    {alt.savings > 0 && (
                      <View style={styles.savingsBadge}>
                        <Text style={styles.savingsText}>
                          Save {formatPrice(alt.savings)} ({alt.savings_percent}%)
                        </Text>
                      </View>
                    )}
                  </View>

                  {/* Stock & Rating */}
                  <View style={styles.altMetaInfo}>
                    {alt.rating && (
                      <View style={styles.altRating}>
                        <Ionicons name="star" size={12} color={COLORS.warning} />
                        <Text style={[styles.altRatingText, { color: themePalette.textSecondary || COLORS.textSecondary }]}>
                          {alt.rating}
                        </Text>
                      </View>
                    )}
                    <View style={[styles.stockDot, { backgroundColor: alt.in_stock ? COLORS.success : COLORS.error }]} />
                    <Text style={[styles.stockText, { color: alt.in_stock ? COLORS.success : COLORS.error }]}>
                      {alt.in_stock ? 'In Stock' : 'Out of Stock'}
                    </Text>
                  </View>
                </TouchableOpacity>
              );
            })}
          </View>
        )}

        {/* TOTAL OPTIONS SUMMARY */}
        <View style={[styles.summaryCard, { backgroundColor: themePalette.surfaceMuted || COLORS.gray100 }]}>
          <Ionicons name="checkmark-circle" size={20} color={COLORS.success} />
          <Text style={[styles.summaryText, { color: themePalette.text || COLORS.textPrimary }]}>
            Found on {total_options} platform{total_options !== 1 ? 's' : ''} • Best price: {formatPrice(best_deal.price)}
          </Text>
        </View>
      </View>
    );
  };

  // ============================================
  // RENDER
  // ============================================

  return (
    <SafeAreaView
      style={[
        styles.container,
        { backgroundColor: themePalette.background || COLORS.background },
      ]}
    >
      {/* HEADER - PREMIUM STYLE */}
      <View
        style={[
          styles.header,
          {
            backgroundColor: themePalette.surface || COLORS.white,
            borderBottomColor: themePalette.border || COLORS.gray200,
          },
        ]}
      >
        <View style={styles.headerTop}>
          {showResults && (
            <TouchableOpacity
              onPress={handleClear}
              style={styles.backButtonIcon}
            >
              <Ionicons name="chevron-back" size={24} color={themePalette.primary || COLORS.primary} />
            </TouchableOpacity>
          )}
          <Text style={[styles.headerTitle, { color: themePalette.text || COLORS.textPrimary, flex: 1 }]}>
            ✨ Discover
          </Text>
        </View>

        <View style={styles.quotaPillRow}>
          <View style={[styles.quotaPill, { backgroundColor: themePalette.surfaceMuted || COLORS.gray100 }]}>
            <Ionicons name="search" size={14} color={themePalette.primary || COLORS.primary} />
            <Text style={[styles.quotaPillText, { color: themePalette.text || COLORS.textPrimary }]}>
              {searchQuota.isUnlimited ? 'Unlimited searches' : `${searchQuota.remainingSearches} searches left today`}
            </Text>
          </View>
        </View>
      </View>

      {/* BODY */}
      <KeyboardAvoidingView
        style={styles.bodyWrapper}
        behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
        keyboardVerticalOffset={Platform.OS === 'ios' ? 110 : 20}
      >
        <View style={{ flex: 1 }}>
          <ScrollView
            ref={scrollViewRef}
            style={styles.scrollView}
            contentContainerStyle={[
              styles.scrollContent,
              { paddingBottom: 16 + insets.bottom },
            ]}
            showsVerticalScrollIndicator={false}
            keyboardShouldPersistTaps="handled"
          >
          {showResults ? (
            <>
              {/* SEARCH RESULTS */}
              {searchStatus === 'loading' && (
                <View style={styles.loadingSection}>
                  <ActivityIndicator size="large" color={themePalette.primary || COLORS.primary} />
                  <Text style={[styles.loadingText, { color: themePalette.textSecondary || COLORS.textSecondary }]}>
                    Searching...
                  </Text>
                </View>
              )}

              {searchError && (
                <View style={styles.errorSection}>
                  <Ionicons name="alert-circle" size={48} color={COLORS.error} />
                  <Text style={[styles.errorText, { color: themePalette.text || COLORS.textPrimary }]}>
                    {searchErrorText}
                  </Text>
                  {searchQuery && URL_PATTERN.test(searchQuery.trim()) && (
                    <View>
                      <Text style={[styles.errorSubtext, { color: themePalette.textSecondary || COLORS.textSecondary }]}>
                        Supported: Amazon, Flipkart, Myntra, Meesho, Nykaa, Croma
                      </Text>
                      <Text style={[styles.errorHint, { color: themePalette.textSecondary || COLORS.textSecondary }]}>
                        Try using direct product URL (amazon.in/dp/B0xxxxxx)
                      </Text>
                    </View>
                  )}
                </View>
              )}

              {/* URL SEARCH RESULTS */}
              {searchStatus === 'succeeded' && results?.source && (
                renderURLSearchResult()
              )}

              {/* TEXT/PRODUCT SEARCH RESULTS */}
              {searchStatus === 'succeeded' && !results?.source && results.length > 0 && (
                <>
                  <Text style={[styles.sectionHeader, { color: themePalette.text || COLORS.textPrimary }]}>
                    Found {results.length} products
                  </Text>
                  <FlatList
                    data={results}
                    renderItem={renderResultCard}
                    keyExtractor={(item, idx) => `${item?.product_id || idx}`}
                    scrollEnabled={false}
                  />
                </>
              )}

              {searchStatus === 'succeeded' && results.length === 0 && (
                <View style={styles.emptySection}>
                  <Ionicons name="search-outline" size={48} color={COLORS.gray400} />
                  <Text style={[styles.emptyText, { color: themePalette.text || COLORS.textPrimary }]}>
                    No products found
                  </Text>
                  <Text style={[styles.emptySubtext, { color: themePalette.textSecondary || COLORS.textSecondary }]}>
                    Try a different search term
                  </Text>
                </View>
              )}
            </>
          ) : (
            <>
              {/* NEW PRODUCTS SECTION */}
              {newProducts.length > 0 && (
                <View style={styles.section}>
                  <Text style={[styles.sectionHeader, { color: themePalette.text || COLORS.textPrimary }]}>
                    ✨ New Products
                  </Text>
                  <FlatList
                    data={newProducts}
                    renderItem={renderNewProductCard}
                    keyExtractor={(item, idx) => `new-${item?.product_id || idx}`}
                    horizontal
                    showsHorizontalScrollIndicator={false}
                    contentContainerStyle={styles.horizontalList}
                  />
                </View>
              )}

              {/* PRICE CHANGED SECTION */}
              {priceChanged.length > 0 && (
                <View style={styles.section}>
                  <Text style={[styles.sectionHeader, { color: themePalette.text || COLORS.textPrimary }]}>
                    💰 Price Drops
                  </Text>
                  <FlatList
                    data={priceChanged}
                    renderItem={renderPriceChangedCard}
                    keyExtractor={(item, idx) => `price-${item?.product_id || idx}`}
                    scrollEnabled={false}
                  />
                </View>
              )}

              {/* TRENDING SECTION */}
              {trendingProducts.length > 0 && (
                <View style={styles.section}>
                  <Text style={[styles.sectionHeader, { color: themePalette.text || COLORS.textPrimary }]}>
                    🔥 Trending Now
                  </Text>
                  <FlatList
                    data={trendingProducts.slice(0, 8)}
                    renderItem={renderNewProductCard}
                    keyExtractor={(item, idx) => `trend-${item?.product_id || idx}`}
                    horizontal
                    showsHorizontalScrollIndicator={false}
                    contentContainerStyle={styles.horizontalList}
                  />
                </View>
              )}
            </>
          )}
        </ScrollView>

        {/* WHATSAPP-STYLE INPUT BAR - Inside KeyboardAvoidingView */}
        <View
          style={[
            styles.inputBar,
            {
              backgroundColor: themePalette.surface || COLORS.white,
              borderTopColor: themePalette.border || COLORS.gray200,
              paddingBottom: Math.max(8, insets.bottom),
            },
          ]}
        >
          <View
            style={[
              styles.inputRow,
              {
                backgroundColor: themePalette.surfaceMuted || COLORS.gray100,
                borderColor: themePalette.border || COLORS.gray200,
              },
            ]}
          >
            {/* SEARCH ICON */}
            <Ionicons name="search" size={18} color={themePalette.textSecondary || COLORS.gray500} style={styles.searchIcon} />

            {/* INPUT - DYNAMIC */}
            <TextInput
              ref={inputRef}
              placeholder="Search products, brands, or paste URL..."
              placeholderTextColor={COLORS.gray500}
              style={[styles.input, { color: themePalette.text || COLORS.textPrimary }]}
              value={searchQuery}
              onChangeText={setSearchQuery}
              onSubmitEditing={handleSearch}
              onFocus={handleInputFocus}
              onBlur={handleInputBlur}
              returnKeyType="search"
            />

            {/* CLEAR BUTTON */}
            {searchQuery.length > 0 && (
              <TouchableOpacity onPress={() => setSearchQuery('')} style={styles.clearBtn}>
                <Ionicons name="close-circle" size={18} color={COLORS.gray500} />
              </TouchableOpacity>
            )}

            {/* SEND BUTTON - DYNAMIC */}
            <TouchableOpacity
              style={[
                styles.sendBtn,
                {
                  backgroundColor: themePalette.primary || COLORS.primary,
                  opacity: !searchQuery.trim() || isSearching ? 0.6 : 1,
                },
              ]}
              onPress={handleSearch}
              disabled={!searchQuery.trim() || isSearching}
            >
              {isSearching ? (
                <ActivityIndicator size="small" color={COLORS.white} />
              ) : (
                <Ionicons name="arrow-forward" size={16} color={COLORS.white} />
              )}
            </TouchableOpacity>
          </View>
        </View>
        </View>
      </KeyboardAvoidingView>
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
    paddingVertical: 16,
    borderBottomWidth: 1,
  },

  headerTop: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
  },

  quotaPillRow: {
    marginTop: 12,
    flexDirection: 'row',
    justifyContent: 'flex-start',
  },

  quotaPill: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    paddingHorizontal: 12,
    paddingVertical: 8,
    borderRadius: 999,
    alignSelf: 'flex-start',
  },

  quotaPillText: {
    fontSize: 12,
    fontWeight: '700',
  },

  backButtonIcon: {
    padding: 8,
    borderRadius: 8,
  },

  headerTitle: {
    fontSize: 26,
    fontWeight: '900',
    color: COLORS.textPrimary,
    letterSpacing: 0.5,
  },

  bodyWrapper: {
    flex: 1,
  },

  scrollView: {
    flex: 1,
  },

  scrollContent: {
    paddingHorizontal: 16,
    paddingTop: 16,
  },

  section: {
    marginBottom: 28,
  },

  sectionHeader: {
    fontSize: 18,
    fontWeight: '700',
    marginBottom: 12,
    color: COLORS.textPrimary,
  },

  horizontalList: {
    paddingRight: 8,
  },

  // ===== NEW PRODUCTS CARD =====
  productCard: {
    width: 140,
    marginRight: 12,
    borderRadius: 12,
    overflow: 'hidden',
    borderWidth: 1,
    backgroundColor: COLORS.white,
  },

  cardImageContainer: {
    position: 'relative',
    width: '100%',
    height: 120,
  },

  cardImage: {
    width: '100%',
    height: '100%',
  },

  imagePlaceholder: {
    width: '100%',
    height: '100%',
    justifyContent: 'center',
    alignItems: 'center',
    backgroundColor: COLORS.gray100,
  },

  newBadge: {
    position: 'absolute',
    top: 8,
    right: 8,
    backgroundColor: '#4CAF50',
    paddingHorizontal: 8,
    paddingVertical: 4,
    borderRadius: 4,
  },

  newBadgeText: {
    color: COLORS.white,
    fontSize: 10,
    fontWeight: '700',
  },

  cardInfo: {
    padding: 10,
  },

  productTitle: {
    fontSize: 11,
    fontWeight: '600',
    marginBottom: 6,
    color: COLORS.textPrimary,
    lineHeight: 14,
  },

  productPrice: {
    fontSize: 13,
    fontWeight: '700',
    color: COLORS.primary,
  },

  // ===== PRICE CHANGED CARD =====
  priceChangeCard: {
    flexDirection: 'row',
    paddingHorizontal: 12,
    paddingVertical: 12,
    marginBottom: 10,
    borderRadius: 10,
    borderWidth: 1,
    alignItems: 'center',
    gap: 12,
  },

  smallImageContainer: {
    width: 70,
    height: 70,
    borderRadius: 8,
    overflow: 'hidden',
  },

  smallImage: {
    width: '100%',
    height: '100%',
  },

  smallPlaceholder: {
    width: '100%',
    height: '100%',
    justifyContent: 'center',
    alignItems: 'center',
  },

  priceChangeInfo: {
    flex: 1,
  },

  priceChangeTitle: {
    fontSize: 12,
    fontWeight: '600',
    marginBottom: 6,
    color: COLORS.textPrimary,
  },

  discountRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },

  discountBadge: {
    backgroundColor: '#FF5252',
    paddingHorizontal: 8,
    paddingVertical: 4,
    borderRadius: 4,
  },

  discountText: {
    color: COLORS.white,
    fontSize: 10,
    fontWeight: '700',
  },

  changedPrice: {
    fontSize: 12,
    fontWeight: '700',
    color: COLORS.primary,
  },

  // ===== RESULT CARDS =====
  resultCard: {
    flexDirection: 'row',
    marginBottom: 10,
    paddingHorizontal: 12,
    paddingVertical: 12,
    borderRadius: 10,
    borderWidth: 1,
    alignItems: 'center',
    gap: 12,
  },

  resultImage: {
    width: 60,
    height: 60,
    borderRadius: 8,
  },

  resultInfo: {
    flex: 1,
  },

  resultTitle: {
    fontSize: 12,
    fontWeight: '600',
    marginBottom: 4,
  },

  resultPrice: {
    fontSize: 12,
    fontWeight: '700',
  },

  // ===== URL SEARCH RESULT STYLES =====
  urlSearchHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 16,
  },

  originBadge: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    paddingHorizontal: 12,
    paddingVertical: 6,
    borderRadius: 12,
  },

  originBadgeText: {
    fontSize: 11,
    fontWeight: '600',
  },

  sourceProductCard: {
    flexDirection: 'row',
    marginBottom: 16,
    borderRadius: 12,
    overflow: 'hidden',
    gap: 12,
  },

  sourceImageContainer: {
    position: 'relative',
    width: 120,
    height: 120,
  },

  sourceImage: {
    width: '100%',
    height: '100%',
    borderRadius: 8,
  },

  bestDealBadge: {
    position: 'absolute',
    top: 8,
    right: 8,
    backgroundColor: COLORS.success,
    paddingVertical: 4,
    paddingHorizontal: 8,
    borderRadius: 6,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
  },

  bestDealText: {
    color: COLORS.white,
    fontSize: 10,
    fontWeight: '700',
  },

  platformBadge: {
    position: 'absolute',
    bottom: 8,
    left: 8,
    paddingHorizontal: 10,
    paddingVertical: 4,
    borderRadius: 6,
  },

  platformBadgeText: {
    color: COLORS.white,
    fontSize: 10,
    fontWeight: '700',
  },

  sourceProductInfo: {
    flex: 1,
    paddingVertical: 8,
  },

  sourceTitle: {
    fontSize: 13,
    fontWeight: '700',
    marginBottom: 6,
  },

  brandText: {
    fontSize: 11,
    fontWeight: '500',
    marginBottom: 6,
  },

  priceSection: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    marginBottom: 8,
  },

  sourcePrice: {
    fontSize: 16,
    fontWeight: '700',
  },

  originalPrice: {
    fontSize: 12,
    textDecorationLine: 'line-through',
  },

  ratingSection: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    marginBottom: 8,
  },

  rating: {
    flexDirection: 'row',
    gap: 2,
  },

  reviewCount: {
    fontSize: 10,
  },

  stockStatus: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
  },

  stockDot: {
    width: 8,
    height: 8,
    borderRadius: 4,
  },

  stockText: {
    fontSize: 11,
    fontWeight: '600',
  },

  alternativesSection: {
    marginBottom: 16,
  },

  alternativeCard: {
    padding: 12,
    marginBottom: 10,
    borderRadius: 10,
    borderWidth: 1,
  },

  altPlatformBadge: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    paddingHorizontal: 10,
    paddingVertical: 6,
    borderRadius: 6,
    marginBottom: 8,
    alignSelf: 'flex-start',
  },

  altPlatformText: {
    color: COLORS.white,
    fontSize: 10,
    fontWeight: '700',
  },

  altPriceContainer: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
    marginBottom: 8,
  },

  altPrice: {
    fontSize: 14,
    fontWeight: '700',
  },

  savingsBadge: {
    backgroundColor: '#E8F5E9',
    paddingHorizontal: 8,
    paddingVertical: 4,
    borderRadius: 6,
  },

  savingsText: {
    fontSize: 10,
    fontWeight: '600',
    color: COLORS.success,
  },

  altMetaInfo: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
  },

  altRating: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
  },

  altRatingText: {
    fontSize: 10,
    fontWeight: '600',
  },

  imagePlaceholder: {
    width: '100%',
    height: '100%',
    borderRadius: 8,
    justifyContent: 'center',
    alignItems: 'center',
  },

  summaryCard: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
    paddingHorizontal: 12,
    paddingVertical: 12,
    borderRadius: 10,
    marginBottom: 16,
  },

  summaryText: {
    fontSize: 12,
    fontWeight: '600',
    flex: 1,
  },

  // ===== STATE SECTIONS =====
  loadingSection: {
    paddingVertical: 60,
    justifyContent: 'center',
    alignItems: 'center',
  },

  loadingText: {
    marginTop: 12,
    fontSize: 14,
    color: COLORS.textSecondary,
  },

  errorSection: {
    paddingVertical: 60,
    justifyContent: 'center',
    alignItems: 'center',
  },

  errorText: {
    marginTop: 12,
    fontSize: 14,
    textAlign: 'center',
    color: COLORS.textPrimary,
  },

  errorSubtext: {
    marginTop: 8,
    fontSize: 12,
    textAlign: 'center',
    color: COLORS.textSecondary,
  },

  errorHint: {
    marginTop: 6,
    fontSize: 11,
    textAlign: 'center',
    fontStyle: 'italic',
    color: COLORS.textSecondary,
  },

  emptySection: {
    paddingVertical: 80,
    justifyContent: 'center',
    alignItems: 'center',
  },

  emptyText: {
    marginTop: 12,
    fontSize: 16,
    fontWeight: '600',
    color: COLORS.textPrimary,
  },

  emptySubtext: {
    marginTop: 6,
    fontSize: 12,
    color: COLORS.textSecondary,
  },

  // ===== INPUT BAR (WHATSAPP STYLE) =====
  inputBar: {
    borderTopWidth: 1,
    paddingHorizontal: 12,
    paddingTop: 8,
    paddingBottom: 8,
  },

  inputRow: {
    flexDirection: 'row',
    borderRadius: 24,
    borderWidth: 1,
    paddingHorizontal: 12,
    alignItems: 'center',
    gap: 8,
    backgroundColor: COLORS.gray100,
  },

  searchIcon: {
    marginRight: 4,
  },

  input: {
    flex: 1,
    paddingVertical: 12,
    paddingHorizontal: 8,
    fontSize: 14,
    color: COLORS.textPrimary,
  },

  clearBtn: {
    padding: 6,
  },

  sendBtn: {
    marginLeft: 4,
    paddingHorizontal: 14,
    paddingVertical: 10,
    borderRadius: 20,
    justifyContent: 'center',
    alignItems: 'center',
    backgroundColor: COLORS.primary,
  },

  clearResultsBtn: {
    display: 'none',
  },

  clearResultsText: {
    display: 'none',
  },
});

export default SearchScreenPremium;
