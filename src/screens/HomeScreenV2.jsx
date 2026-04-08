import React, { useEffect, useCallback, useMemo } from 'react';
import {
  View, Text, StyleSheet, ScrollView, TouchableOpacity,
  RefreshControl, StatusBar,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useFocusEffect, useNavigation } from '@react-navigation/native';
import { useDispatch, useSelector } from 'react-redux';
import { Ionicons } from '@expo/vector-icons';

import BannerCarousel from '../components/home/BannerCarousel';
import QuickCategories from '../components/home/QuickCategories';
import ProductSection from '../components/home/ProductSection';

import {
  fetchTrending,
  selectLastSearchQuery,
  selectSearchResults,
  selectTrendingProducts,
  selectTrendingStatus,
} from '../store/searchSlice';
import { selectThemePalette } from '../store/themeSlice';
import { homeAPI } from '../services/homeApi';
import { toEpochMs } from '../utils/formatters';
import { COLORS, APP } from '../utils/constants';

const CATEGORY_SECTIONS = [
  {
    id: 'mobiles',
    title: 'Mobiles',
    subtitle: 'Latest smartphones and launches',
    emoji: '📱',
    accentColor: '#2F80ED',
    query: 'smartphone 5g',
    keywords: ['phone', 'smartphone', 'iphone', 'samsung', 'redmi', 'oneplus', 'realme', 'pixel', 'oppo', 'vivo'],
  },
  {
    id: 'tablets',
    title: 'Tablets',
    subtitle: 'iPad and Android tablets',
    emoji: '📟',
    accentColor: '#0EA5E9',
    query: 'tablet ipad',
    keywords: ['ipad', 'tablet', 'tab'],
  },
  {
    id: 'laptops',
    title: 'Laptops',
    subtitle: 'Work, gaming, and study picks',
    emoji: '💻',
    accentColor: '#00A67E',
    query: 'laptop',
    keywords: ['laptop', 'notebook', 'macbook', 'chromebook', 'gaming laptop', 'ultrabook'],
  },
  {
    id: 'mobile_accessories',
    title: 'Mobile Accessories',
    subtitle: 'Covers, chargers, cables, and audio',
    emoji: '🎧',
    accentColor: '#0F766E',
    query: 'mobile cover charger cable',
    keywords: ['cover', 'case', 'tempered', 'protector', 'charger', 'cable', 'earbuds', 'earphones', 'power bank', 'magsafe', 'airpods'],
  },
  {
    id: 'laptop_accessories',
    title: 'Laptop Accessories',
    subtitle: 'Bags, keyboards, docks, and more',
    emoji: '🖱️',
    accentColor: '#2563EB',
    query: 'laptop accessories mouse keyboard',
    keywords: ['laptop bag', 'sleeve', 'mouse', 'keyboard', 'cooling pad', 'dock', 'usb hub', 'webcam', 'external ssd', 'hard disk'],
  },
  {
    id: 'fashion',
    title: 'Fashion',
    subtitle: 'Style deals for everyday wear',
    emoji: '👗',
    accentColor: '#F97316',
    query: 'fashion clothing men women',
    keywords: ['shirt', 'tshirt', 't-shirt', 'jeans', 'dress', 'saree', 'kurta', 'shoes', 'fashion', 'watch'],
  },
  {
    id: 'home_kitchen',
    title: 'Home & Kitchen',
    subtitle: 'Kitchen and home essentials',
    emoji: '🏠',
    accentColor: '#9333EA',
    query: 'home kitchen essentials',
    keywords: ['mixer', 'kitchen', 'cookware', 'vacuum', 'chair', 'table', 'mattress', 'home', 'furniture'],
  },
  {
    id: 'books',
    title: 'Books',
    subtitle: 'Bestsellers and must-read picks',
    emoji: '📚',
    accentColor: '#B45309',
    query: 'books novel bestseller',
    keywords: ['book', 'novel', 'author', 'paperback', 'hardcover', 'bestseller'],
  },
];

const CROSS_PLATFORM_HIGHLIGHT_LIMIT = 24;

const toEpoch = (value) => {
  return toEpochMs(value);
};

const getStableKey = (product) => {
  const byFingerprint = product?.variant_fingerprint || product?.base_fingerprint;
  if (byFingerprint) return `fp:${String(byFingerprint).toLowerCase()}`;

  const byId = product?.product_id || product?.id;
  if (byId) return `id:${String(byId)}`;

  return `title:${String(product?.title || '').trim().toLowerCase()}`;
};

