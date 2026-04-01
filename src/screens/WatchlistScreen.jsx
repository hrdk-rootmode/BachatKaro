// ============================================
// DEALHUNT APP - WATCHLIST SCREEN
// Part 3: Watchlist & Price Alerts
// ============================================

import React, { useCallback, useEffect, useState, useMemo } from 'react';
import {
  View,
  Text,
  StyleSheet,
  FlatList,
  RefreshControl,
  TouchableOpacity,
  ActivityIndicator,
  Animated,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useNavigation, useFocusEffect } from '@react-navigation/native';
import { Ionicons } from '@expo/vector-icons';
import { useSelector } from 'react-redux';

import { useWatchlist } from '../hooks/useWatchlist';
import WatchlistCard from '../components/WatchlistCard';
import { COLORS } from '../utils/constants';
import { selectIsAuthenticated } from '../store/authSlice';

// --------------------------------------------
// SORT OPTIONS
// --------------------------------------------

const SORT_OPTIONS = [
  { id: 'recent', label: 'Recently Added', icon: 'time-outline' },
  { id: 'price_low', label: 'Price: Low to High', icon: 'arrow-up-outline' },
  { id: 'price_high', label: 'Price: High to Low', icon: 'arrow-down-outline' },
  { id: 'price_drop', label: 'Biggest Price Drop', icon: 'trending-down-outline' },
  { id: 'name', label: 'Name (A-Z)', icon: 'text-outline' },
];

// --------------------------------------------
// SKELETON LOADER
// --------------------------------------------

const SkeletonCard = () => {
  const animatedValue = React.useRef(new Animated.Value(0)).current;
  
  React.useEffect(() => {
    const animation = Animated.loop(
      Animated.sequence([
        Animated.timing(animatedValue, {
          toValue: 1,
          duration: 1000,
          useNativeDriver: true,
        }),
        Animated.timing(animatedValue, {
          toValue: 0,
          duration: 1000,
          useNativeDriver: true,
        }),
      ])
    );
    animation.start();
    return () => animation.stop();
  }, [animatedValue]);
  
  const opacity = animatedValue.interpolate({
    inputRange: [0, 1],
    outputRange: [0.3, 0.7],
  });
  
  return (
    <Animated.View style={[styles.skeletonCard, { opacity }]}>
      <View style={styles.skeletonImage} />
      <View style={styles.skeletonContent}>
        <View style={styles.skeletonTitle} />
        <View style={styles.skeletonPrice} />
        <View style={styles.skeletonBadge} />
      </View>
    </Animated.View>
  );
};

const SkeletonGrid = () => (
  <View style={styles.skeletonGrid}>
    {[1, 2, 3, 4, 5, 6].map((i) => (
      <SkeletonCard key={`skeleton-${i}`} />
    ))}
  </View>
);

// --------------------------------------------
// EMPTY STATE
// --------------------------------------------

const EmptyState = ({ onBrowse }) => (
  <View style={styles.emptyContainer}>
    <View style={styles.emptyIconContainer}>
      <Ionicons name="heart-outline" size={64} color={COLORS.gray300} />
    </View>
    <Text style={styles.emptyTitle}>No Products in Watchlist</Text>
    <Text style={styles.emptyDescription}>
      Products you save will appear here.{'\n'}
      Get alerts when prices drop!
    </Text>
    <TouchableOpacity style={styles.emptyButton} onPress={onBrowse}>
      <Ionicons name="search-outline" size={18} color={COLORS.white} />
      <Text style={styles.emptyButtonText}>Browse Products</Text>
    </TouchableOpacity>
  </View>
);

// --------------------------------------------
// LOGIN PROMPT
// --------------------------------------------

