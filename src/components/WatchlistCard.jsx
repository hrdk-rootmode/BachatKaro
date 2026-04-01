// ============================================
// DEALHUNT APP - WATCHLIST CARD COMPONENT
// Part 3: Watchlist & Price Alerts
// ============================================

import React, { memo, useCallback, useRef } from 'react';
import {
  View,
  Text,
  Image,
  TouchableOpacity,
  StyleSheet,
  Animated,
  Alert,
  ActivityIndicator,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useNavigation } from '@react-navigation/native';
import { useDispatch, useSelector } from 'react-redux';

import { COLORS, FONTS, PLATFORMS } from '../utils/constants';
import PriceChangeIndicator, { PriceChangeBadge } from './PriceChangeIndicator';
import {
  removeFromWatchlist,
  selectIsRemovingFromWatchlist,
} from '../store/watchlistSlice';

// --------------------------------------------
// PLATFORM BADGE COMPONENT
// --------------------------------------------

const PlatformBadge = memo(({ platform }) => {
  const platformConfig = PLATFORMS?.[platform?.toUpperCase()] || PLATFORMS?.DEFAULT || {
    name: platform || 'Unknown',
    color: '#6B7280',
  };
  
  return (
    <View style={[styles.platformBadge, { backgroundColor: platformConfig.color + '20' }]}>
      <Text style={[styles.platformText, { color: platformConfig.color }]}>
        {platformConfig.name || platform}
      </Text>
    </View>
  );
});

// --------------------------------------------
// WATCHLIST CARD COMPONENT
// --------------------------------------------

/**
 * Card component specifically designed for watchlist items
 * Features: Price change indicator, delete button, platform badge
 * 
 * @param {Object} props
 * @param {Object} props.item - Watchlist item with product data
 * @param {Function} props.onRemove - Optional callback after removal
 * @param {number} props.index - Item index for stagger animation
 */
