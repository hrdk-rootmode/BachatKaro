// ============================================
// DEALHUNT APP - TRENDING PRODUCT CARD
// ============================================

import React, { memo } from 'react';
import {
  View,
  Text,
  StyleSheet,
  TouchableOpacity,
} from 'react-native';
import { Image } from 'expo-image';
import { Ionicons } from '@expo/vector-icons';

import { COLORS } from '../utils/constants';
import { formatPrice, parsePrice } from '../utils/formatters';

// Placeholder blurhash
const PLACEHOLDER_BLURHASH = 'L6PZfSi_.AyE_3t7t7R**0o#DgR4';

/**
 * Smaller horizontal card for trending products carousel
 * Uses trending response structure (title/image at top level)
 * 
 * @param {Object} product - Trending product from backend
 * @param {function} onPress - Tap handler
 */
const TrendingProductCard = ({ product, onPress }) => {
  const id = product?.product_id;
  const title = product?.title || 'Trending Product';
  const imageUrl = product?.image_url;
  const price = parsePrice(product?.best_price);
  const platformCount = product?.platform_count || 1;

  return (
    <TouchableOpacity
      style={styles.card}
      onPress={() => onPress?.(product)}
      activeOpacity={0.7}
    >
      {/* Product Image */}
      <View style={styles.imageContainer}>
        <Image
          source={{ uri: imageUrl }}
          placeholder={PLACEHOLDER_BLURHASH}
          style={styles.image}
          contentFit="cover"
          transition={200}
        />
      </View>

      {/* Product Info */}
      <View style={styles.content}>
        {/* Title */}
        <Text style={styles.title} numberOfLines={2}>
          {title}
        </Text>

        {/* Price + Platform Count */}
        <View style={styles.footer}>
          <Text style={styles.price}>{formatPrice(price)}</Text>
          {platformCount > 1 && (
            <View style={styles.platformCount}>
              <Ionicons name="flash" size={10} color={COLORS.primary} />
              <Text style={styles.platformCountText}>{platformCount}</Text>
            </View>
          )}
        </View>
      </View>

      {/* Trending Badge */}
      <View style={styles.trendingBadge}>
        <Ionicons name="flame" size={10} color={COLORS.white} />
      </View>
    </TouchableOpacity>
  );
};

// --------------------------------------------
// STYLES
// --------------------------------------------

const styles = StyleSheet.create({
  card: {
    width: 140,
    backgroundColor: COLORS.white,
    borderRadius: 12,
    overflow: 'hidden',
    marginRight: 12,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.08,
    shadowRadius: 6,
    elevation: 3,
  },

  imageContainer: {
    width: '100%',
    height: 100,
    backgroundColor: COLORS.gray100,
  },

  image: {
    width: '100%',
    height: '100%',
  },

  content: {
    padding: 10,
  },

  title: {
    fontSize: 12,
    fontWeight: '500',
    color: COLORS.textPrimary,
    lineHeight: 16,
    marginBottom: 6,
    minHeight: 32,
  },

  footer: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },

  price: {
    fontSize: 14,
    fontWeight: '700',
    color: COLORS.primary,
  },

  platformCount: {
    flexDirection: 'row',
    alignItems: 'center',
  },

  platformCountText: {
    fontSize: 10,
    fontWeight: '600',
    color: COLORS.primary,
    marginLeft: 2,
  },

  trendingBadge: {
    position: 'absolute',
    top: 6,
    right: 6,
    width: 20,
    height: 20,
    borderRadius: 10,
    backgroundColor: COLORS.error,
    alignItems: 'center',
    justifyContent: 'center',
  },
});

export default memo(TrendingProductCard);