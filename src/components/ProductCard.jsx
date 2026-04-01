// ============================================
// DEALHUNT APP - PRODUCT CARD COMPONENT
// Part 3: Added Watchlist Functionality
// ============================================

import React, { memo, useRef, useCallback } from 'react';
import { View, Text, StyleSheet, TouchableOpacity, Animated } from 'react-native';
import { Image } from 'expo-image';
import { Ionicons } from '@expo/vector-icons';
import { COLORS } from '../utils/constants';
import {
  formatPrice, parsePrice, calculateDiscount,
  getPlatformName, getPlatformColor, getDisplayListingForPrice,
} from '../utils/formatters';
import { useProductWatchlist } from '../hooks/useWatchlist';

// --------------------------------------------
// IMAGE URL UPGRADER
// --------------------------------------------

const upgradeImageUrl = (rawUrl) => {
  if (!rawUrl || typeof rawUrl !== 'string') return rawUrl;

  let url = rawUrl;
  // Amazon thumbnails often include a low-res token like ._SX38_SY50_.
  url = url.replace(/\._[^.]+_\./g, '._SL500_.');
  // Some CDNs expose small 128x128 paths.
  url = url.replace(/\/128\/128\//g, '/832/832/');
  // Raise quality query where available.
  url = url.replace(/([?&])q=\d+/g, '$1q=100');

  return url;
};

// --------------------------------------------
// WISHLIST BUTTON COMPONENT
// --------------------------------------------

const WishlistButton = memo(({ productId, product, style }) => {
  const { isInWatchlist, isProcessing, toggle } = useProductWatchlist(productId, product);
  
  // Animation
  const scaleAnim = useRef(new Animated.Value(1)).current;
  
  const handlePress = useCallback(async () => {
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
      style={[styles.wishlistButton, style]}
      onPress={handlePress}
      hitSlop={{ top: 10, bottom: 10, left: 10, right: 10 }}
      disabled={isProcessing}
    >
      <Animated.View style={{ transform: [{ scale: scaleAnim }] }}>
        <Ionicons
          name={isInWatchlist ? 'heart' : 'heart-outline'}
          size={20}
          color={isInWatchlist ? COLORS.error : COLORS.gray400}
        />
      </Animated.View>
    </TouchableOpacity>
  );
});

// --------------------------------------------
// PRODUCT CARD COMPONENT
// --------------------------------------------

const ProductCard = ({ product, onPress, onWishlistPress }) => {
  if (!product) return null;

  const primaryListing = getDisplayListingForPrice(product) || product?.listings?.[0];
  
  // ✅ FIX: Use both id and product_id
  const id = product?.id || product?.product_id;
  const title = primaryListing?.title || product?.ai_generated_essence || product?.title || 'Product';
  const imageUrl = upgradeImageUrl(primaryListing?.image_url || product?.image_url);
  const currentPrice = parsePrice(primaryListing?.current_price || product?.best_price);
  const originalPrice = parsePrice(primaryListing?.original_price);
  const platform = product?.best_platform || primaryListing?.platform;
  const platformCount = product?.total_platforms || product?.listings?.length || 1;
  const inStock = primaryListing?.in_stock ?? true;
  const discount = originalPrice > currentPrice
    ? (primaryListing?.discount_percentage || calculateDiscount(originalPrice, currentPrice))
    : 0;
  const showDiscount = discount >= 5;

  // Build full product object for watchlist
  const fullProduct = {
    ...product,
    id,
    product_id: id,
  };

  return (
    <TouchableOpacity
      style={styles.card}
      onPress={() => onPress?.(fullProduct)}
      activeOpacity={0.7}
    >
      <View style={styles.imageContainer}>
        {imageUrl ? (
          <Image
            source={{ uri: imageUrl }}
            style={styles.image}
            contentFit="cover"
            transition={120}
          />
        ) : (
          <View style={styles.imagePlaceholder}>
            <Ionicons name="image-outline" size={32} color={COLORS.gray300} />
          </View>
        )}
        
        {showDiscount && (
          <View style={styles.discountBadge}>
            <Text style={styles.discountText}>{Math.round(discount)}% OFF</Text>
          </View>
        )}

        {!inStock && (
          <View style={styles.outOfStockOverlay}>
            <Text style={styles.outOfStockText}>Out of Stock</Text>
          </View>
        )}
      </View>

      <View style={styles.content}>
        <Text style={styles.title} numberOfLines={2}>{title}</Text>

        <View style={styles.priceContainer}>
          <Text style={styles.currentPrice}>{formatPrice(currentPrice)}</Text>
          {originalPrice > currentPrice && (
            <Text style={styles.originalPrice}>{formatPrice(originalPrice)}</Text>
          )}
        </View>

        <View style={styles.footer}>
          <View style={styles.platformContainer}>
            <View style={[styles.platformBadge, { backgroundColor: getPlatformColor(platform) + '20' }]}>
              <Text style={[styles.platformText, { color: getPlatformColor(platform) }]}>
                {getPlatformName(platform)}
              </Text>
            </View>
            {platformCount > 1 && (
              <View style={styles.platformCount}>
                <Ionicons name="flash" size={12} color={COLORS.primary} />
                <Text style={styles.platformCountText}>{platformCount}</Text>
              </View>
            )}
          </View>
          
          {/* ✅ UPDATED: Functional Wishlist Button */}
          <WishlistButton 
            productId={id} 
            product={fullProduct}
          />
        </View>
      </View>
    </TouchableOpacity>
  );
};

// --------------------------------------------
// STYLES
// --------------------------------------------

const styles = StyleSheet.create({
  card: {
    backgroundColor: COLORS.white,
    borderRadius: 12,
    overflow: 'hidden',
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.1,
    shadowRadius: 8,
    elevation: 4,
  },
  imageContainer: {
    position: 'relative',
    width: '100%',
    aspectRatio: 1,
    backgroundColor: COLORS.gray100,
  },
  image: {
    width: '100%',
    height: '100%',
  },
  imagePlaceholder: {
    width: '100%',
    height: '100%',
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: COLORS.gray50,
  },
  discountBadge: {
    position: 'absolute',
    top: 8,
    left: 8,
    backgroundColor: COLORS.error,
    paddingHorizontal: 8,
    paddingVertical: 4,
    borderRadius: 6,
  },
  discountText: {
    color: COLORS.white,
    fontSize: 11,
    fontWeight: '700',
  },
  outOfStockOverlay: {
    position: 'absolute',
    top: 0,
    left: 0,
    right: 0,
    bottom: 0,
    backgroundColor: 'rgba(0,0,0,0.5)',
    alignItems: 'center',
    justifyContent: 'center',
  },
  outOfStockText: {
    color: COLORS.white,
    fontSize: 14,
    fontWeight: '600',
  },
  content: {
    padding: 12,
  },
  title: {
    fontSize: 14,
    fontWeight: '500',
    color: COLORS.textPrimary,
    lineHeight: 20,
    marginBottom: 8,
    minHeight: 40,
  },
  priceContainer: {
    flexDirection: 'row',
    alignItems: 'center',
    marginBottom: 10,
    flexWrap: 'wrap',
  },
  currentPrice: {
    fontSize: 16,
    fontWeight: '700',
    color: COLORS.textPrimary,
    marginRight: 8,
  },
  originalPrice: {
    fontSize: 13,
    color: COLORS.gray500,
    textDecorationLine: 'line-through',
  },
  footer: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  platformContainer: {
    flexDirection: 'row',
    alignItems: 'center',
    flex: 1,
  },
  platformBadge: {
    paddingHorizontal: 8,
    paddingVertical: 4,
    borderRadius: 6,
  },
  platformText: {
    fontSize: 11,
    fontWeight: '600',
  },
  platformCount: {
    flexDirection: 'row',
    alignItems: 'center',
    marginLeft: 8,
  },
  platformCountText: {
    fontSize: 12,
    fontWeight: '600',
    color: COLORS.primary,
    marginLeft: 2,
  },
  wishlistButton: {
    padding: 4,
  },
});

export default memo(ProductCard);