const dedupeProducts = (items) => {
  const map = new Map();

  for (const item of items || []) {
    if (!item) continue;
    const key = getStableKey(item);
    const existing = map.get(key);
    if (!existing) {
      map.set(key, item);
      continue;
    }

    const existingFreshness = Math.max(
      toEpoch(existing?.last_price_change_at),
      toEpoch(existing?.last_updated_at)
    );
    const incomingFreshness = Math.max(
      toEpoch(item?.last_price_change_at),
      toEpoch(item?.last_updated_at)
    );

    // Prefer fresher records so home cards don't stay stale.
    if (incomingFreshness >= existingFreshness) {
      map.set(key, item);
    }
  }

  return Array.from(map.values());
};

const matchCategory = (product) => {
  const searchable = `${product?.title || ''} ${product?.category || ''} ${product?.subcategory || ''} ${product?.ai_generated_essence || ''}`.toLowerCase();
  const found = CATEGORY_SECTIONS.find((category) =>
    category.keywords.some((keyword) => searchable.includes(keyword))
  );
  return found?.id || null;
};

const getCategoryRelevanceForQuery = (category, query) => {
  const normalized = String(query || '').toLowerCase().trim();
  if (!normalized) return 0;

  const words = normalized.split(/\s+/).filter(Boolean);
  if (words.length === 0) return 0;

  let score = 0;
  for (const word of words) {
    if (category.keywords.some((k) => k.includes(word) || word.includes(k))) score += 2;
    if (category.query.includes(word)) score += 1;
    if (category.title.toLowerCase().includes(word)) score += 1;
  }

  return score;
};

const getCategoryMatchStrength = (product, category) => {
  const searchable = `${product?.title || ''} ${product?.category || ''} ${product?.subcategory || ''} ${product?.ai_generated_essence || ''}`.toLowerCase();
  let score = 0;
  for (const keyword of category.keywords) {
    if (searchable.includes(keyword)) score += 1;
  }
  return score;
};