const LoginPrompt = ({ onLogin }) => (
  <View style={styles.emptyContainer}>
    <View style={styles.emptyIconContainer}>
      <Ionicons name="log-in-outline" size={64} color={COLORS.gray300} />
    </View>
    <Text style={styles.emptyTitle}>Login Required</Text>
    <Text style={styles.emptyDescription}>
      Please login to view and manage{'\n'}
      your watchlist.
    </Text>
    <TouchableOpacity style={styles.emptyButton} onPress={onLogin}>
      <Ionicons name="log-in-outline" size={18} color={COLORS.white} />
      <Text style={styles.emptyButtonText}>Login Now</Text>
    </TouchableOpacity>
  </View>
);

// --------------------------------------------
// SORT MODAL
// --------------------------------------------

const SortModal = ({ visible, currentSort, onSelect, onClose }) => {
  if (!visible) return null;
  
  return (
    <TouchableOpacity 
      style={styles.modalOverlay} 
      activeOpacity={1} 
      onPress={onClose}
    >
      <View style={styles.sortModal}>
        <View style={styles.sortModalHeader}>
          <Text style={styles.sortModalTitle}>Sort By</Text>
          <TouchableOpacity onPress={onClose}>
            <Ionicons name="close" size={24} color={COLORS.textPrimary} />
          </TouchableOpacity>
        </View>
        {SORT_OPTIONS.map((option) => (
          <TouchableOpacity
            key={option.id}
            style={[
              styles.sortOption,
              currentSort === option.id && styles.sortOptionActive,
            ]}
            onPress={() => {
              onSelect(option.id);
              onClose();
            }}
          >
            <Ionicons
              name={option.icon}
              size={20}
              color={currentSort === option.id ? COLORS.primary : COLORS.textSecondary}
            />
            <Text
              style={[
                styles.sortOptionText,
                currentSort === option.id && styles.sortOptionTextActive,
              ]}
            >
              {option.label}
            </Text>
            {currentSort === option.id && (
              <Ionicons name="checkmark" size={20} color={COLORS.primary} />
            )}
          </TouchableOpacity>
        ))}
      </View>
    </TouchableOpacity>
  );
};

// --------------------------------------------
// WATCHLIST SCREEN
// --------------------------------------------

