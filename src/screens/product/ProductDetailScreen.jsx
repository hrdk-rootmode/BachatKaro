// ============================================
// DEALHUNT APP - PRODUCT DETAIL SCREEN
// ============================================

import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  Image,
  TouchableOpacity,
  ActivityIndicator,
  FlatList,
  Alert,
  Linking,
  Animated,
} from 'react-native';
import { useDispatch, useSelector } from 'react-redux';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useFocusEffect } from '@react-navigation/native';
import { useProductWatchlist } from '../../hooks/useWatchlist';
import { Ionicons } from '@expo/vector-icons';

import {
  fetchProductDetails,
  fetchPriceHistory,
  refreshProductPrice,
  clearProductDetails,
  clearPriceHistory,
  selectSelectedProduct,
  selectProductDetailStatus,
  selectProductError,
  selectPriceHistory,
  selectPriceHistoryStatus,
} from '../../store/searchSlice';
import { COLORS } from '../../utils/constants';
import {
  formatPrice,
  formatShortDate,
  getPlatformBadge,
  getProductDisplayData,
  getVariantBadge,
} from '../../utils/formatters';
import PriceAccuracyDisclaimer from '../../components/PriceAccuracyDisclaimer';
import FreshnessIndicator from '../../components/FreshnessIndicator';
import PriceComparisonTable from '../../components/PriceComparisonTable';
import productAPI from '../../services/productApi';
import { searchAPI } from '../../services/searchApi';

// ============================================
// WISHLIST BUTTON COMPONENT (Add before ProductDetailScreen)
// ============================================

const WishlistHeaderButton = ({ productId, product }) => {
  const { isInWatchlist, isProcessing, toggle } = useProductWatchlist(productId, product);
  const scaleAnim = React.useRef(new Animated.Value(1)).current;
  
  const handlePress = React.useCallback(async () => {
    // Bounce animation
    Animated.sequence([
      Animated.timing(scaleAnim, {
        toValue: 0.7,
        duration: 100,
        useNativeDriver: true,
      }),
      Animated.spring(scaleAnim, {
        toValue: 1,
        friction: 3,
        tension: 100,
        useNativeDriver: true,
      }),
    ]).start();
    
    await toggle();
  }, [toggle, scaleAnim]);
  
  return (
    <TouchableOpacity
      style={wishlistButtonStyles.container}
      onPress={handlePress}
      disabled={isProcessing}
      activeOpacity={0.7}
    >
      <Animated.View style={{ transform: [{ scale: scaleAnim }] }}>
        {isProcessing ? (
          <ActivityIndicator size="small" color={COLORS.primary} />
        ) : (
          <Ionicons
            name={isInWatchlist ? 'heart' : 'heart-outline'}
            size={24}
            color={isInWatchlist ? COLORS.error : COLORS.gray500}
          />
        )}
      </Animated.View>
    </TouchableOpacity>
  );
};

const wishlistButtonStyles = StyleSheet.create({
  container: {
    width: 40,
    height: 40,
    borderRadius: 20,
    backgroundColor: COLORS.white,
    justifyContent: 'center',
    alignItems: 'center',
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.1,
    shadowRadius: 4,
    elevation: 3,
  },
});

// ============================================
// PRODUCT DETAIL SCREEN
// ============================================