const WatchlistCard = ({
  item,
  onRemove,
  index = 0,
}) => {
  const navigation = useNavigation();
  const dispatch = useDispatch();
  
  // Extract product data
  const product = item?.product || item;
  const productId = item?.product_id || product?.product_id || product?.id;
  const watchlistItemId = item?.id || null;
  const removeKey = productId || watchlistItemId;
  
  // Check if currently being removed
  const isRemoving = useSelector(selectIsRemovingFromWatchlist(removeKey));
  
  // Animation values
  const scaleAnim = useRef(new Animated.Value(1)).current;
  const opacityAnim = useRef(new Animated.Value(1)).current;
  
  // Extract product details
  const title =
    product?.title ||
    product?.product_title ||
    item?.product_title ||
    product?.name ||
    'Unknown Product';
  const image =
    product?.image_url ||
    item?.image_url ||
    product?.image ||
    product?.listings?.[0]?.image_url;
  const bestPrice =
    product?.best_price ??
    product?.current_price ??
    item?.current_price ??
    product?.price ??
    item?.price ??
    product?.listings?.[0]?.current_price ??
    product?.listings?.[0]?.price;
  const originalPrice =
    product?.original_price ??
    item?.original_price ??
    product?.listings?.[0]?.original_price ??
    null;
  const bestPlatform =
    product?.best_platform ||
    item?.best_platform ||
    product?.platform ||
    item?.platform ||
    product?.listings?.[0]?.platform;
  const priceChange = Number(
    product?.price_change_7d ?? item?.price_change_7d ?? product?.price_change ?? item?.price_change ?? 0
  ) || 0;
  const priceChangePercentage = Number(
    product?.price_change_percentage ?? item?.price_change_percentage ?? 0
  ) || 0;
  const addedAt = item?.added_at;
  
  // Extract price history / previous price info
  const previousPrice = priceChange && priceChange !== 0
    ? Number(bestPrice || 0) - Number(priceChange || 0)
    : null;
  
  // Determine if price went up or down
  const priceWentUp = priceChange > 0;
  const priceWentDown = priceChange < 0;
  
  // Format price
  const formatPrice = (price) => {
    if (price === null || price === undefined || price === '') return '—';
    const numPrice = typeof price === 'string'
      ? parseFloat(price.replace(/[^\d.]/g, ''))
      : Number(price);
    if (!Number.isFinite(numPrice) || numPrice <= 0) return '—';
    return `₹${numPrice.toLocaleString('en-IN')}`;
  };
  
  // Handle card press - navigate to product detail
  const handlePress = useCallback(() => {
    // Press animation
    Animated.sequence([
      Animated.timing(scaleAnim, {
        toValue: 0.97,
        duration: 100,
        useNativeDriver: true,
      }),
      Animated.timing(scaleAnim, {
        toValue: 1,
        duration: 100,
        useNativeDriver: true,
      }),
    ]).start();
    
    if (!productId) {
      Alert.alert('Unavailable', 'Product details are not available for this item yet.');
      return;
    }

    // Navigate to product detail with normalized product identity for immediate render context.
    navigation.navigate('ProductDetail', {
      productId,
      product: {
        ...product,
        id: productId,
        product_id: productId,
        title,
        product_title: title,
        current_price: bestPrice,
        original_price: originalPrice,
      },
    });
  }, [navigation, productId, product, scaleAnim, title, bestPrice, originalPrice]);
  
  // Handle remove button press
  const handleRemove = useCallback(() => {
    Alert.alert(
      'Remove from Watchlist',
      'Are you sure you want to remove this product from your watchlist?',
      [
        {
          text: 'Cancel',
          style: 'cancel',
        },
        {
          text: 'Remove',
          style: 'destructive',
          onPress: async () => {
            // Fade out animation
            Animated.timing(opacityAnim, {
              toValue: 0,
              duration: 200,
              useNativeDriver: true,
            }).start();
            
            // Dispatch remove action
            try {
              await dispatch(
                removeFromWatchlist({
                  productId,
                  watchlistItemId,
                })
              ).unwrap();
              onRemove?.(removeKey);
            } catch (error) {
              // Restore opacity on error
              Animated.timing(opacityAnim, {
                toValue: 1,
                duration: 200,
                useNativeDriver: true,
              }).start();
            }
          },
        },
      ]
    );
  }, [dispatch, productId, watchlistItemId, removeKey, opacityAnim, onRemove]);
  
  // Placeholder image
  const renderImage = () => {
    if (image) {
      return (
        <Image
          source={{ uri: image }}
          style={styles.image}
          resizeMode="contain"
        />
      );
    }
    
    return (
      <View style={styles.imagePlaceholder}>
        <Ionicons
          name="image-outline"
          size={32}
          color={COLORS?.textTertiary || '#9CA3AF'}
        />
      </View>
    );
  };
  
  return (
    <Animated.View
      style={[
        styles.container,
        {
          transform: [{ scale: scaleAnim }],
          opacity: opacityAnim,
        },
      ]}
    >
      <TouchableOpacity
        activeOpacity={0.8}
        onPress={handlePress}
        style={styles.touchable}
        disabled={isRemoving}
      >
        {/* Image */}
        <View style={styles.imageContainer}>
          {renderImage()}
          
          {/* Platform Badge */}
          {bestPlatform && (
            <View style={styles.platformBadgeContainer}>
              <PlatformBadge platform={bestPlatform} />
            </View>
          )}
        </View>
        
        {/* Content */}
        <View style={styles.content}>
          {/* Title */}
          <Text style={styles.title} numberOfLines={2}>
            {title}
          </Text>
          
          {/* Price Row */}
          <View style={styles.priceRow}>
            <View style={styles.priceDisplay}>
              {/* Current Price */}
              <Text style={styles.price}>
                {formatPrice(bestPrice)}
              </Text>
              
              {/* Previous Price and Change info - shown if price has changed */}
              {previousPrice && previousPrice > 0 && (priceChange !== 0) && (
                <View style={styles.priceChangeContainer}>
                  <Text style={styles.priceChangeText}>
                    {priceWentDown ? '↓' : priceWentUp ? '↑' : ''}
                  </Text>
                  <Text style={[
                    styles.priceChangeText,
                    priceWentDown ? styles.priceDropped : styles.priceIncreased
                  ]}>
                    {formatPrice(Math.abs(priceChange))}
                  </Text>
                  <Text style={styles.previousPriceLabel}>
                    (was {formatPrice(previousPrice)})
                  </Text>
                </View>
              )}
              
              {/* Fallback to original price if no recent change tracked */}
              {(!previousPrice || previousPrice <= 0) && Number(originalPrice || 0) > Number(bestPrice || 0) && (
                <Text style={styles.oldPrice}>{formatPrice(originalPrice)}</Text>
              )}
            </View>
          </View>
          
          {/* Added Date */}
          {addedAt && (
            <Text style={styles.addedDate}>
              Added {formatAddedDate(addedAt)}
            </Text>
          )}
        </View>
        
        {/* Remove Button */}
        <TouchableOpacity
          style={styles.removeButton}
          onPress={handleRemove}
          disabled={isRemoving}
          hitSlop={{ top: 10, bottom: 10, left: 10, right: 10 }}
        >
          {isRemoving ? (
            <ActivityIndicator size="small" color={COLORS?.error || '#EF4444'} />
          ) : (
            <Ionicons
              name="trash-outline"
              size={18}
              color={COLORS?.error || '#EF4444'}
            />
          )}
        </TouchableOpacity>
      </TouchableOpacity>
    </Animated.View>
  );
};