const WatchlistScreen = () => {
  const navigation = useNavigation();
  const isAuthenticated = useSelector(selectIsAuthenticated);
  
  // Watchlist hook
  const {
    items,
    totalCount,
    limit,
    isLoading,
    isRefreshing,
    error,
    isEmpty,
    fetch,
    refresh,
  } = useWatchlist();
  
  // Local state
  const [sortBy, setSortBy] = useState('recent');
  const [showSortModal, setShowSortModal] = useState(false);
  
  // Fetch watchlist on mount and when focused
  useFocusEffect(
    useCallback(() => {
      if (isAuthenticated) {
        fetch();
      }
    }, [isAuthenticated, fetch])
  );
  
  // Sort items
  const sortedItems = useMemo(() => {
    if (!items || items.length === 0) return [];
    
    const itemsCopy = [...items];

    const resolvePrice = (entry) => {
      const candidate =
        entry?.product?.best_price ??
        entry?.product?.current_price ??
        entry?.current_price ??
        entry?.product?.price ??
        entry?.price ??
        0;

      const numeric = Number(candidate);
      return Number.isFinite(numeric) ? numeric : 0;
    };

    const resolveTitle = (entry) =>
      String(
        entry?.product?.title ||
          entry?.product?.product_title ||
          entry?.product_title ||
          entry?.title ||
          entry?.product?.name ||
          ''
      );

    const resolveDrop = (entry) => {
      const candidate =
        entry?.product?.price_change_7d ??
        entry?.price_change_7d ??
        entry?.product?.price_change ??
        entry?.price_change ??
        0;
      const numeric = Number(candidate);
      return Number.isFinite(numeric) ? numeric : 0;
    };
    
    switch (sortBy) {
      case 'recent':
        return itemsCopy.sort((a, b) => 
          new Date(b.added_at || 0) - new Date(a.added_at || 0)
        );
      
      case 'price_low':
        return itemsCopy.sort((a, b) => {
          const priceA = resolvePrice(a);
          const priceB = resolvePrice(b);
          return priceA - priceB;
        });
      
      case 'price_high':
        return itemsCopy.sort((a, b) => {
          const priceA = resolvePrice(a);
          const priceB = resolvePrice(b);
          return priceB - priceA;
        });
      
      case 'price_drop':
        return itemsCopy.sort((a, b) => {
          const dropA = resolveDrop(a);
          const dropB = resolveDrop(b);
          // More negative = bigger drop
          return dropA - dropB;
        });
      
      case 'name':
        return itemsCopy.sort((a, b) => {
          const nameA = resolveTitle(a);
          const nameB = resolveTitle(b);
          return nameA.localeCompare(nameB);
        });
      
      default:
        return itemsCopy;
    }
  }, [items, sortBy]);
  
  // Handle navigation
  const handleBrowse = useCallback(() => {
    navigation.navigate('HomeTab');
  }, [navigation]);
  
  const handleLogin = useCallback(() => {
    navigation.navigate('Auth');
  }, [navigation]);
  
  // Handle item removal callback
  const handleItemRemoved = useCallback((productId) => {
    // Optional: Show toast or feedback
    console.log('Removed from watchlist:', productId);
  }, []);
  
  // Render item
  const renderItem = useCallback(({ item, index }) => (
    <WatchlistCard
      item={item}
      index={index}
      onRemove={handleItemRemoved}
    />
  ), [handleItemRemoved]);
  
  // Key extractor
  const keyExtractor = useCallback(
    (item, index) =>
      String(item.id || item.product_id || item?.product?.product_id || `watchlist-${index}`),
    []
  );
  
  // Get current sort label
  const currentSortLabel = SORT_OPTIONS.find(o => o.id === sortBy)?.label || 'Sort';
  
  // Not authenticated
  if (!isAuthenticated) {
    return (
      <SafeAreaView style={styles.container} edges={['top']}>
        <View style={styles.header}>
          <Text style={styles.headerTitle}>Watchlist</Text>
        </View>
        <LoginPrompt onLogin={handleLogin} />
      </SafeAreaView>
    );
  }
  
  // Loading state (initial load)
  if (isLoading && items.length === 0) {
    return (
      <SafeAreaView style={styles.container} edges={['top']}>
        <View style={styles.header}>
          <View style={styles.headerLeft}>
            <Text style={styles.headerTitle}>Watchlist</Text>
            <View style={styles.countBadge}>
              <Text style={styles.countText}>{totalCount}/{limit}</Text>
            </View>
          </View>
        </View>
        <SkeletonGrid />
      </SafeAreaView>
    );
  }
  
  // Error state
  if (error && items.length === 0) {
    return (
      <SafeAreaView style={styles.container} edges={['top']}>
        <View style={styles.header}>
          <View style={styles.headerLeft}>
            <Text style={styles.headerTitle}>Watchlist</Text>
            <View style={styles.countBadge}>
              <Text style={styles.countText}>{totalCount}/{limit}</Text>
            </View>
          </View>
        </View>
        <View style={styles.errorContainer}>
          <Ionicons name="alert-circle-outline" size={48} color={COLORS.error} />
          <Text style={styles.errorText}>
            {typeof error === 'string' ? error : 'Failed to load watchlist'}
          </Text>
          <TouchableOpacity style={styles.retryButton} onPress={() => fetch(true)}>
            <Text style={styles.retryButtonText}>Try Again</Text>
          </TouchableOpacity>
        </View>
      </SafeAreaView>
    );
  }
  
  return (
    <SafeAreaView style={styles.container} edges={['top']}>
      {/* Header */}
      <View style={styles.header}>
        <View style={styles.headerLeft}>
          <Text style={styles.headerTitle}>Watchlist</Text>
          <View style={styles.countBadge}>
            <Text style={styles.countText}>{totalCount}/{limit}</Text>
          </View>
        </View>
        
        {items.length > 0 && (
          <TouchableOpacity
            style={styles.sortButton}
            onPress={() => setShowSortModal(true)}
          >
            <Ionicons name="swap-vertical-outline" size={18} color={COLORS.primary} />
            <Text style={styles.sortButtonText}>{currentSortLabel}</Text>
          </TouchableOpacity>
        )}
      </View>
      
      {/* Limit Warning */}
      {totalCount >= limit && (
        <View style={styles.limitWarning}>
          <Ionicons name="warning-outline" size={16} color={COLORS.warning} />
          <Text style={styles.limitWarningText}>
            Watchlist full! Upgrade to add more products.
          </Text>
          <TouchableOpacity 
            style={styles.upgradeLink}
            onPress={() => {
              // TODO: Navigate to subscription (Part 5)
              console.log('Navigate to upgrade');
            }}
          >
            <Text style={styles.upgradeLinkText}>Upgrade</Text>
          </TouchableOpacity>
        </View>
      )}
      
      {/* Content */}
      {isEmpty ? (
        <EmptyState onBrowse={handleBrowse} />
      ) : (
        <FlatList
          data={sortedItems}
          renderItem={renderItem}
          keyExtractor={keyExtractor}
          numColumns={2}
          contentContainerStyle={styles.listContent}
          columnWrapperStyle={styles.columnWrapper}
          showsVerticalScrollIndicator={false}
          refreshControl={
            <RefreshControl
              refreshing={isRefreshing}
              onRefresh={refresh}
              colors={[COLORS.primary]}
              tintColor={COLORS.primary}
            />
          }
          ListFooterComponent={
            <View style={styles.listFooter}>
              <Text style={styles.footerText}>
                {totalCount} product{totalCount !== 1 ? 's' : ''} in watchlist
              </Text>
            </View>
          }
        />
      )}
      
      {/* Sort Modal */}
      <SortModal
        visible={showSortModal}
        currentSort={sortBy}
        onSelect={setSortBy}
        onClose={() => setShowSortModal(false)}
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
    backgroundColor: '#F3F6FA',
  },
  
  // Header
  header: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingHorizontal: 16,
    paddingVertical: 12,
    backgroundColor: COLORS.white,
    borderBottomWidth: 1,
    borderBottomColor: '#E7ECF2',
  },
  
  headerLeft: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
  },
  
  headerTitle: {
    fontSize: 22,
    fontWeight: '700',
    color: COLORS.textPrimary,
  },
  
  countBadge: {
    backgroundColor: COLORS.primary + '15',
    paddingHorizontal: 10,
    paddingVertical: 4,
    borderRadius: 12,
  },
  
  countText: {
    fontSize: 12,
    fontWeight: '600',
    color: COLORS.primary,
  },
  
  sortButton: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    paddingHorizontal: 12,
    paddingVertical: 8,
    backgroundColor: COLORS.primary + '10',
    borderRadius: 8,
  },
  
  sortButtonText: {
    fontSize: 13,
    fontWeight: '500',
    color: COLORS.primary,
  },
  
  // Limit Warning
  limitWarning: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: COLORS.warning + '15',
    paddingHorizontal: 16,
    paddingVertical: 10,
    gap: 8,
  },
  
  limitWarningText: {
    flex: 1,
    fontSize: 12,
    color: COLORS.warning,
    fontWeight: '500',
  },
  
  upgradeLink: {
    paddingHorizontal: 12,
    paddingVertical: 6,
    backgroundColor: COLORS.warning,
    borderRadius: 6,
  },
  
  upgradeLinkText: {
    fontSize: 12,
    fontWeight: '600',
    color: COLORS.white,
  },
  
  // List
  listContent: {
    padding: 10,
  },
  
  columnWrapper: {
    justifyContent: 'space-between',
  },
  
  listFooter: {
    alignItems: 'center',
    paddingVertical: 20,
  },
  
  footerText: {
    fontSize: 12,
    color: COLORS.textSecondary,
  },
  
  // Empty State
  emptyContainer: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    paddingHorizontal: 40,
  },
  
  emptyIconContainer: {
    width: 120,
    height: 120,
    borderRadius: 60,
    backgroundColor: COLORS.gray100,
    justifyContent: 'center',
    alignItems: 'center',
    marginBottom: 24,
  },
  
  emptyTitle: {
    fontSize: 20,
    fontWeight: '700',
    color: COLORS.textPrimary,
    marginBottom: 12,
    textAlign: 'center',
  },
  
  emptyDescription: {
    fontSize: 14,
    color: COLORS.textSecondary,
    textAlign: 'center',
    lineHeight: 22,
    marginBottom: 24,
  },
  
  emptyButton: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    backgroundColor: COLORS.primary,
    paddingHorizontal: 24,
    paddingVertical: 14,
    borderRadius: 12,
  },
  
  emptyButtonText: {
    fontSize: 15,
    fontWeight: '600',
    color: COLORS.white,
  },
  
  // Error State
  errorContainer: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    paddingHorizontal: 40,
  },
  
  errorText: {
    fontSize: 14,
    color: COLORS.textSecondary,
    textAlign: 'center',
    marginTop: 16,
    marginBottom: 20,
  },
  
  retryButton: {
    backgroundColor: COLORS.primary,
    paddingHorizontal: 24,
    paddingVertical: 12,
    borderRadius: 10,
  },
  
  retryButtonText: {
    fontSize: 14,
    fontWeight: '600',
    color: COLORS.white,
  },
  
  // Skeleton
  skeletonGrid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    padding: 10,
  },
  
  skeletonCard: {
    width: '48%',
    margin: '1%',
    backgroundColor: COLORS.white,
    borderRadius: 12,
    overflow: 'hidden',
  },
  
  skeletonImage: {
    width: '100%',
    height: 120,
    backgroundColor: COLORS.gray200,
  },
  
  skeletonContent: {
    padding: 12,
  },
  
  skeletonTitle: {
    height: 16,
    backgroundColor: COLORS.gray200,
    borderRadius: 4,
    marginBottom: 8,
  },
  
  skeletonPrice: {
    height: 20,
    width: '60%',
    backgroundColor: COLORS.gray200,
    borderRadius: 4,
    marginBottom: 8,
  },
  
  skeletonBadge: {
    height: 24,
    width: '40%',
    backgroundColor: COLORS.gray200,
    borderRadius: 6,
  },
  
  // Sort Modal
  modalOverlay: {
    position: 'absolute',
    top: 0,
    left: 0,
    right: 0,
    bottom: 0,
    backgroundColor: 'rgba(0, 0, 0, 0.5)',
    justifyContent: 'flex-end',
  },
  
  sortModal: {
    backgroundColor: COLORS.white,
    borderTopLeftRadius: 20,
    borderTopRightRadius: 20,
    paddingBottom: 34,
  },
  
  sortModalHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingHorizontal: 20,
    paddingVertical: 16,
    borderBottomWidth: 1,
    borderBottomColor: COLORS.gray200,
  },
  
  sortModalTitle: {
    fontSize: 18,
    fontWeight: '700',
    color: COLORS.textPrimary,
  },
  
  sortOption: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 20,
    paddingVertical: 14,
    gap: 12,
  },
  
  sortOptionActive: {
    backgroundColor: COLORS.primary + '10',
  },
  
  sortOptionText: {
    flex: 1,
    fontSize: 15,
    color: COLORS.textPrimary,
  },
  
  sortOptionTextActive: {
    color: COLORS.primary,
    fontWeight: '600',
  },
});

export default WatchlistScreen;