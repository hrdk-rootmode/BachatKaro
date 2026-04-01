// ============================================
// DEALHUNT APP - PRICE COMPARISON TABLE
// ============================================

import React, { memo, useMemo } from 'react';
import {
  View,
  Text,
  StyleSheet,
  TouchableOpacity,
  Linking,
  Alert,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';

import PlatformBadge from './PlatformBadge';
import { COLORS } from '../utils/constants';
import {
  formatPrice,
  parsePrice,
  formatTimeAgo,
  getPlatformColor,
} from '../utils/formatters';

/**
 * Price comparison table showing all platforms
 * 
 * @param {Array} listings - Product listings from all platforms
 * @param {string} bestPlatform - Platform with best price
 * @param {function} onBuyPress - Optional custom buy handler
 */
const PriceComparisonTable = ({ listings, bestPlatform, onBuyPress }) => {
  // Sort listings by price (in-stock first, then by price)
  const sortedListings = useMemo(() => {
    if (!listings || listings.length === 0) return [];

    return [...listings].sort((a, b) => {
      // Validate items
      if (!a || !b) return 0;
      
      // In-stock items first
      if (a.in_stock && !b.in_stock) return -1;
      if (!a.in_stock && b.in_stock) return 1;

      // Then by price - ✅ CRITICAL: Use current_price (backend field) or fallback to price
      const priceA = a.current_price || a.price || 0;
      const priceB = b.current_price || b.price || 0;
      return priceA - priceB;
    });
  }, [listings]);

  // Handle buy button press
  const handleBuyPress = async (listing) => {
    if (onBuyPress) {
      onBuyPress(listing);
      return;
    }

    const url = listing.url;
    if (!url) {
      Alert.alert('Error', 'Product link not available');
      return;
    }

    try {
      const supported = await Linking.canOpenURL(url);
      if (supported) {
        await Linking.openURL(url);
      } else {
        Alert.alert('Error', 'Cannot open this link');
      }
    } catch (error) {
      console.error('Open URL error:', error);
      Alert.alert('Error', 'Failed to open link');
    }
  };

  if (!sortedListings || sortedListings.length === 0) {
    return (
      <View style={styles.emptyContainer}>
        <Ionicons name="alert-circle-outline" size={40} color={COLORS.gray300} />
        <Text style={styles.emptyText}>No price data available</Text>
      </View>
    );
  }

  return (
    <View style={styles.container}>
      {/* Header */}
      <View style={styles.header}>
        <Text style={styles.headerTitle}>📊 Price Comparison</Text>
        <Text style={styles.headerSubtitle}>
          {sortedListings.length} platform{sortedListings.length > 1 ? 's' : ''} available
        </Text>
      </View>

      {/* Platform Rows */}
      <View style={styles.tableContainer}>
        {sortedListings.map((listing, index) => {
          const isBest = listing.platform === bestPlatform && listing.in_stock;
          // ✅ CRITICAL: Use current_price (backend field) or fallback to price
          const price = listing.current_price || listing.price || 0;
          const originalPrice = listing.original_price || 0;
          const hasDiscount = originalPrice > price && originalPrice > 0;
          const discountPct = listing.discount_percentage || listing.discount_percent || 0;
          const platformColor = getPlatformColor(listing.platform);

          return (
            <View
              key={listing.id || listing.listing_id || `listing-${index}`}
              style={[
                styles.row,
                isBest && styles.bestRow,
                index === sortedListings.length - 1 && styles.lastRow,
              ]}
            >
              {/* Best Badge */}
              {isBest && (
                <View style={styles.bestBadge}>
                  <Text style={styles.bestBadgeText}>BEST</Text>
                </View>
              )}

              {/* Platform Info */}
              <View style={styles.platformColumn}>
                <PlatformBadge
                  platform={listing.platform || 'amazon'}
                  size="medium"
                  showName={true}
                />
              </View>

              {/* Price Info */}
              <View style={styles.priceColumn}>
                {listing.in_stock ? (
                  <>
                    <Text
                      style={[
                        styles.priceText,
                        isBest && styles.bestPriceText,
                      ]}
                    >
                      {formatPrice(price)}
                    </Text>
                    {hasDiscount && (
                      <Text style={styles.originalPriceText}>
                        {formatPrice(originalPrice)}
                      </Text>
                    )}
                    {discountPct > 0 && (
                      <View style={styles.discountBadge}>
                        <Text style={styles.discountText}>
                          {Math.round(discountPct)}% OFF
                        </Text>
                      </View>
                    )}
                  </>
                ) : (
                  <Text style={styles.outOfStockText}>Out of Stock</Text>
                )}
              </View>

              {/* Action Button */}
              <View style={styles.actionColumn}>
                {listing.in_stock ? (
                  <TouchableOpacity
                    style={[
                      styles.buyButton,
                      isBest && { backgroundColor: platformColor },
                    ]}
                    onPress={() => handleBuyPress(listing)}
                    activeOpacity={0.7}
                  >
                    <Text
                      style={[
                        styles.buyButtonText,
                        isBest && styles.bestBuyButtonText,
                      ]}
                    >
                      Buy
                    </Text>
                    <Ionicons
                      name="open-outline"
                      size={14}
                      color={isBest ? COLORS.white : platformColor}
                    />
                  </TouchableOpacity>
                ) : (
                  <View style={styles.unavailableButton}>
                    <Ionicons name="close-circle" size={18} color={COLORS.gray400} />
                  </View>
                )}
              </View>
            </View>
          );
        })}
      </View>

      {/* Footer Note */}
      <View style={styles.footer}>
        <Ionicons name="time-outline" size={14} color={COLORS.gray400} />
        <Text style={styles.footerText}>
          Prices updated {formatTimeAgo(sortedListings[0]?.last_checked)}
        </Text>
      </View>
    </View>
  );
};

// --------------------------------------------
// STYLES
// --------------------------------------------

const styles = StyleSheet.create({
  container: {
    backgroundColor: COLORS.white,
    borderRadius: 16,
    overflow: 'hidden',
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.08,
    shadowRadius: 8,
    elevation: 3,
  },

  header: {
    paddingHorizontal: 16,
    paddingVertical: 14,
    borderBottomWidth: 1,
    borderBottomColor: COLORS.gray100,
  },

  headerTitle: {
    fontSize: 16,
    fontWeight: '700',
    color: COLORS.textPrimary,
  },

  headerSubtitle: {
    fontSize: 12,
    color: COLORS.textSecondary,
    marginTop: 2,
  },

  tableContainer: {
    paddingHorizontal: 12,
  },

  row: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingVertical: 14,
    paddingHorizontal: 8,
    borderBottomWidth: 1,
    borderBottomColor: COLORS.gray100,
    position: 'relative',
  },

  bestRow: {
    backgroundColor: COLORS.successLight,
    borderRadius: 12,
    marginVertical: 4,
    borderBottomWidth: 0,
  },

  lastRow: {
    borderBottomWidth: 0,
  },

  bestBadge: {
    position: 'absolute',
    top: 4,
    right: 8,
    backgroundColor: COLORS.success,
    paddingHorizontal: 6,
    paddingVertical: 2,
    borderRadius: 4,
  },

  bestBadgeText: {
    fontSize: 8,
    fontWeight: '800',
    color: COLORS.white,
    letterSpacing: 0.5,
  },

  platformColumn: {
    flex: 1.2,
  },

  priceColumn: {
    flex: 1,
    alignItems: 'flex-start',
  },

  priceText: {
    fontSize: 16,
    fontWeight: '700',
    color: COLORS.textPrimary,
  },

  bestPriceText: {
    color: COLORS.success,
    fontSize: 17,
  },

  originalPriceText: {
    fontSize: 12,
    color: COLORS.gray500,
    textDecorationLine: 'line-through',
    marginTop: 2,
  },

  discountBadge: {
    backgroundColor: COLORS.error + '15',
    paddingHorizontal: 6,
    paddingVertical: 2,
    borderRadius: 4,
    marginTop: 4,
  },

  discountText: {
    fontSize: 10,
    fontWeight: '700',
    color: COLORS.error,
  },

  outOfStockText: {
    fontSize: 13,
    fontWeight: '500',
    color: COLORS.gray400,
    fontStyle: 'italic',
  },

  actionColumn: {
    flex: 0.6,
    alignItems: 'flex-end',
  },

  buyButton: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 14,
    paddingVertical: 8,
    borderRadius: 20,
    backgroundColor: COLORS.gray100,
    gap: 4,
  },

  buyButtonText: {
    fontSize: 13,
    fontWeight: '600',
    color: COLORS.textPrimary,
  },

  bestBuyButtonText: {
    color: COLORS.white,
  },

  unavailableButton: {
    padding: 8,
  },

  footer: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: 12,
    backgroundColor: COLORS.gray50,
    gap: 6,
  },

  footerText: {
    fontSize: 11,
    color: COLORS.gray500,
  },

  emptyContainer: {
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: 40,
    backgroundColor: COLORS.white,
    borderRadius: 16,
  },

  emptyText: {
    fontSize: 14,
    color: COLORS.gray500,
    marginTop: 12,
  },
});

export default memo(PriceComparisonTable);