const ProductDetailScreen = ({ navigation, route }) => {
  const productId = route.params?.productId || route.params?.product_id;
  const dispatch = useDispatch();

  // Redux state with defaults
  const product = useSelector(selectSelectedProduct) || null;
  const productStatus = useSelector(selectProductDetailStatus) || 'idle';
  const productError = useSelector(selectProductError) || null;
  const priceHistory = useSelector(selectPriceHistory) || null;
  const priceHistoryStatus = useSelector(selectPriceHistoryStatus) || 'idle';

  // Local state
  const [selectedPlatform, setSelectedPlatform] = useState(null);
  const [isLiveRefreshing, setIsLiveRefreshing] = useState(false);
  const [similarProducts, setSimilarProducts] = useState([]);
  const [similarLoading, setSimilarLoading] = useState(false);
  const [crossPlatformListings, setCrossPlatformListings] = useState([]);
  const [crossPlatformLoading, setCrossPlatformLoading] = useState(false);
  const lastHistoryRequestKeyRef = useRef(null);
  const productRequestInFlightRef = useRef(null);

  const isValidDisplayImage = (url) => {
    if (!url || typeof url !== 'string') return false;
    const u = url.trim().toLowerCase();
    if (!u) return false;
    if (u.includes('svgicons') || u.includes('wishlist.svg') || u.endsWith('.svg')) return false;
    return u.startsWith('http');
  };

  const isRouteProductLoaded = !!product?.id && String(product.id) === String(productId);
  const availablePlatforms = useMemo(() => {
    if (!isRouteProductLoaded || !Array.isArray(product?.listings)) return [];
    return Array.from(
      new Set(
        product.listings
          .map((l) => String(l?.platform || '').toLowerCase())
          .filter(Boolean)
      )
    );
  }, [isRouteProductLoaded, product?.listings]);

  const requestProductForRoute = useCallback(
    (targetProductId) => {
      const normalizedProductId = String(targetProductId || '').trim();
      if (!normalizedProductId) return;
      if (productRequestInFlightRef.current === normalizedProductId) return;

      productRequestInFlightRef.current = normalizedProductId;
      lastHistoryRequestKeyRef.current = null;
      dispatch(clearProductDetails());
      dispatch(clearPriceHistory());
      dispatch(fetchProductDetails({ productId: normalizedProductId }));
    },
    [dispatch]
  );

  // Load route product details and prevent stale snapshots from other pushed ProductDetail screens.
  useEffect(() => {
    requestProductForRoute(productId);
  }, [productId, requestProductForRoute]);

  // Release request lock once we get a terminal state for current route.
  useEffect(() => {
    if (isRouteProductLoaded || productStatus === 'failed') {
      productRequestInFlightRef.current = null;
    }
  }, [isRouteProductLoaded, productStatus]);

  // When user returns from a pushed similar-product detail, refetch route product if store holds another product.
  useFocusEffect(
    useCallback(() => {
      if (!isRouteProductLoaded) {
        requestProductForRoute(productId);
      }
      return undefined;
    }, [isRouteProductLoaded, productId, requestProductForRoute])
  );

  // Ensure selected platform exists for current product
  useEffect(() => {
    if (!isRouteProductLoaded) return;
    if (availablePlatforms.length === 0) return;

    setSelectedPlatform((prev) => (availablePlatforms.includes(String(prev || '').toLowerCase()) ? prev : availablePlatforms[0]));
  }, [isRouteProductLoaded, product?.id, product?.listings, availablePlatforms]);

  // Load price history when product loads
  useEffect(() => {
    if (isRouteProductLoaded && selectedPlatform && availablePlatforms.includes(String(selectedPlatform).toLowerCase())) {
      const requestKey = `${product.id}:${String(selectedPlatform).toLowerCase()}:120`;
      if (lastHistoryRequestKeyRef.current === requestKey) {
        return;
      }
      lastHistoryRequestKeyRef.current = requestKey;
      dispatch(clearPriceHistory());
      dispatch(fetchPriceHistory({
        productId: product.id,
        platform: selectedPlatform,
        days: 120,
      }));
    }
  }, [isRouteProductLoaded, product?.id, selectedPlatform, availablePlatforms, dispatch]);

  // Fetch similar products from search using product title keywords.
  useEffect(() => {
    let isMounted = true;

    const normalizeText = (value) =>
      String(value || '')
        .toLowerCase()
        .replace(/[^a-z0-9]+/g, ' ')
        .trim();

    const stopwords = new Set(['the', 'and', 'for', 'with', 'from', 'this', 'that', 'new', 'best']);

    const toTokens = (value) =>
      normalizeText(value)
        .split(/\s+/)
        .filter((token) => token.length > 2 && !stopwords.has(token));

    const loadSimilar = async () => {
      if (!isRouteProductLoaded || !product?.title) {
        if (isMounted) setSimilarProducts([]);
        return;
      }

      const primaryTitleTokens = toTokens(product.title).slice(0, 4);
      const intentContext = [product?.category, product?.subcategory]
        .filter(Boolean)
        .map((part) => normalizeText(part));

      const keywords = [...intentContext, ...primaryTitleTokens]
        .filter(Boolean)
        .join(' ')
        .trim();

      if (!keywords || keywords.length < 3) {
        if (isMounted) setSimilarProducts([]);
        return;
      }

      try {
        if (isMounted) setSimilarLoading(true);
        const result = await searchAPI.searchProducts(keywords, {}, 1);
        if (!result?.success) {
          if (isMounted) setSimilarProducts([]);
          return;
        }

        const candidates = Array.isArray(result?.data?.products) ? result.data.products : [];
        const currentCategory = normalizeText(product?.category);
        const currentSubcategory = normalizeText(product?.subcategory);
        const titleTokenSet = new Set(toTokens(product?.title));

        const baseFiltered = candidates.filter((p) => String(p?.id || p?.product_id) !== String(product.id));

        const scored = baseFiltered
          .map((candidate) => {
            const candidateCategory = normalizeText(candidate?.category);
            const candidateSubcategory = normalizeText(candidate?.subcategory);
            const sameCategory =
              (currentCategory && candidateCategory && currentCategory === candidateCategory) ||
              (currentSubcategory && candidateSubcategory && currentSubcategory === candidateSubcategory);

            const candidateTokens = toTokens(candidate?.title || candidate?.ai_generated_essence || '');
            const overlap = candidateTokens.reduce(
              (count, token) => (titleTokenSet.has(token) ? count + 1 : count),
              0
            );

            return {
              candidate,
              sameCategory,
              overlap,
              score: (sameCategory ? 100 : 0) + overlap,
            };
          })
          .filter((entry) => entry.overlap > 0)
          .sort((a, b) => b.score - a.score);

        const strictCategoryMatches = scored
          .filter((entry) => entry.sameCategory)
          .map((entry) => entry.candidate)
          .slice(0, 10);

        const fallbackMatches = scored
          .map((entry) => entry.candidate)
          .slice(0, 10);

        const filtered = strictCategoryMatches.length > 0 ? strictCategoryMatches : fallbackMatches;

        if (isMounted) setSimilarProducts(filtered);
      } catch {
        if (isMounted) setSimilarProducts([]);
      } finally {
        if (isMounted) setSimilarLoading(false);
      }
    };

    loadSimilar();
    return () => {
      isMounted = false;
    };
  }, [isRouteProductLoaded, product?.id, product?.title]);

  // Fetch same-product availability across platforms/variants from backend family endpoint.
  useEffect(() => {
    let isMounted = true;

    const loadCrossPlatform = async () => {
      if (!isRouteProductLoaded || !product?.id) {
        if (isMounted) setCrossPlatformListings([]);
        return;
      }

      try {
        if (isMounted) setCrossPlatformLoading(true);

        const result = await productAPI.getCrossPlatformVariants(product.id);
        if (!result?.success) {
          if (isMounted) setCrossPlatformListings([]);
          return;
        }

        const variants = Array.isArray(result?.data?.variants) ? result.data.variants : [];
        const flattened = [];

        variants.forEach((variant) => {
          const variantFingerprint = String(variant?.variant_fingerprint || 'standard');
          const rows = Array.isArray(variant?.platforms) ? variant.platforms : [];

          rows.forEach((row, idx) => {
            const platformName = String(row?.platform || '').toLowerCase();
            const price = Number(row?.price || 0);
            if (!platformName || price <= 0) return;

            flattened.push({
              id: `${variantFingerprint}-${platformName}-${idx}`,
              platform: platformName,
              price,
              originalPrice: Number(row?.original_price || 0) || null,
              discountPercent: Number(row?.discount_percent || 0) || 0,
              url: row?.url || '',
              inStock: row?.in_stock !== false,
              rating: row?.rating,
              reviewCount: row?.review_count,
              variantFingerprint,
            });
          });
        });

        if (isMounted) setCrossPlatformListings(flattened);
      } catch {
        if (isMounted) setCrossPlatformListings([]);
      } finally {
        if (isMounted) setCrossPlatformLoading(false);
      }
    };

    loadCrossPlatform();
    return () => {
      isMounted = false;
    };
  }, [isRouteProductLoaded, product?.id]);

  const otherPlatformListings = useMemo(() => {
    const selected = String(selectedPlatform || '').toLowerCase();
    const bestByPlatform = new Map();

    crossPlatformListings.forEach((listing) => {
      const platformName = String(listing?.platform || '').toLowerCase();
      if (!platformName) return;
      if (selected && platformName === selected) return;

      const existing = bestByPlatform.get(platformName);
      if (!existing || Number(listing?.price || Infinity) < Number(existing?.price || Infinity)) {
        bestByPlatform.set(platformName, listing);
      }
    });

    return Array.from(bestByPlatform.values())
      .sort((a, b) => Number(a?.price || 0) - Number(b?.price || 0))
      .slice(0, 12);
  }, [crossPlatformListings, selectedPlatform]);

  const getFreshnessStatus = (updatedAt) => {
    if (!updatedAt) return 'very_stale';
    const ageMs = Date.now() - new Date(updatedAt).getTime();
    const ageHours = ageMs / (1000 * 60 * 60);
    if (ageHours <= 2) return 'fresh';
    if (ageHours <= 12) return 'stale';
    return 'very_stale';
  };

  if (productStatus === 'loading' || (product && !isRouteProductLoaded)) {
    return (
      <SafeAreaView style={styles.container}>
        <View style={styles.loadingContainer}>
          <ActivityIndicator size="large" color={COLORS.primary} />
          <Text style={styles.loadingText}>Loading product details...</Text>
        </View>
      </SafeAreaView>
    );
  }

  if (productStatus === 'failed') {
    return (
      <SafeAreaView style={styles.container}>
        <View style={styles.emptyContainer}>
          <Ionicons name="alert-circle" size={48} color={COLORS.error} />
          <Text style={styles.emptyText}>{productError || 'Product not found'}</Text>
          <TouchableOpacity
            style={styles.backButtonSmall}
            onPress={() => dispatch(fetchProductDetails({ productId }))}
          >
            <Text style={styles.backButtonText}>Retry</Text>
          </TouchableOpacity>
        </View>
      </SafeAreaView>
    );
  }

  if (!product) {
    return (
      <SafeAreaView style={styles.container}>
        <View style={styles.emptyContainer}>
          <Ionicons name="alert-circle" size={48} color={COLORS.error} />
          <Text style={styles.emptyText}>Product not found</Text>
          <TouchableOpacity
            style={styles.backButtonSmall}
            onPress={() => navigation.goBack()}
          >
            <Text style={styles.backButtonText}>Go Back</Text>
          </TouchableOpacity>
        </View>
      </SafeAreaView>
    );
  }

  // ✅ Get display data from product
  const displayData = getProductDisplayData(product);

  const handleOpenUrl = (url) => {
    if (!url) {
      Alert.alert('Unavailable', 'Product link is not available right now.');
      return;
    }

    Linking.openURL(url).catch(() =>
      Alert.alert('Error', 'Cannot open URL')
    );
  };

   const handleLiveRefresh = async () => {
    if (!product?.id || isLiveRefreshing) return;

    try {
      setIsLiveRefreshing(true);
      
      // ✅ FIX 1: Call refresh API
      const refreshResult = await dispatch(
        refreshProductPrice({ productId: product.id, platform: selectedPlatform || undefined })
      ).unwrap();

      const liveRefreshMeta = refreshResult?.stats?.live_refresh || null;
      const liveUsed = Boolean(liveRefreshMeta?.live_used);
      const changedCount = Number(liveRefreshMeta?.changed_count || 0);
      const refreshedCount = Number(liveRefreshMeta?.refreshed_count || 0);
      const failedPlatforms = Array.isArray(liveRefreshMeta?.failed_platforms)
        ? liveRefreshMeta.failed_platforms
        : [];
      
      // ✅ FIX 2: Use returned data directly - NO redundant fetchProductDetails
      // The refresh endpoint already returns full ProductResponse
      
      // ✅ FIX 3: Only fetch price history (not full product again)
      if (selectedPlatform) {
        lastHistoryRequestKeyRef.current = null;
        dispatch(clearPriceHistory());
        dispatch(
          fetchPriceHistory({
            productId: refreshResult.id || product.id,
            platform: selectedPlatform,
            days: 120,
          })
        );
      }
      
      if (liveRefreshMeta && !liveUsed) {
        const platformHint = failedPlatforms.length > 0
          ? ` (${failedPlatforms.join(', ')})`
          : '';

        Alert.alert(
          'Live Refresh Unavailable',
          `Could not fetch fresh live prices right now${platformHint}. Showing latest saved prices from database.`,
          [{ text: 'OK', style: 'default' }]
        );
      } else {
        const summaryText = changedCount > 0
          ? `Live scraping updated ${refreshedCount || 1} platform(s) and detected ${changedCount} price change(s).`
          : `Live scraping completed for ${refreshedCount || 1} platform(s). No price change detected.`;

        Alert.alert(
          'Live Prices Updated',
          summaryText,
          [{ text: 'OK', style: 'default' }]
        );
      }
      
    } catch (err) {
      const errText = String(err || '');
      
      // ✅ FIX 5: Simplified error handling - single path, no nested fallbacks
      console.error('Live Refresh Error:', errText);
      
      // Sync DB snapshot (silently - already done by backend fallback)
      try {
        await dispatch(fetchProductDetails({ productId: product.id })).unwrap();
        
        // Reload price history
        if (selectedPlatform) {
          lastHistoryRequestKeyRef.current = null;
          dispatch(clearPriceHistory());
          dispatch(
            fetchPriceHistory({
              productId: product.id,
              platform: selectedPlatform,
              days: 120,
            })
          );
        }
      } catch (syncErr) {
        // Silent - DB sync already happened in backend
      }
      
      // Show user-friendly message
      Alert.alert(
        'Refresh Info',
        'Showing latest database prices. Live scraping may be temporarily unavailable.',
        [{ text: 'OK', style: 'default' }]
      );
      
    } finally {
      setIsLiveRefreshing(false);
    }
  };

  const latestListingForSelectedPlatform = Array.isArray(product?.listings)
    ? product.listings
        .filter((l) => String(l?.platform || '').toLowerCase() === String(selectedPlatform || '').toLowerCase())
        .sort((a, b) => new Date(b?.last_scraped_at || 0) - new Date(a?.last_scraped_at || 0))[0]
    : null;

  const sanitizedHistory = Array.isArray(priceHistory?.history)
    ? priceHistory.history.filter((p) => Number(p?.price || 0) > 0)
    : [];

  const fallbackImageFromListings = Array.isArray(product?.listings)
    ? product.listings
        .map((l) => l?.image_url)
        .find((u) => isValidDisplayImage(u))
    : null;

  const resolvedDisplayImage = isValidDisplayImage(displayData.imageUrl)
    ? displayData.imageUrl
    : fallbackImageFromListings;

  const latestHistoryPoint = sanitizedHistory.length > 0
    ? sanitizedHistory[sanitizedHistory.length - 1]
    : null;

  const historyRecommendation = String(priceHistory?.recommendation || '').toLowerCase();
  const recommendationMeta = {
    buy_now: { label: 'Buy Now', color: COLORS.success, icon: 'checkmark-circle' },
    wait: { label: 'Wait for Better Offer', color: COLORS.warning, icon: 'time' },
    watch: { label: 'Watch This Product', color: COLORS.info, icon: 'analytics' },
  };
  const recommendationConfig = recommendationMeta[historyRecommendation] || recommendationMeta.watch;

  const dataPointsCount = Number(priceHistory?.data_points_count || sanitizedHistory.length || 0);
  const historySpanDays = Number(priceHistory?.history_span_days || 0);
  const hasObservedWeeklyChange =
    priceHistory?.observed_change_percentage_7d !== null &&
    priceHistory?.observed_change_percentage_7d !== undefined;
  const observedChange7d = Number(priceHistory?.observed_change_percentage_7d || 0);
  const hasObservedDropAmount =
    priceHistory?.observed_drop_amount_7d !== null &&
    priceHistory?.observed_drop_amount_7d !== undefined;
  const observedDropAmount7d = Number(priceHistory?.observed_drop_amount_7d || 0);

  const predictionAvailable = Boolean(priceHistory?.prediction_available);
  const hasPredictedChange7d =
    priceHistory?.predicted_change_percentage_7d !== null &&
    priceHistory?.predicted_change_percentage_7d !== undefined;
  const predictedChange7d = Number(priceHistory?.predicted_change_percentage_7d || 0);
  const confidenceScore = Number(priceHistory?.confidence_score || 0);
  const recommendationReasons = Array.isArray(priceHistory?.recommendation_reasons)
    ? priceHistory.recommendation_reasons.filter(Boolean)
    : [];
  const insightBasis = Array.isArray(priceHistory?.insight_basis)
    ? priceHistory.insight_basis.filter(Boolean)
    : [];

  const latestKnownUpdateAt = latestHistoryPoint?.date || latestListingForSelectedPlatform?.last_scraped_at || null;
  const freshnessStatus = getFreshnessStatus(latestKnownUpdateAt);

  // ✅ NEW: Get best price and cheapest platform for comparison header
  const getBestPriceInfo = () => {
    if (!Array.isArray(product?.listings) || product.listings.length === 0) {
      return { bestPrice: null, cheapestPlatform: null, savings: null };
    }
    
    const validListings = product.listings.filter(l => l && l.current_price);
    if (validListings.length === 0) return { bestPrice: null, cheapestPlatform: null, savings: null };
    
    const cheapest = validListings.reduce((min, curr) => 
      curr.current_price < min.current_price ? curr : min
    );
    
    const avgPrice = validListings.reduce((sum, l) => sum + l.current_price, 0) / validListings.length;
    const savings = Math.round(((avgPrice - cheapest.current_price) / avgPrice) * 100);
    
    return { 
      bestPrice: cheapest.current_price,
      cheapestPlatform: cheapest.platform,
      savings: savings > 0 ? savings : null
    };
  };

  const getSelectedPlatformLivePrice = () => {
    if (!Array.isArray(product?.listings) || product.listings.length === 0) return null;

    const platformListings = product.listings.filter(
      (l) => l && l.current_price != null && String(l.platform || '').toLowerCase() === String(selectedPlatform || '').toLowerCase()
    );

    if (platformListings.length === 0) return null;

    // Prefer the most recently scraped listing for that platform
    const latestListing = platformListings
      .slice()
      .sort((a, b) => new Date(b.last_scraped_at || 0) - new Date(a.last_scraped_at || 0))[0];

    return latestListing?.current_price ?? null;
  };

  // ✅ NEW: Group listings by variant fingerprint for cross-platform comparison
  const groupListingsByVariant = () => {
    if (!Array.isArray(product?.listings)) return [];
    
    const variantMap = {};
    product.listings.forEach(listing => {
      if (listing && listing.id) {
        const variantKey = listing.variant_fingerprint || 'default';
        if (!variantMap[variantKey]) {
          variantMap[variantKey] = [];
        }
        variantMap[variantKey].push(listing);
      }
    });
    
    return Object.entries(variantMap).map(([variant, listings]) => ({
      variant,
      listings,
      platformCount: listings.length
    }));
  };

  const renderListingCard = ({ item }) => {
    // 🛡️ DEFENSIVE: Handle invalid items gracefully
    if (!item || !item.id) {
      return null;
    }
    
    const platformBadge = getPlatformBadge(item.platform || 'amazon');
    
    // ✅ CRITICAL: Use current_price (backend field), fallback to price
    const currentPrice = item.current_price || item.price;
    const originalPrice = item.original_price || item.mrp || null;
    const discountPct = item.discount_percentage || item.discount_percent || 0;

    return (
      <TouchableOpacity
        style={styles.listingCard}
        onPress={() => handleOpenUrl(item.product_url || item.url)}
        activeOpacity={0.7}
      >
        {/* Platform Badge */}
        <View
          style={[
            styles.platformTag,
            { backgroundColor: platformBadge.color },
          ]}
        >
          <Text style={styles.platformTagText}>
            {platformBadge.icon}
            {platformBadge.name}
          </Text>
        </View>

        {/* Price */}
        <View style={styles.listingPriceContainer}>
          <Text style={styles.listingPrice}>
            {formatPrice(currentPrice)}
          </Text>
          {originalPrice && originalPrice > currentPrice && (
            <Text style={styles.listingOriginalPrice}>
              {formatPrice(originalPrice)}
            </Text>
          )}
        </View>

        {/* Discount */}
        {discountPct > 0 && (
          <View style={styles.discountTag}>
            <Text style={styles.discountTagText}>
              {Math.round(discountPct)}% OFF
            </Text>
          </View>
        )}

        {/* Rating */}
        {item.rating !== null && item.rating !== undefined && (
          <View style={styles.ratingSmall}>
            <Ionicons name="star" size={12} color="#FFC107" />
            <Text style={styles.ratingSmallText}>
              {typeof item.rating === 'number' ? item.rating.toFixed(1) : item.rating}
            </Text>
          </View>
        )}

        {/* Stock Status */}
        <View style={[
          styles.stockStatus,
          { borderLeftColor: item.in_stock ? COLORS.success : COLORS.error }
        ]}>
          <Text style={[
            styles.stockText,
            { color: item.in_stock ? COLORS.success : COLORS.error }
          ]}>
            {item.in_stock ? 'In Stock' : 'Out of Stock'}
          </Text>
        </View>

        {/* Buy Button */}
        <TouchableOpacity
          style={styles.buyButton}
          onPress={() => handleOpenUrl(item.product_url || item.url)}
        >
          <Ionicons name="open-outline" size={16} color={COLORS.white} />
          <Text style={styles.buyButtonText}>View on Site</Text>
        </TouchableOpacity>
      </TouchableOpacity>
    );
  };

  return (
    <SafeAreaView style={styles.container}>
      <ScrollView showsVerticalScrollIndicator={false} contentContainerStyle={styles.scrollContent}>
        {/* Header */}
        <View style={styles.header}>
          <TouchableOpacity
            style={styles.backButton}
            onPress={() => navigation.goBack()}
          >
            <Ionicons name="arrow-back" size={24} color={COLORS.primary} />
          </TouchableOpacity>
          <Text style={styles.headerTitle}>Product Details</Text>
          
          {/* ✅ NEW: Wishlist Button in Header */}
          {product && productId && (
            <WishlistHeaderButton 
              productId={productId} 
              product={{
                ...product,
                id: productId,
                product_id: productId,
              }} 
            />
          )}
          {!product && <View style={{ width: 40 }} />}
        </View>

        {/* Product Image */}
        <View style={styles.imageContainer}>
          {resolvedDisplayImage ? (
            <Image
              source={{ uri: resolvedDisplayImage }}
              style={styles.productImage}
              resizeMode="contain"
            />
          ) : (
            <View style={styles.imagePlaceholder}>
              <Ionicons name="image-outline" size={64} color={COLORS.gray400} />
            </View>
          )}
        </View>

        {/* Product Title & Price */}
        <View style={styles.productSection}>
          <Text style={styles.productTitle}>{displayData.title}</Text>

        <TouchableOpacity
          style={[styles.liveRefreshButton, isLiveRefreshing && styles.liveRefreshButtonDisabled]}
          onPress={handleLiveRefresh}
          activeOpacity={0.8}
          disabled={isLiveRefreshing}
        >
          {isLiveRefreshing ? (
            <ActivityIndicator size="small" color={COLORS.white} />
          ) : (
            <Ionicons name="refresh" size={16} color={COLORS.white} />
          )}
          <Text style={styles.liveRefreshButtonText}>
            {isLiveRefreshing ? 'Refreshing Live Price...' : 'Refresh Live Price'}
          </Text>
        </TouchableOpacity>

        {/* Price Display */}
        <View style={styles.priceSection}>
          {(() => {
            const livePlatformPrice = getSelectedPlatformLivePrice();
            const historyLatestPrice =
              sanitizedHistory.length > 0
                ? sanitizedHistory[sanitizedHistory.length - 1].price
                : null;
            const resolvedPrice = livePlatformPrice ?? historyLatestPrice ?? product?.best_price ?? 0;
            const selectedListingOriginal = Number(latestListingForSelectedPlatform?.original_price || 0) > Number(resolvedPrice || 0)
              ? latestListingForSelectedPlatform?.original_price
              : null;
            const selectedListingDiscount = selectedListingOriginal
              ? Math.round(((selectedListingOriginal - resolvedPrice) / selectedListingOriginal) * 100)
              : 0;

            return (
              <>
                <Text style={styles.bestPrice}>
                  {formatPrice(resolvedPrice)}
                </Text>
                {selectedListingOriginal && (
                  <Text style={styles.originalPrice}>
                    {formatPrice(selectedListingOriginal)}
                  </Text>
                )}
                {selectedListingDiscount > 0 && (
                  <View style={styles.discountBadgeLarge}>
                    <Text style={styles.discountBadgeText}>
                      {selectedListingDiscount}% OFF
                    </Text>
                  </View>
                )}
              </>
            );
          })()}
          {/* ✅ NEW: Show when price was last updated */}
{sanitizedHistory.length >= 2 && (
  <View style={styles.priceUpdateInfo}>
    <Ionicons name="time-outline" size={12} color={COLORS.gray500} />
    <Text style={styles.priceUpdateText}>
      Price changed {(() => {
        const latestPoint = sanitizedHistory[sanitizedHistory.length - 1];
        const date = new Date(latestPoint.date);
        const today = new Date();
        const diffMs = today - date;
        const diffMins = Math.floor(diffMs / 60000);
        const diffHours = Math.floor(diffMins / 60);
        const diffDays = Math.floor(diffHours / 24);
        
        if (diffMins < 60) return `${diffMins} mins ago`;
        if (diffHours < 24) return `${diffHours}h ago`;
        if (diffDays < 7) return `${diffDays}d ago`;
        return date.toLocaleDateString('en-IN');
      })()}
    </Text>
  </View>
)}
{sanitizedHistory.length === 1 && (
  <View style={styles.priceUpdateInfo}>
    <Ionicons name="time-outline" size={12} color={COLORS.success} />
    <Text style={styles.priceUpdateText}>
      First price recorded {formatShortDate(sanitizedHistory[0].date)}
    </Text>
  </View>
)}
        </View>

          {/* ✅ NEW: Price Accuracy Disclaimer */}
          <PriceAccuracyDisclaimer 
            lastUpdatedAt={latestKnownUpdateAt}
            freshness_status={freshnessStatus}
          />

          {/* ✅ NEW: Freshness Indicator */}
          <FreshnessIndicator 
            freshness_status={freshnessStatus}
            lastUpdatedAt={latestKnownUpdateAt}
          />

          {/* ✅ NEW: Price Comparison Table */}
          {Array.isArray(product?.listings) && product.listings.length > 0 && (
            <View style={{ marginVertical: 12 }}>
              <PriceComparisonTable
                listings={product.listings}
                bestPlatform={product.listings.reduce((best, curr) => 
                  curr.current_price < (best?.current_price || Infinity) ? curr : best
                )?.platform}
              />
            </View>
          )}

          {/* Rating */}
          {displayData.rating !== null && displayData.rating !== undefined && (
            <View style={styles.ratingSection}>
              <View style={styles.ratingStars}>
                {[...Array(5)].map((_, i) => (
                  <Ionicons
                    key={`star-${i}`}
                    name="star"
                    size={16}
                    color={
                      i < Math.floor(displayData.rating)
                        ? '#FFC107'
                        : COLORS.gray300
                    }
                  />
                ))}
              </View>
              <Text style={styles.ratingValue}>
                {typeof displayData.rating === 'number' ? displayData.rating.toFixed(1) : displayData.rating}/5
              </Text>
              <Text style={styles.reviewCountValue}>
                ({displayData.reviewCount} reviews)
              </Text>
            </View>
          )}
        </View>

        {/* ✅ NEW: Variant Information Section */}
        {(displayData.variant_type || displayData.storage_gb || displayData.color || displayData.condition) && (
          <View style={styles.variantSection}>
            <Text style={styles.sectionTitle}>Variant Details</Text>
            
            {/* Variant Type Badge */}
            {displayData.variant_type && (
              <View style={styles.variantTypeContainer}>
                <View 
                  style={[
                    styles.variantTypeBadge,
                    { backgroundColor: getVariantBadge(displayData.variant_type).color }
                  ]}
                >
                  <Text style={styles.variantTypeText}>
                    {getVariantBadge(displayData.variant_type).label}
                  </Text>
                </View>
              </View>
            )}
            
            {/* Variant Specs Grid */}
            {(displayData.storage_gb || displayData.color || displayData.condition) && (
              <View style={styles.variantSpecsGrid}>
                {displayData.storage_gb && (
                  <View style={styles.variantSpecItem}>
                    <Text style={styles.variantSpecLabel}>Storage</Text>
                    <Text style={styles.variantSpecValue}>{displayData.storage_gb}GB</Text>
                  </View>
                )}
                {displayData.color && (
                  <View style={styles.variantSpecItem}>
                    <Text style={styles.variantSpecLabel}>Color</Text>
                    <Text style={styles.variantSpecValue}>{displayData.color}</Text>
                  </View>
                )}
                {displayData.condition && (
                  <View style={styles.variantSpecItem}>
                    <Text style={styles.variantSpecLabel}>Condition</Text>
                    <Text style={styles.variantSpecValue}>{displayData.condition}</Text>
                  </View>
                )}
              </View>
            )}
            
            {/* Variant Fingerprints for Advanced Users */}
            {displayData.variant_fingerprint && (
              <View style={styles.fingerprintInfo}>
                <Text style={styles.fingerprintLabel}>Variant ID</Text>
                <Text style={styles.fingerprintValue} numberOfLines={1}>
                  {displayData.variant_fingerprint}
                </Text>
              </View>
            )}
          </View>
        )}

        {/* Specifications */}
        {Object.keys(displayData.specs).length > 0 && (
          <View style={styles.specsSection}>
            <Text style={styles.sectionTitle}>Specifications</Text>
            {Object.entries(displayData.specs).filter(([_, value]) => value != null && value !== undefined)
            .map(([key, value], index) => (
              <View key={`spec-${key}`} style={styles.specItem}>
                <Text style={styles.specLabel}>
                  {key.replace(/_/g, ' ')}
                </Text>
                <Text style={styles.specValue}>{String(value)}</Text>
              </View>
            ))}
          </View>
        )}

        {/* Platform Selector */}
        <View style={styles.platformSection}>
          <View style={styles.platformHeaderRow}>
            <Text style={styles.sectionTitle}>Available Platforms</Text>
            {Array.isArray(product?.listings) && product.listings.length > 0 && (
              <View style={styles.platformCountBadge}>
                <Text style={styles.platformCountText}>
                  {product.listings.length} Platform{product.listings.length !== 1 ? 's' : ''}
                </Text>
              </View>
            )}
          </View>
          {Array.isArray(product?.listings) && product.listings.length > 0 ? (
            <FlatList
              data={product.listings.filter(item => item && item.id)} // 🛡️ Filter out invalid items
              renderItem={({ item }) => {
                const badge = getPlatformBadge(item.platform || 'amazon');
                const isSelected = item.platform === selectedPlatform;

                return (
                  <TouchableOpacity
                    style={[
                      styles.platformSelector,
                      isSelected && styles.platformSelectorSelected,
                    ]}
                    onPress={() => setSelectedPlatform(item.platform)}
                  >
                    <Text
                      style={[
                        styles.platformSelectorText,
                        isSelected && styles.platformSelectorTextSelected,
                      ]}
                    >
                      {badge.icon} {badge.name}
                    </Text>
                  </TouchableOpacity>
                );
              }}
              keyExtractor={(item, index) => `listing-platform-${item?.id || `index-${index}`}`}
              scrollEnabled={false}
            />
          ) : (
            <Text style={{ color: COLORS.textSecondary }}>No listings available</Text>
          )}
        </View>

        {/* Price Comparison */}
        <View style={styles.comparisonSection}>
          {/* Header with Best Price Info */}
          {(() => {
            const { bestPrice, cheapestPlatform, savings } = getBestPriceInfo();
            return (
              <>
                <View style={styles.comparisonHeader}>
                  <View style={styles.comparisonTitleRow}>
                    <Text style={styles.sectionTitle}>Price Comparison</Text>
                    {Array.isArray(product?.listings) && product.listings.length > 0 && (
                      <View style={styles.listingCountBadge}>
                        <Text style={styles.listingCountText}>
                          {product.listings.length} Listing{product.listings.length !== 1 ? 's' : ''}
                        </Text>
                      </View>
                    )}
                  </View>
                  {bestPrice && (
                    <View style={styles.bestPriceTag}>
                      <Text style={styles.bestPriceText}>Best: {formatPrice(bestPrice)}</Text>
                      {savings && <Text style={styles.savingsText}>Save {savings}%</Text>}
                    </View>
                  )}
                </View>
                {cheapestPlatform && (
                  <Text style={styles.cheapestPlatformHint}>
                    Lowest price on {getPlatformBadge(cheapestPlatform).name}
                  </Text>
                )}
              </>
            );
          })()}
          
          {Array.isArray(product?.listings) && product.listings.length > 0 ? (
            <View>
              {/* If multiple variants, show grouped comparison */}
              {(() => {
                const variantGroups = groupListingsByVariant();
                return variantGroups.length > 1 ? (
                  <View style={styles.variantComparisonNote}>
                    <Ionicons name="information-circle" size={16} color={COLORS.info} />
                    <Text style={styles.variantComparisonText}>
                      Showing {variantGroups.length} variant(s) across {product.listings.length} platform(s)
                    </Text>
                  </View>
                ) : null;
              })()}
              
              <FlatList
                data={product.listings.filter(item => item && item.id)}
                renderItem={renderListingCard}
                keyExtractor={(item, index) => `listing-${item?.id || `index-${index}`}`}
                scrollEnabled={false}
              />

              <View style={styles.comparisonSubSection}>
                <View style={styles.comparisonSubHeader}>
                  <Text style={styles.comparisonSubTitle}>Same Product On Other Platforms</Text>
                  {!crossPlatformLoading && otherPlatformListings.length > 0 && (
                    <Text style={styles.comparisonSubHint}>{otherPlatformListings.length} option{otherPlatformListings.length > 1 ? 's' : ''}</Text>
                  )}
                </View>

                {crossPlatformLoading ? (
                  <View style={styles.chartLoading}>
                    <ActivityIndicator color={COLORS.primary} />
                    <Text style={{ marginTop: 8, color: COLORS.textSecondary }}>Checking platform availability...</Text>
                  </View>
                ) : otherPlatformListings.length > 0 ? (
                  <FlatList
                    data={otherPlatformListings}
                    horizontal
                    showsHorizontalScrollIndicator={false}
                    keyExtractor={(item, index) => `same-product-${item?.id || index}`}
                    contentContainerStyle={{ paddingHorizontal: 2, paddingBottom: 4 }}
                    renderItem={({ item }) => {
                      const badge = getPlatformBadge(item?.platform || 'amazon');
                      const isInStock = item?.inStock !== false;
                      return (
                        <TouchableOpacity
                          style={styles.crossPlatformCard}
                          activeOpacity={0.85}
                          onPress={() => handleOpenUrl(item?.url)}
                        >
                          <View style={styles.crossPlatformHeader}>
                            <View style={[styles.platformTag, { backgroundColor: badge.color, marginBottom: 0 }]}>
                              <Text style={styles.platformTagText}>{badge.icon}{badge.name}</Text>
                            </View>
                          </View>
                          <Text style={styles.crossPlatformPrice}>{formatPrice(item?.price || 0)}</Text>
                          {item?.originalPrice && item.originalPrice > item.price && (
                            <Text style={styles.crossPlatformOriginalPrice}>{formatPrice(item.originalPrice)}</Text>
                          )}
                          <Text style={[styles.crossPlatformStock, { color: isInStock ? COLORS.success : COLORS.error }]}>
                            {isInStock ? 'In stock' : 'Out of stock'}
                          </Text>
                          <TouchableOpacity
                            style={styles.crossPlatformCta}
                            onPress={() => handleOpenUrl(item?.url)}
                          >
                            <Text style={styles.crossPlatformCtaText}>Open Deal</Text>
                          </TouchableOpacity>
                        </TouchableOpacity>
                      );
                    }}
                  />
                ) : (
                  <View style={styles.noPriceHistory}>
                    <Text style={{ color: COLORS.textSecondary }}>
                      No confirmed same-product listing found on other platforms yet.
                    </Text>
                  </View>
                )}
              </View>
            </View>
          ) : (
            <Text style={{ color: COLORS.textSecondary }}>No price listings available</Text>
          )}
        </View>

        {/* Price History Chart */}
        <View style={styles.chartSection}>
          <View style={styles.chartHeader}>
            <Text style={styles.sectionTitle}>Price History (120 Days)</Text>
            {priceHistory && selectedPlatform && (
              <Text style={styles.platformPriceInfo}>
                {getPlatformBadge(selectedPlatform).name}
              </Text>
            )}
          </View>
          
          {priceHistoryStatus === 'loading' && (
            <View style={styles.chartLoading}>
              <ActivityIndicator color={COLORS.primary} />
              <Text style={{ marginTop: 8, color: COLORS.textSecondary }}>Loading price history...</Text>
            </View>
          )}
          
          {sanitizedHistory.length > 0 ? (
            <View style={styles.priceHistoryCard}>
              {/* Price Stats Grid */}
              <View style={styles.priceStatsGrid}>
                <View style={styles.priceStatItem}>
                  <Text style={styles.priceStatLabel}>Lowest Price</Text>
                  <Text style={styles.priceStatValue}>
                    {formatPrice(Math.min(...sanitizedHistory.map((p) => Number(p.price || 0))))}
                  </Text>
                </View>
                <View style={styles.priceStatItem}>
                  <Text style={styles.priceStatLabel}>Highest Price</Text>
                  <Text style={styles.priceStatValue}>
                    {formatPrice(Math.max(...sanitizedHistory.map((p) => Number(p.price || 0))))}
                  </Text>
                </View>
                <View style={styles.priceStatItem}>
                  <Text style={styles.priceStatLabel}>Average Price</Text>
                  <Text style={styles.priceStatValue}>
                    {formatPrice(
                      sanitizedHistory.reduce((sum, p) => sum + Number(p.price || 0), 0) /
                      sanitizedHistory.length
                    )}
                  </Text>
                </View>
              </View>
              
              {/* Price Trend */}
              {priceHistory.price_drop_percentage && (
                <View style={styles.priceTrendBox}>
                  <Ionicons 
                    name={parseFloat(priceHistory.price_drop_percentage) > 0 ? "arrow-down" : "arrow-up"} 
                    size={20} 
                    color={parseFloat(priceHistory.price_drop_percentage) > 0 ? COLORS.success : COLORS.error} 
                  />
                  <Text style={[
                    styles.priceTrendText,
                    { color: parseFloat(priceHistory.price_drop_percentage) > 0 ? COLORS.success : COLORS.error }
                  ]}>
                    {parseFloat(priceHistory.price_drop_percentage) > 0 ? 'Dropped' : 'Increased'} {Math.abs(priceHistory.price_drop_percentage)}% in last 120 days
                  </Text>
                </View>
              )}

              {(priceHistory?.recommendation || hasObservedWeeklyChange || predictionAvailable || recommendationReasons.length > 0 || priceHistory?.upcoming_sale_event) && (
                <View style={styles.recommendationCard}>
                  <View style={styles.recommendationHeader}>
                    <View style={styles.recommendationTitleWrap}>
                      <Ionicons
                        name={recommendationConfig.icon}
                        size={18}
                        color={recommendationConfig.color}
                      />
                      <Text style={[styles.recommendationTitle, { color: recommendationConfig.color }]}>
                        {recommendationConfig.label}
                      </Text>
                    </View>
                    {predictionAvailable && confidenceScore > 0 && (
                      <View style={styles.confidenceBadge}>
                        <Text style={styles.confidenceText}>{Math.round(confidenceScore)}% confidence</Text>
                      </View>
                    )}
                  </View>

                  <View style={styles.predictionGrid}>
                    <View style={styles.predictionItem}>
                      <Text style={styles.predictionLabel}>History Coverage</Text>
                      <Text style={styles.predictionValue}>{dataPointsCount} points / {historySpanDays} days</Text>
                    </View>
                    <View style={styles.predictionItem}>
                      <Text style={styles.predictionLabel}>Last 7 Days (Observed)</Text>
                      {hasObservedWeeklyChange ? (
                        <>
                          <Text
                            style={[
                              styles.predictionValue,
                              { color: observedChange7d <= 0 ? COLORS.success : COLORS.error },
                            ]}
                          >
                            {observedChange7d <= 0
                              ? `${Math.abs(observedChange7d).toFixed(1)}% down`
                              : `${observedChange7d.toFixed(1)}% up`}
                          </Text>
                          {hasObservedDropAmount && observedDropAmount7d > 0 && (
                            <Text style={styles.predictionSubText}>Drop: {formatPrice(observedDropAmount7d)}</Text>
                          )}
                        </>
                      ) : (
                        <Text style={styles.predictionSubText}>Not enough recent points</Text>
                      )}
                    </View>
                  </View>

                  {predictionAvailable && hasPredictedChange7d ? (
                    <Text
                      style={[
                        styles.predictionDelta,
                        { color: predictedChange7d <= 0 ? COLORS.success : COLORS.error },
                      ]}
                    >
                      Next 7-day trend signal: {predictedChange7d <= -0.5
                        ? `likely drop around ${Math.abs(predictedChange7d).toFixed(1)}%`
                        : predictedChange7d >= 0.5
                          ? `likely rise around ${predictedChange7d.toFixed(1)}%`
                          : 'likely flat movement'}
                    </Text>
                  ) : (
                    <Text style={styles.insufficientDataText}>
                      Honest mode: forecast is hidden until enough history is available.
                    </Text>
                  )}

                  {priceHistory?.upcoming_sale_event && (
                    <Text style={styles.saleEventHint}>
                      Upcoming: {priceHistory.upcoming_sale_event}
                      {priceHistory?.days_until_sale_event !== null && priceHistory?.days_until_sale_event !== undefined
                        ? ` (${priceHistory.days_until_sale_event} day${Number(priceHistory.days_until_sale_event) === 1 ? '' : 's'})`
                        : ''}
                    </Text>
                  )}

                  {recommendationReasons.map((reason, idx) => (
                    <Text key={`reason-${idx}`} style={styles.recommendationReason}>
                      - {reason}
                    </Text>
                  ))}

                  {insightBasis.length > 0 && (
                    <Text style={styles.honestyNote}>
                      Based on: {insightBasis.join(' | ')}
                    </Text>
                  )}
                </View>
              )}

              {/* Recent timeline */}
              <View style={styles.debugTimelineContainer}>
                <View style={styles.debugTimelineHeader}>
                  <Text style={styles.debugTimelineTitle}>Recent Price Updates</Text>
                  <Text style={styles.debugTimelineSubtitle}>Newest first</Text>
                </View>

                {sanitizedHistory
                  .slice()
                  .sort((a, b) => new Date(b.date) - new Date(a.date))
                  .slice(0, 8)
                  .map((point, idx) => {
                    const pointDate = new Date(point.date);
                    return (
                      <View key={`ph-${idx}-${point.date}`} style={styles.debugTimelineRow}>
                        <Text style={styles.debugTimelineTime}>
                          {pointDate.toLocaleString('en-IN', {
                            month: 'short',
                            day: '2-digit',
                            hour: '2-digit',
                            minute: '2-digit',
                            hour12: true,
                          })}
                        </Text>
                        <Text style={styles.debugTimelinePrice}>{formatPrice(point.price)}</Text>
                      </View>
                    );
                  })}
              </View>
            </View>
          ) : priceHistoryStatus !== 'loading' && (
            <View style={styles.noPriceHistory}>
              <Text style={{ color: COLORS.textSecondary }}>
                No price history available for this product on {getPlatformBadge(selectedPlatform || 'amazon').name}
              </Text>
            </View>
          )}
        </View>

        {/* Similar Products */}
        <View style={styles.chartSection}>
          <View style={styles.chartHeader}>
            <Text style={styles.sectionTitle}>Similar Products</Text>
          </View>
          {similarLoading ? (
            <View style={styles.chartLoading}>
              <ActivityIndicator color={COLORS.primary} />
              <Text style={{ marginTop: 8, color: COLORS.textSecondary }}>Loading similar products...</Text>
            </View>
          ) : similarProducts.length > 0 ? (
            <FlatList
              data={similarProducts}
              horizontal
              showsHorizontalScrollIndicator={false}
              keyExtractor={(item, index) => `similar-${item?.id || item?.product_id || index}`}
              contentContainerStyle={{ paddingHorizontal: 16, paddingBottom: 10 }}
              renderItem={({ item }) => {
                const pid = item?.id || item?.product_id;
                const listing = Array.isArray(item?.listings) && item.listings.length > 0 ? item.listings[0] : null;
                const imageUrl = item?.image_url || listing?.image_url || null;
                const price = item?.best_price || listing?.current_price || 0;
                return (
                  <TouchableOpacity
                    style={styles.similarCard}
                    activeOpacity={0.8}
                    onPress={() => pid && navigation.push('ProductDetail', { productId: pid })}
                  >
                    <View style={styles.similarImageWrap}>
                      {imageUrl ? (
                        <Image source={{ uri: imageUrl }} style={styles.similarImage} resizeMode="cover" />
                      ) : (
                        <View style={styles.imagePlaceholder}>
                          <Ionicons name="image-outline" size={28} color={COLORS.gray400} />
                        </View>
                      )}
                    </View>
                    <View style={{ padding: 10 }}>
                      <Text style={styles.similarTitle} numberOfLines={2}>{item?.title || 'Product'}</Text>
                      <Text style={styles.similarPrice}>{formatPrice(price)}</Text>
                    </View>
                  </TouchableOpacity>
                );
              }}
            />
          ) : (
            <View style={styles.noPriceHistory}>
              <Text style={{ color: COLORS.textSecondary }}>No similar products found yet.</Text>
            </View>
          )}
        </View>

      </ScrollView>

      {/* ✅ NEW: Floating Wishlist Button */}
      {product && productId && (
        <View style={styles.floatingButtonContainer}>
          <WishlistHeaderButton 
            productId={productId} 
            product={{
              ...product,
              id: productId,
              product_id: productId,
            }} 
          />
        </View>
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
    backgroundColor: '#F3F6FA',
  },

  scrollContent: {
    paddingBottom: 24,
  },

  loadingContainer: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    paddingHorizontal: 24,
  },

  loadingText: {
    marginTop: 12,
    fontSize: 15,
    fontWeight: '500',
    color: COLORS.textSecondary,
  },

  emptyContainer: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    paddingHorizontal: 24,
  },

  emptyText: {
    marginTop: 12,
    fontSize: 17,
    fontWeight: '600',
    color: COLORS.textPrimary,
    textAlign: 'center',
  },

  header: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginHorizontal: 12,
    marginTop: 8,
    paddingHorizontal: 12,
    paddingVertical: 12,
    backgroundColor: COLORS.white,
    borderRadius: 14,
    borderWidth: 1,
    borderColor: '#E7ECF2',
    shadowColor: '#0B1A33',
    shadowOffset: { width: 0, height: 6 },
    shadowOpacity: 0.08,
    shadowRadius: 12,
    elevation: 2,
  },

  backButton: {
    width: 36,
    height: 36,
    borderRadius: 18,
    backgroundColor: COLORS.gray100,
    justifyContent: 'center',
    alignItems: 'center',
  },

  backButtonSmall: {
    marginTop: 16,
    backgroundColor: COLORS.primary,
    borderRadius: 10,
    paddingHorizontal: 18,
    paddingVertical: 10,
  },

  backButtonText: {
    color: COLORS.white,
    fontSize: 15,
    fontWeight: '700',
  },

  headerTitle: {
    fontSize: 18,
    fontWeight: '700',
    color: COLORS.textPrimary,
    letterSpacing: 0.2,
  },

  imageContainer: {
    marginTop: 12,
    marginHorizontal: 12,
    height: 280,
    backgroundColor: COLORS.white,
    borderRadius: 18,
    borderWidth: 1,
    borderColor: '#E7ECF2',
    justifyContent: 'center',
    alignItems: 'center',
    overflow: 'hidden',
  },

  productImage: {
    width: '90%',
    height: '90%',
  },

  imagePlaceholder: {
    width: '100%',
    height: '100%',
    justifyContent: 'center',
    alignItems: 'center',
    backgroundColor: COLORS.gray100,
  },

  productSection: {
    marginTop: 12,
    marginHorizontal: 12,
    padding: 16,
    backgroundColor: COLORS.white,
    borderRadius: 16,
    borderWidth: 1,
    borderColor: '#E7ECF2',
  },

  productTitle: {
    fontSize: 22,
    fontWeight: '700',
    color: COLORS.textPrimary,
    marginBottom: 14,
    lineHeight: 30,
  },

  liveRefreshButton: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: COLORS.primary,
    borderRadius: 12,
    paddingVertical: 11,
    paddingHorizontal: 14,
    marginBottom: 14,
    gap: 8,
  },

  liveRefreshButtonDisabled: {
    opacity: 0.8,
  },

  liveRefreshButtonText: {
    color: COLORS.white,
    fontSize: 14,
    fontWeight: '700',
  },

  priceSection: {
    marginBottom: 10,
  },

  bestPrice: {
    fontSize: 30,
    fontWeight: '700',
    color: COLORS.primary,
    marginBottom: 6,
  },

  originalPrice: {
    fontSize: 14,
    color: COLORS.textSecondary,
    textDecorationLine: 'line-through',
    marginBottom: 8,
  },

  discountBadgeLarge: {
    backgroundColor: COLORS.error,
    borderRadius: 8,
    paddingHorizontal: 12,
    paddingVertical: 6,
    alignSelf: 'flex-start',
    marginBottom: 8,
  },

  discountBadgeText: {
    color: COLORS.white,
    fontSize: 14,
    fontWeight: '600',
  },

  priceUpdateInfo: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    paddingTop: 10,
    borderTopWidth: 1,
    borderTopColor: COLORS.gray200,
  },

  priceUpdateText: {
    fontSize: 12,
    color: COLORS.gray500,
    fontStyle: 'italic',
  },

  ratingSection: {
    flexDirection: 'row',
    alignItems: 'center',
    marginTop: 6,
  },

  ratingStars: {
    flexDirection: 'row',
    marginRight: 8,
  },

  ratingValue: {
    fontSize: 15,
    fontWeight: '600',
    color: COLORS.textPrimary,
  },

  reviewCountValue: {
    marginLeft: 4,
    fontSize: 13,
    color: COLORS.textSecondary,
  },

  specsSection: {
    marginTop: 12,
    marginHorizontal: 12,
    padding: 16,
    backgroundColor: COLORS.white,
    borderRadius: 16,
    borderWidth: 1,
    borderColor: '#E7ECF2',
  },

  sectionTitle: {
    fontSize: 17,
    fontWeight: '700',
    color: COLORS.textPrimary,
    marginBottom: 14,
  },

  specItem: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingVertical: 10,
    borderBottomWidth: 1,
    borderBottomColor: COLORS.gray200,
  },

  specLabel: {
    fontSize: 14,
    color: COLORS.textSecondary,
  },

  specValue: {
    fontSize: 14,
    fontWeight: '600',
    color: COLORS.textPrimary,
    flex: 1,
    textAlign: 'right',
    marginLeft: 12,
  },

  platformSection: {
    marginTop: 12,
    marginHorizontal: 12,
    padding: 16,
    backgroundColor: COLORS.white,
    borderRadius: 16,
    borderWidth: 1,
    borderColor: '#E7ECF2',
  },

  platformHeaderRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 12,
  },

  platformCountBadge: {
    backgroundColor: '#FFF2EC',
    paddingHorizontal: 10,
    paddingVertical: 4,
    borderRadius: 12,
    borderWidth: 1,
    borderColor: '#FFD6C5',
  },

  platformCountText: {
    fontSize: 12,
    fontWeight: '600',
    color: COLORS.primary,
  },

  platformSelector: {
    backgroundColor: COLORS.white,
    borderRadius: 10,
    paddingVertical: 10,
    paddingHorizontal: 12,
    marginBottom: 8,
    borderWidth: 1,
    borderColor: '#DCE3EB',
  },

  platformSelectorSelected: {
    borderColor: COLORS.primary,
    backgroundColor: '#FFF2EC',
  },

  platformSelectorText: {
    fontSize: 14,
    color: COLORS.textPrimary,
    fontWeight: '500',
  },

  platformSelectorTextSelected: {
    color: COLORS.primary,
    fontWeight: '600',
  },

  comparisonSection: {
    marginTop: 12,
    marginHorizontal: 12,
    padding: 16,
    backgroundColor: COLORS.white,
    borderRadius: 16,
    borderWidth: 1,
    borderColor: '#E7ECF2',
  },

  listingCard: {
    backgroundColor: '#F8FAFD',
    borderRadius: 14,
    padding: 12,
    marginBottom: 12,
    borderWidth: 1,
    borderColor: '#E0E7EF',
  },

  platformTag: {
    alignSelf: 'flex-start',
    borderRadius: 6,
    paddingHorizontal: 9,
    paddingVertical: 5,
    marginBottom: 10,
  },

  platformTagText: {
    color: COLORS.white,
    fontSize: 12,
    fontWeight: '700',
  },

  listingPriceContainer: {
    flexDirection: 'row',
    alignItems: 'center',
    marginBottom: 8,
  },

  listingPrice: {
    fontSize: 20,
    fontWeight: '700',
    color: COLORS.primary,
  },

  listingOriginalPrice: {
    marginLeft: 8,
    fontSize: 12,
    color: COLORS.textSecondary,
    textDecorationLine: 'line-through',
  },

  discountTag: {
    backgroundColor: COLORS.error,
    borderRadius: 6,
    paddingHorizontal: 6,
    paddingVertical: 2,
    alignSelf: 'flex-start',
    marginBottom: 8,
  },

  discountTagText: {
    color: COLORS.white,
    fontSize: 11,
    fontWeight: '600',
  },

  ratingSmall: {
    flexDirection: 'row',
    alignItems: 'center',
    marginBottom: 8,
  },

  ratingSmallText: {
    marginLeft: 4,
    fontSize: 12,
    fontWeight: '500',
    color: COLORS.textPrimary,
  },

  stockStatus: {
    borderLeftWidth: 3,
    paddingLeft: 8,
    marginBottom: 8,
  },

  stockText: {
    fontSize: 12,
    fontWeight: '600',
  },

  buyButton: {
    flexDirection: 'row',
    backgroundColor: COLORS.primary,
    borderRadius: 10,
    paddingVertical: 10,
    paddingHorizontal: 16,
    justifyContent: 'center',
    alignItems: 'center',
  },

  buyButtonText: {
    color: COLORS.white,
    fontSize: 14,
    fontWeight: '600',
    marginLeft: 6,
  },

  chartSection: {
    marginTop: 12,
    marginHorizontal: 12,
    padding: 16,
    backgroundColor: COLORS.white,
    borderRadius: 16,
    borderWidth: 1,
    borderColor: '#E7ECF2',
  },

  chartLoading: {
    backgroundColor: '#F8FAFD',
    borderRadius: 12,
    paddingVertical: 20,
    justifyContent: 'center',
    alignItems: 'center',
  },

  similarCard: {
    width: 186,
    marginRight: 12,
    backgroundColor: COLORS.white,
    borderRadius: 14,
    overflow: 'hidden',
    borderWidth: 1,
    borderColor: '#E0E7EF',
    shadowColor: '#0B1A33',
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.06,
    shadowRadius: 8,
    elevation: 1,
  },

  crossPlatformCard: {
    width: 176,
    marginRight: 12,
    backgroundColor: COLORS.white,
    borderRadius: 14,
    borderWidth: 1,
    borderColor: '#E0E7EF',
    padding: 12,
  },

  crossPlatformHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 10,
  },

  crossPlatformPrice: {
    fontSize: 20,
    fontWeight: '700',
    color: COLORS.primary,
  },

  crossPlatformOriginalPrice: {
    marginTop: 4,
    fontSize: 12,
    color: COLORS.textSecondary,
    textDecorationLine: 'line-through',
  },

  crossPlatformStock: {
    marginTop: 8,
    fontSize: 12,
    fontWeight: '600',
  },

  crossPlatformCta: {
    marginTop: 10,
    borderRadius: 8,
    backgroundColor: COLORS.primary,
    paddingVertical: 8,
    alignItems: 'center',
  },

  crossPlatformCtaText: {
    fontSize: 12,
    fontWeight: '700',
    color: COLORS.white,
  },

  similarImageWrap: {
    width: '100%',
    height: 126,
    backgroundColor: COLORS.gray100,
  },

  similarImage: {
    width: '100%',
    height: '100%',
  },

  similarTitle: {
    fontSize: 13,
    fontWeight: '500',
    color: COLORS.textPrimary,
    minHeight: 36,
    lineHeight: 18,
  },

  similarPrice: {
    marginTop: 8,
    fontSize: 15,
    fontWeight: '700',
    color: COLORS.primary,
  },

  chartPlaceholder: {
    backgroundColor: '#F8FAFD',
    borderRadius: 12,
    padding: 16,
  },

  chartPlaceholderText: {
    fontSize: 14,
    color: COLORS.textPrimary,
    marginVertical: 6,
    fontWeight: '500',
  },

  // ✅ NEW: Variant Details Section Styles
  variantSection: {
    marginTop: 12,
    marginHorizontal: 12,
    padding: 16,
    backgroundColor: COLORS.white,
    borderRadius: 16,
    borderWidth: 1,
    borderColor: '#E7ECF2',
  },

  variantTypeContainer: {
    marginBottom: 16,
  },

  variantTypeBadge: {
    borderRadius: 8,
    paddingVertical: 10,
    paddingHorizontal: 16,
    alignSelf: 'flex-start',
  },

  variantTypeText: {
    color: COLORS.white,
    fontSize: 14,
    fontWeight: '600',
  },

  variantSpecsGrid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    marginHorizontal: -8,
    marginBottom: 12,
  },

  variantSpecItem: {
    width: '33.33%',
    paddingHorizontal: 8,
    marginBottom: 12,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: '#F8FAFD',
    borderRadius: 10,
    borderWidth: 1,
    borderColor: '#E0E7EF',
    paddingVertical: 12,
  },

  variantSpecLabel: {
    fontSize: 12,
    color: COLORS.textSecondary,
    marginBottom: 4,
  },

  variantSpecValue: {
    fontSize: 14,
    fontWeight: '600',
    color: COLORS.primary,
  },

  fingerprintInfo: {
    backgroundColor: '#F8FAFD',
    borderRadius: 8,
    paddingHorizontal: 12,
    paddingVertical: 10,
    borderWidth: 1,
    borderColor: '#E0E7EF',
  },

  fingerprintLabel: {
    fontSize: 11,
    color: COLORS.textSecondary,
    marginBottom: 4,
  },

  fingerprintValue: {
    fontSize: 10,
    fontFamily: 'monospace',
    color: COLORS.textPrimary,
    fontWeight: '500',
  },

  // ✅ NEW: Enhanced Price Comparison & History Styles
  comparisonHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 8,
  },

  comparisonTitleRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },

  listingCountBadge: {
    backgroundColor: '#FFF2EC',
    paddingHorizontal: 10,
    paddingVertical: 4,
    borderRadius: 12,
    borderWidth: 1,
    borderColor: '#FFD6C5',
  },

  listingCountText: {
    fontSize: 12,
    fontWeight: '600',
    color: COLORS.primary,
  },

  bestPriceTag: {
    backgroundColor: COLORS.success + '20',
    borderRadius: 6,
    paddingHorizontal: 10,
    paddingVertical: 6,
    alignItems: 'center',
  },

  bestPriceText: {
    color: COLORS.success,
    fontSize: 12,
    fontWeight: '600',
  },

  savingsText: {
    color: COLORS.success,
    fontSize: 11,
    marginTop: 2,
  },

  cheapestPlatformHint: {
    fontSize: 11,
    color: COLORS.info,
    marginBottom: 12,
    fontStyle: 'italic',
  },

  comparisonSubSection: {
    marginTop: 12,
    paddingTop: 12,
    borderTopWidth: 1,
    borderTopColor: COLORS.gray200,
  },

  comparisonSubHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 10,
  },

  comparisonSubTitle: {
    fontSize: 14,
    fontWeight: '700',
    color: COLORS.textPrimary,
  },

  comparisonSubHint: {
    fontSize: 11,
    color: COLORS.textSecondary,
  },

  variantComparisonNote: {
    flexDirection: 'row',
    backgroundColor: COLORS.infoLight,
    borderRadius: 8,
    paddingHorizontal: 12,
    paddingVertical: 10,
    marginBottom: 12,
    alignItems: 'center',
  },

  variantComparisonText: {
    fontSize: 12,
    color: COLORS.info,
    marginLeft: 8,
    flex: 1,
  },

  chartHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 12,
  },

  platformPriceInfo: {
    fontSize: 12,
    color: COLORS.textSecondary,
    fontStyle: 'italic',
  },

  priceHistoryCard: {
    backgroundColor: '#F8FAFD',
    borderRadius: 12,
    padding: 16,
    borderWidth: 1,
    borderColor: '#E0E7EF',
  },

  priceStatsGrid: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    marginBottom: 16,
  },

  priceStatItem: {
    flex: 1,
    alignItems: 'center',
  },

  priceStatLabel: {
    fontSize: 11,
    color: COLORS.textSecondary,
    marginBottom: 4,
  },

  priceStatValue: {
    fontSize: 14,
    fontWeight: '700',
    color: COLORS.textPrimary,
  },

  priceTrendBox: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: COLORS.white,
    borderRadius: 10,
    borderWidth: 1,
    borderColor: '#E0E7EF',
    padding: 12,
    marginBottom: 12,
  },

  priceTrendText: {
    fontSize: 13,
    fontWeight: '600',
    marginLeft: 8,
  },

  recommendationCard: {
    backgroundColor: COLORS.white,
    borderRadius: 10,
    borderWidth: 1,
    borderColor: '#E0E7EF',
    padding: 12,
    marginBottom: 12,
  },

  recommendationHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 10,
  },

  recommendationTitleWrap: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
  },

  recommendationTitle: {
    fontSize: 14,
    fontWeight: '700',
  },

  confidenceBadge: {
    backgroundColor: '#EFF6FF',
    borderRadius: 999,
    borderWidth: 1,
    borderColor: '#D8E7FF',
    paddingHorizontal: 8,
    paddingVertical: 4,
  },

  confidenceText: {
    fontSize: 11,
    color: COLORS.info,
    fontWeight: '600',
  },

  predictionGrid: {
    flexDirection: 'row',
    gap: 8,
  },

  predictionItem: {
    flex: 1,
    backgroundColor: '#F8FAFD',
    borderRadius: 8,
    borderWidth: 1,
    borderColor: '#E0E7EF',
    padding: 10,
  },

  predictionLabel: {
    fontSize: 11,
    color: COLORS.textSecondary,
  },

  predictionValue: {
    marginTop: 4,
    fontSize: 14,
    fontWeight: '700',
    color: COLORS.textPrimary,
  },

  predictionSubText: {
    marginTop: 4,
    fontSize: 11,
    color: COLORS.textSecondary,
  },

  predictionDelta: {
    marginTop: 10,
    fontSize: 12,
    fontWeight: '600',
  },

  insufficientDataText: {
    marginTop: 10,
    fontSize: 12,
    color: COLORS.textSecondary,
    fontStyle: 'italic',
  },

  saleEventHint: {
    marginTop: 8,
    fontSize: 12,
    color: COLORS.info,
  },

  recommendationReason: {
    marginTop: 6,
    fontSize: 12,
    color: COLORS.textSecondary,
    lineHeight: 18,
  },

  honestyNote: {
    marginTop: 10,
    fontSize: 11,
    color: COLORS.gray500,
    fontStyle: 'italic',
  },

  chartComingSoon: {
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: 20,
    borderTopWidth: 1,
    borderTopColor: COLORS.gray200,
  },

  chartComingSoonText: {
    fontSize: 12,
    color: COLORS.gray400,
    marginTop: 8,
  },

  debugTimelineContainer: {
    marginTop: 8,
    borderTopWidth: 1,
    borderTopColor: COLORS.gray200,
    paddingTop: 12,
  },

  debugTimelineHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 8,
  },

  debugTimelineTitle: {
    fontSize: 13,
    fontWeight: '700',
    color: COLORS.textPrimary,
  },

  debugTimelineSubtitle: {
    fontSize: 11,
    color: COLORS.textSecondary,
  },

  debugTimelineRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    backgroundColor: COLORS.white,
    borderRadius: 10,
    borderWidth: 1,
    borderColor: '#E0E7EF',
    paddingHorizontal: 10,
    paddingVertical: 8,
    marginBottom: 6,
  },

  debugTimelineTime: {
    fontSize: 12,
    color: COLORS.textSecondary,
    flex: 1,
  },

  debugTimelinePrice: {
    fontSize: 13,
    fontWeight: '700',
    color: COLORS.primary,
    marginLeft: 12,
  },

  noPriceHistory: {
    paddingVertical: 16,
    alignItems: 'center',
  },

  floatingButtonContainer: {
    position: 'absolute',
    bottom: 24,
    right: 20,
    zIndex: 100,
  },
});

export default ProductDetailScreen;