const HomeScreenV2 = () => {
  const navigation = useNavigation();
  const dispatch = useDispatch();
  const scrollRef = React.useRef(null);
  const sectionOffsetsRef = React.useRef({});

  const trending = useSelector(selectTrendingProducts) || [];
  const trendingStatus = useSelector(selectTrendingStatus);
  const searchResults = useSelector(selectSearchResults) || [];
  const lastSearchQuery = useSelector(selectLastSearchQuery) || '';
  const themePalette = useSelector(selectThemePalette);

  const [refreshing, setRefreshing] = React.useState(false);
  const [visibleItemsPerSection, setVisibleItemsPerSection] = React.useState(8);
  const [isLoadingMore, setIsLoadingMore] = React.useState(false);
  const [homeFeatured, setHomeFeatured] = React.useState([]);
  const [homeDeals, setHomeDeals] = React.useState([]);
  const [homeCategoryCounts, setHomeCategoryCounts] = React.useState({});
  const [crossPlatformHighlights, setCrossPlatformHighlights] = React.useState([]);
  const [homeDataLoading, setHomeDataLoading] = React.useState(true);

  // Fetch trending on mount
  useEffect(() => {
    if (trendingStatus === 'idle') {
      dispatch(fetchTrending());
    }
  }, []);

  const fetchHomeData = useCallback(async () => {
    setHomeDataLoading(true);
    try {
      const [featuredRes, dealsRes, categoriesRes, crossPlatformRes] = await Promise.all([
        homeAPI.getFeatured(24),
        homeAPI.getDeals(36),
        homeAPI.getCategories(),
        homeAPI.getCrossPlatformHighlights(CROSS_PLATFORM_HIGHLIGHT_LIMIT, 2),
      ]);

      setHomeFeatured(featuredRes?.success ? (featuredRes.data || []) : []);
      setHomeDeals(dealsRes?.success ? (dealsRes.data || []) : []);
      setHomeCategoryCounts(categoriesRes?.success ? (categoriesRes.data || {}) : {});
      setCrossPlatformHighlights(crossPlatformRes?.success ? (crossPlatformRes.data || []) : []);
    } catch {
      setHomeFeatured([]);
      setHomeDeals([]);
      setHomeCategoryCounts({});
      setCrossPlatformHighlights([]);
    } finally {
      setHomeDataLoading(false);
    }
  }, []);

  // Pull to refresh
  const onRefresh = useCallback(async () => {
    setRefreshing(true);
    await Promise.all([dispatch(fetchTrending()), fetchHomeData()]);
    setRefreshing(false);
  }, [dispatch, fetchHomeData]);

  useFocusEffect(
    useCallback(() => {
      Promise.all([dispatch(fetchTrending()), fetchHomeData()]);
    }, [dispatch, fetchHomeData])
  );

  // Derived sections from trending data
  const trendingProducts = useMemo(() => trending, [trending]);

  const mergedFeedProducts = useMemo(() => {
    return dedupeProducts([
      ...searchResults,
      ...homeDeals,
      ...homeFeatured,
      ...trending,
    ]);
  }, [homeDeals, homeFeatured, searchResults, trending]);

  const relatedSearchProducts = useMemo(() => {
    if (!lastSearchQuery || !Array.isArray(searchResults) || searchResults.length === 0) {
      return [];
    }

    return dedupeProducts(searchResults)
      .sort((a, b) => {
        const queryA = String(a?.title || '').toLowerCase().includes(lastSearchQuery.toLowerCase()) ? 1 : 0;
        const queryB = String(b?.title || '').toLowerCase().includes(lastSearchQuery.toLowerCase()) ? 1 : 0;
        if (queryB !== queryA) return queryB - queryA;
        return (Number(b?.discount_percentage || 0) - Number(a?.discount_percentage || 0));
      })
      .slice(0, 24);
  }, [lastSearchQuery, searchResults]);

  const crossPlatformProducts = useMemo(() => {
    const explicit = Array.isArray(crossPlatformHighlights) ? crossPlatformHighlights : [];
    const explicitValid = explicit.filter((item) => Number(item?.platform_count || 0) >= 2);
    if (explicitValid.length > 0) {
      return explicitValid;
    }

    const fallbackMap = new Map();
    for (const item of mergedFeedProducts) {
      const id = item?.product_id || item?.id;
      if (!id || fallbackMap.has(id)) continue;

      const platformCount = Number(
        item?.platform_count || (Array.isArray(item?.listings) ? item.listings.length : 0)
      );
      if (platformCount >= 2) {
        fallbackMap.set(id, item);
      }
    }

    return Array.from(fallbackMap.values()).slice(0, CROSS_PLATFORM_HIGHLIGHT_LIMIT);
  }, [crossPlatformHighlights, mergedFeedProducts]);

  const newArrivals = useMemo(() => {
    const trendingIds = new Set((trendingProducts || []).map((item) => item?.product_id || item?.id).filter(Boolean));
    const featuredItems = Array.isArray(homeFeatured) ? homeFeatured : [];

    const unique = featuredItems
      .filter((item) => {
        const id = item?.product_id || item?.id;
        return Boolean(id) && !trendingIds.has(id);
      })
      .slice(0, 18);

    if (unique.length > 0) {
      return unique;
    }

    return featuredItems.slice(0, 18);
  }, [homeFeatured, trendingProducts]);

  const bestDeals = useMemo(() => {
    const source = homeDeals.length > 0 ? homeDeals : trending;
    return [...source]
      .filter(p => (p.discount_percentage || 0) >= 10)
      .sort((a, b) => (b.discount_percentage || 0) - (a.discount_percentage || 0));
  }, [homeDeals, trending]);

  const recentPriceChanges = useMemo(() => {
    const source = mergedFeedProducts.length > 0 ? mergedFeedProducts : (homeDeals.length > 0 ? homeDeals : trending);
    return dedupeProducts(source)
      .filter((p) => Boolean(p?.last_price_change_at || p?.last_updated_at || (p?.discount_percentage || 0) >= 5))
      .sort((a, b) => {
        const changeA = toEpoch(a?.last_price_change_at);
        const changeB = toEpoch(b?.last_price_change_at);
        if (changeB !== changeA) return changeB - changeA;

        const freshA = toEpoch(a?.last_updated_at);
        const freshB = toEpoch(b?.last_updated_at);
        if (freshB !== freshA) return freshB - freshA;

        return (Number(b?.discount_percentage || 0) - Number(a?.discount_percentage || 0));
      });
  }, [homeDeals, mergedFeedProducts, trending]);

  const budgetPicks = useMemo(() =>
    [...mergedFeedProducts]
      .filter(p => (p.best_price || 0) < 5000 && (p.best_price || 0) > 0),
    [mergedFeedProducts]
  );

  const categoryWiseSections = useMemo(() => {
    const grouped = CATEGORY_SECTIONS.reduce((acc, category) => {
      acc[category.id] = [];
      return acc;
    }, {});

    for (const product of mergedFeedProducts) {
      let categoryId = matchCategory(product);

      if (!categoryId) {
        let bestCategory = null;
        let bestScore = 0;
        for (const category of CATEGORY_SECTIONS) {
          const score = getCategoryMatchStrength(product, category);
          if (score > bestScore) {
            bestScore = score;
            bestCategory = category;
          }
        }
        categoryId = bestCategory?.id || null;
      }

      if (!categoryId) continue;
      grouped[categoryId].push(product);
    }

    const sections = CATEGORY_SECTIONS
      .map((category) => ({
        ...category,
        products: dedupeProducts(grouped[category.id] || []).sort((a, b) => {
          const queryBoostA = lastSearchQuery
            ? Number(String(a?.title || '').toLowerCase().includes(lastSearchQuery.toLowerCase()))
            : 0;
          const queryBoostB = lastSearchQuery
            ? Number(String(b?.title || '').toLowerCase().includes(lastSearchQuery.toLowerCase()))
            : 0;
          if (queryBoostB !== queryBoostA) return queryBoostB - queryBoostA;

          const freshA = Math.max(toEpoch(a?.last_price_change_at), toEpoch(a?.last_updated_at));
          const freshB = Math.max(toEpoch(b?.last_price_change_at), toEpoch(b?.last_updated_at));
          if (freshB !== freshA) return freshB - freshA;

          return (Number(b?.discount_percentage || 0) - Number(a?.discount_percentage || 0));
        }),
      }))
      .filter((category) => category.products.length > 0 || trendingStatus === 'loading' || homeDataLoading);

    if (!lastSearchQuery) return sections;

    return [...sections].sort((a, b) => {
      const queryRelevanceA = getCategoryRelevanceForQuery(a, lastSearchQuery);
      const queryRelevanceB = getCategoryRelevanceForQuery(b, lastSearchQuery);
      if (queryRelevanceB !== queryRelevanceA) return queryRelevanceB - queryRelevanceA;
      return b.products.length - a.products.length;
    });
  }, [homeDataLoading, lastSearchQuery, mergedFeedProducts, trendingStatus]);

  const topCategories = useMemo(() => {
    const mapped = [
      ...(relatedSearchProducts.length > 0
        ? [{
            id: 'related-search',
            label: 'For You',
            emoji: '🎯',
            query: lastSearchQuery,
            homeSectionId: 'related-search',
            bg: '#E6FFFB',
            border: '#99F6E4',
            count: relatedSearchProducts.length,
          }]
        : []),
      {
        id: 'trending',
        label: 'Trending',
        emoji: '🔥',
        query: 'trending deals',
        homeSectionId: 'trending-now',
        bg: '#FFF2E6',
        border: '#FFBE99',
        count: trendingProducts.length,
      },
      {
        id: 'new-arrivals',
        label: 'New',
        emoji: '🆕',
        query: 'latest launches',
        homeSectionId: 'new-arrivals',
        bg: '#EAF6FF',
        border: '#9FD8FF',
        count: newArrivals.length,
      },
      {
        id: 'cross-platform',
        label: 'Cross Match',
        emoji: '🔗',
        query: 'same product all platforms',
        homeSectionId: 'cross-platform-matched',
        bg: '#E9F5FF',
        border: '#8ECDF7',
        count: crossPlatformProducts.length,
      },
      {
        id: 'mobiles',
        label: 'Mobiles',
        emoji: '📱',
        query: 'smartphone 5g',
        homeSectionId: 'mobiles',
        bg: '#E8F2FF',
        border: '#A6C8FF',
        count: homeCategoryCounts.mobiles || categoryWiseSections.find((s) => s.id === 'mobiles')?.products?.length || 0,
      },
      {
        id: 'laptops',
        label: 'Laptops',
        emoji: '💻',
        query: 'laptop',
        homeSectionId: 'laptops',
        bg: '#EAF9F4',
        border: '#9FE3C9',
        count: homeCategoryCounts.laptops || categoryWiseSections.find((s) => s.id === 'laptops')?.products?.length || 0,
      },
      {
        id: 'mobile-accessories',
        label: 'Mobile Acc',
        emoji: '🎧',
        query: 'mobile cover charger',
        homeSectionId: 'mobile_accessories',
        bg: '#E8FFFA',
        border: '#7CE7CF',
        count: homeCategoryCounts.mobile_accessories || categoryWiseSections.find((s) => s.id === 'mobile_accessories')?.products?.length || 0,
      },
      {
        id: 'fashion',
        label: 'Fashion',
        emoji: '👗',
        query: 'fashion clothing',
        homeSectionId: 'fashion',
        bg: '#FFF2E8',
        border: '#FFC9A3',
        count: homeCategoryCounts.fashion || categoryWiseSections.find((s) => s.id === 'fashion')?.products?.length || 0,
      },
      {
        id: 'home-kitchen',
        label: 'Home',
        emoji: '🏠',
        query: 'home kitchen',
        homeSectionId: 'home_kitchen',
        bg: '#F3F0FF',
        border: '#CABDFF',
        count: homeCategoryCounts.home_kitchen || categoryWiseSections.find((s) => s.id === 'home_kitchen')?.products?.length || 0,
      },
      {
        id: 'books',
        label: 'Books',
        emoji: '📚',
        query: 'books bestseller',
        homeSectionId: 'books',
        bg: '#FFF9E8',
        border: '#FDE08A',
        count: homeCategoryCounts.books || categoryWiseSections.find((s) => s.id === 'books')?.products?.length || 0,
      },
    ];

    return mapped.filter((category) => category.count > 0 || trendingStatus === 'loading' || homeDataLoading);
  }, [categoryWiseSections, crossPlatformProducts.length, homeCategoryCounts, homeDataLoading, lastSearchQuery, newArrivals.length, relatedSearchProducts.length, trendingProducts.length, trendingStatus]);

  const maxItemsAvailable = useMemo(() => {
    const baseCounts = [trendingProducts.length, newArrivals.length, crossPlatformProducts.length, bestDeals.length, budgetPicks.length, recentPriceChanges.length, relatedSearchProducts.length];
    const categoryCounts = categoryWiseSections.map((s) => s.products.length);
    return Math.max(0, ...baseCounts, ...categoryCounts);
  }, [trendingProducts.length, newArrivals.length, crossPlatformProducts.length, bestDeals.length, budgetPicks.length, recentPriceChanges.length, relatedSearchProducts.length, categoryWiseSections]);

  // Navigation handlers
  const handleProductPress = useCallback((product) => {
    const pid = product?.id || product?.product_id;
    if (!pid) return;

    // Always open ProductDetail so users get full title/specs/price history
    // plus platform-wise comparison in one consistent screen.
    navigation.navigate('ProductDetail', { productId: pid });
  }, [navigation]);

  const handleCategoryPress = useCallback((category) => {
    const targetSectionId = category?.homeSectionId;
    const sectionY = targetSectionId ? sectionOffsetsRef.current[targetSectionId] : undefined;

    if (typeof sectionY === 'number' && scrollRef.current) {
      scrollRef.current.scrollTo({ y: Math.max(0, sectionY - 12), animated: true });
      return;
    }

    navigation.navigate('SearchTab', {
      screen: 'SearchMain',
      params: { initialQuery: category.query },
    });
  }, [navigation]);

  const handleSearchTap = useCallback(() => {
    navigation.navigate('SearchTab', { screen: 'SearchMain' });
  }, [navigation]);

  // ✅ Banner press should navigate to product detail, not search
  const handleBannerPress = useCallback((product) => {
    const pid = product?.product_id || product?.id;
    if (!pid) {
      // If no product_id, just go to search
      navigation.navigate('SearchTab', { screen: 'SearchMain' });
      return;
    }
    // Navigate to product detail with the banner product
    navigation.navigate('ProductDetail', { productId: pid });
  }, [navigation]);

  const isLoading = trendingStatus === 'loading';

  const registerSectionOffset = useCallback((sectionId, y) => {
    sectionOffsetsRef.current[sectionId] = y;
  }, []);

  const handleScroll = useCallback((event) => {
    if (isLoadingMore || visibleItemsPerSection >= maxItemsAvailable) return;

    const { layoutMeasurement, contentOffset, contentSize } = event.nativeEvent;
    const nearBottom = layoutMeasurement.height + contentOffset.y >= contentSize.height - 240;

    if (!nearBottom) return;

    setIsLoadingMore(true);
    setVisibleItemsPerSection((prev) => Math.min(prev + 4, maxItemsAvailable));
    setTimeout(() => setIsLoadingMore(false), 220);
  }, [isLoadingMore, maxItemsAvailable, visibleItemsPerSection]);

  return (
    <SafeAreaView style={[styles.container, { backgroundColor: themePalette.background || styles.container.backgroundColor }]} edges={['top']}>
      <StatusBar barStyle="dark-content" backgroundColor={themePalette.surface || COLORS.white} />

      {/* Header */}
      <View style={[styles.header, { backgroundColor: themePalette.surface || COLORS.white, borderBottomColor: themePalette.border || COLORS.gray100 }]}>
        <View style={styles.headerLeft}>
          <Text style={[styles.logo, { backgroundColor: themePalette.primary || COLORS.primary }]}>DH</Text>
          <Text style={[styles.appName, { color: themePalette.text || COLORS.textPrimary }]}>{APP.NAME}</Text>
        </View>
        <View style={styles.headerRight}>
          <TouchableOpacity style={styles.iconBtn}>
            <Ionicons name="notifications-outline" size={24} color={themePalette.text || COLORS.textPrimary} />
          </TouchableOpacity>
        </View>
      </View>

      {/* Search Bar (Tap to navigate) */}
      <TouchableOpacity style={[styles.searchBar, { backgroundColor: themePalette.surface || COLORS.white, borderColor: themePalette.border || COLORS.gray200 }]} onPress={handleSearchTap} activeOpacity={0.8}>
        <Ionicons name="search" size={20} color={COLORS.gray400} />
        <Text style={styles.searchPlaceholder}>Search products across platforms...</Text>
      </TouchableOpacity>

      {/* Scrollable Content */}
      <ScrollView
        ref={scrollRef}
        showsVerticalScrollIndicator={false}
        onScroll={handleScroll}
        scrollEventThrottle={16}
        refreshControl={
          <RefreshControl
            refreshing={refreshing}
            onRefresh={onRefresh}
            colors={[themePalette.primary || COLORS.primary]}
            tintColor={themePalette.primary || COLORS.primary}
          />
        }
      >
        {/* Banner Carousel */}
        <BannerCarousel onBannerPress={handleBannerPress} />

        {/* Quick Categories */}
        <QuickCategories onCategoryPress={handleCategoryPress} categories={topCategories} />

        {/* Personalized by last user search */}
        {relatedSearchProducts.length > 0 && (
          <View onLayout={(e) => registerSectionOffset('related-search', e.nativeEvent.layout.y)}>
            <ProductSection
              title={`Based on "${lastSearchQuery}"`}
              emoji="🎯"
              subtitle="Products related to your most recent search"
              accentColor="#0891B2"
              products={relatedSearchProducts}
              maxItems={visibleItemsPerSection}
              onProductPress={handleProductPress}
              isLoading={false}
            />
          </View>
        )}

        {/* New Arrivals */}
        <View onLayout={(e) => registerSectionOffset('new-arrivals', e.nativeEvent.layout.y)}>
          <ProductSection
            title="New Arrivals"
            emoji="🆕"
            subtitle="Freshly added products from recent crawls"
            accentColor="#0EA5E9"
            products={newArrivals}
            maxItems={visibleItemsPerSection}
            onProductPress={handleProductPress}
            isLoading={isLoading || homeDataLoading}
          />
        </View>

        {/* Trending Now */}
        <View onLayout={(e) => registerSectionOffset('trending-now', e.nativeEvent.layout.y)}>
          <ProductSection
            title="Trending Now"
            emoji="🔥"
            subtitle="Most viewed and searched products right now"
            accentColor="#F97316"
            products={trendingProducts}
            maxItems={visibleItemsPerSection}
            onProductPress={handleProductPress}
            isLoading={isLoading}
          />
        </View>

        {/* Cross-Platform Matched */}
        <View onLayout={(e) => registerSectionOffset('cross-platform-matched', e.nativeEvent.layout.y)}>
          <ProductSection
            title="Cross-Platform Matched"
            emoji="🔗"
            subtitle="Tap any product for full details and platform-wise comparison"
            accentColor="#2563EB"
            products={crossPlatformProducts}
            maxItems={visibleItemsPerSection}
            onProductPress={handleProductPress}
            isLoading={isLoading || homeDataLoading}
          />
        </View>

        {/* Recently Price Changed */}
        <View onLayout={(e) => registerSectionOffset('recent-price-changes', e.nativeEvent.layout.y)}>
          <ProductSection
            title="Recently Price Changed"
            emoji="📉"
            subtitle="Sorted by latest price-change and update timestamps"
            accentColor="#7C3AED"
            products={recentPriceChanges}
            maxItems={visibleItemsPerSection}
            onProductPress={handleProductPress}
            isLoading={isLoading || homeDataLoading}
          />
        </View>

        {/* Best Deals */}
        <ProductSection
          title="Best Deals"
          emoji="💥"
          subtitle="Top discounts across platforms"
          accentColor="#DC2626"
          products={bestDeals}
          maxItems={visibleItemsPerSection}
          onProductPress={handleProductPress}
          isLoading={isLoading || homeDataLoading}
        />

        {/* Budget Picks */}
        <ProductSection
          title="Under ₹5,000"
          emoji="💡"
          subtitle="Budget-friendly picks"
          accentColor="#0EA5E9"
          products={budgetPicks}
          maxItems={visibleItemsPerSection}
          onProductPress={handleProductPress}
          isLoading={isLoading}
        />

        {/* Category-wise Sections */}
        {categoryWiseSections.map((section) => (
          <View
            key={section.id}
            onLayout={(e) => registerSectionOffset(section.id, e.nativeEvent.layout.y)}
          >
            <ProductSection
              title={section.title}
              subtitle={section.subtitle}
              emoji={section.emoji}
              accentColor={section.accentColor}
              products={section.products}
              maxItems={visibleItemsPerSection}
              onProductPress={handleProductPress}
              isLoading={isLoading || homeDataLoading}
            />
          </View>
        ))}

        {visibleItemsPerSection < maxItemsAvailable && (
          <View style={styles.loadMoreWrap}>
            <Text style={styles.loadMoreText}>{isLoadingMore ? 'Loading more...' : 'Scroll for more products'}</Text>
          </View>
        )}

        {/* Footer */}
        <View style={[styles.footer, { backgroundColor: themePalette.surfaceMuted || '#EEF0F6' }]}>
          <Text style={[styles.footerText, { color: themePalette.textSecondary || COLORS.textSecondary }]}>Compare prices across 6 platforms</Text>
          <Text style={styles.footerPlatforms}>Amazon • Flipkart • Meesho • Myntra • Nykaa • Croma</Text>
        </View>
      </ScrollView>
    </SafeAreaView>
  );
};

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#F7F8FB' },
  header: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingHorizontal: 16,
    paddingVertical: 8,
    backgroundColor: COLORS.white,
    borderBottomWidth: 1,
    borderBottomColor: COLORS.gray100,
  },
  headerLeft: { flexDirection: 'row', alignItems: 'center' },
  logo: {
    fontSize: 14,
    fontWeight: '900',
    color: COLORS.white,
    marginRight: 8,
    backgroundColor: COLORS.primary,
    width: 34,
    height: 34,
    borderRadius: 17,
    textAlign: 'center',
    textAlignVertical: 'center',
    overflow: 'hidden',
    lineHeight: 34,
  },
  appName: { fontSize: 20, fontWeight: '800', color: COLORS.textPrimary },
  headerRight: { flexDirection: 'row' },
  iconBtn: { padding: 8 },
  searchBar: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: COLORS.white,
    marginHorizontal: 16,
    marginTop: 12,
    marginBottom: 12,
    paddingHorizontal: 16,
    paddingVertical: 12,
    borderRadius: 12,
    borderWidth: 1,
    borderColor: COLORS.gray200,
  },
  searchPlaceholder: { marginLeft: 10, fontSize: 15, color: COLORS.gray400, flex: 1 },
  loadMoreWrap: { paddingTop: 2, paddingBottom: 12, alignItems: 'center' },
  loadMoreText: { fontSize: 12, fontWeight: '600', color: COLORS.gray500 },
  footer: { alignItems: 'center', paddingVertical: 30, paddingHorizontal: 20, backgroundColor: '#EEF0F6', marginTop: 10 },
  footerText: { fontSize: 14, fontWeight: '600', color: COLORS.textSecondary, marginBottom: 6 },
  footerPlatforms: { fontSize: 12, color: COLORS.gray400, textAlign: 'center' },
});

export default HomeScreenV2;