// --------------------------------------------
// HELPER FUNCTIONS
// --------------------------------------------

const formatAddedDate = (dateString) => {
  try {
    const date = new Date(dateString);
    const now = new Date();
    const diffMs = now - date;
    const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24));
    
    if (diffDays === 0) return 'today';
    if (diffDays === 1) return 'yesterday';
    if (diffDays < 7) return `${diffDays} days ago`;
    if (diffDays < 30) return `${Math.floor(diffDays / 7)} weeks ago`;
    
    return date.toLocaleDateString('en-IN', {
      day: 'numeric',
      month: 'short',
    });
  } catch {
    return '';
  }
};

// --------------------------------------------
// STYLES
// --------------------------------------------

const styles = StyleSheet.create({
  container: {
    flex: 1,
    margin: 6,
    backgroundColor: COLORS?.surface || '#FFFFFF',
    borderRadius: 12,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.08,
    shadowRadius: 8,
    elevation: 3,
    overflow: 'hidden',
  },
  
  touchable: {
    flex: 1,
  },
  
  imageContainer: {
    width: '100%',
    height: 120,
    backgroundColor: COLORS?.backgroundSecondary || '#F3F4F6',
    position: 'relative',
  },
  
  image: {
    width: '100%',
    height: '100%',
  },
  
  imagePlaceholder: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
  },
  
  platformBadgeContainer: {
    position: 'absolute',
    top: 6,
    left: 6,
  },
  
  platformBadge: {
    paddingHorizontal: 6,
    paddingVertical: 2,
    borderRadius: 4,
  },
  
  platformText: {
    fontSize: 9,
    fontFamily: FONTS?.semiBold || 'System',
    fontWeight: '600',
    textTransform: 'capitalize',
  },
  
  content: {
    padding: 10,
    flex: 1,
  },
  
  title: {
    fontSize: 13,
    fontFamily: FONTS?.medium || 'System',
    fontWeight: '500',
    color: COLORS?.text || '#111827',
    lineHeight: 18,
    marginBottom: 6,
  },
  
  priceRow: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    flexWrap: 'wrap',
    gap: 6,
  },
  
  priceDisplay: {
    flexDirection: 'column',
    gap: 2,
  },
  
  price: {
    fontSize: 15,
    fontFamily: FONTS?.bold || 'System',
    fontWeight: '700',
    color: COLORS?.primary || '#6366F1',
  },
  
  priceChangeContainer: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 3,
  },

  priceChangeText: {
    fontSize: 11,
    fontFamily: FONTS?.semiBold || 'System',
    fontWeight: '600',
  },
  
  priceDropped: {
    color: '#10B981', // Green for price drop (good)
  },
  
  priceIncreased: {
    color: '#EF4444', // Red for price increase (bad)
  },
  
  previousPriceLabel: {
    fontSize: 10,
    fontFamily: FONTS?.regular || 'System',
    color: COLORS?.textTertiary || '#9CA3AF',
  },

  oldPrice: {
    fontSize: 11,
    fontFamily: FONTS?.regular || 'System',
    color: COLORS?.textTertiary || '#9CA3AF',
    textDecorationLine: 'line-through',
  },
  
  priceChange: {
    marginLeft: 4,
  },
  
  addedDate: {
    fontSize: 10,
    fontFamily: FONTS?.regular || 'System',
    color: COLORS?.textTertiary || '#9CA3AF',
    marginTop: 4,
  },
  
  removeButton: {
    position: 'absolute',
    top: 8,
    right: 8,
    width: 32,
    height: 32,
    borderRadius: 16,
    backgroundColor: COLORS?.surface || '#FFFFFF',
    justifyContent: 'center',
    alignItems: 'center',
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.1,
    shadowRadius: 2,
    elevation: 2,
  },
});

// --------------------------------------------
// EXPORTS
// --------------------------------------------

export default memo(WatchlistCard);