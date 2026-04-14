// ============================================
// DEALHUNT APP - COMPREHENSIVE PRICE COMPARISON TABLE
// ============================================

import React, { memo, useMemo } from 'react';
import {
  View,
  Text,
  StyleSheet,
  TouchableOpacity,
  Linking,
  Alert,
  Image,
  ScrollView,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';

import PlatformBadge from './PlatformBadge';
import { COLORS } from '../utils/constants';
import {
  formatPrice,
  parsePrice,
  formatTimeAgo,
  getPlatformColor,
  toEpochMs,
  parseApiDate,
} from '../utils/formatters';

/**
 * Comprehensive price comparison table showing all platforms with full details
 * 
 * @param {Array} listings - Product listings from all platforms
 * @param {string} bestPlatform - Platform with best price
 * @param {function} onBuyPress - Optional custom buy handler
 * @param {Object} product - Main product object for image fallback
 */
const PriceComparisonTable = ({ listings, bestPlatform, onBuyPress, product }) => {
  // Validate image URL
  const isValidDisplayImage = (url) => {
    if (!url || typeof url !== 'string') return false;
    const u = url.trim().toLowerCase();
    if (!u) return false;
    if (u.includes('svgicons') || u.includes('wishlist.svg') || u.endsWith('.svg')) return false;
    return u.startsWith('http');
  };

  // Get display image for listing
  const getListingImage = (listing) => {
    // Try listing image first
    if (isValidDisplayImage(listing.image_url)) {
      return listing.image_url;
    }
    // Fallback to product image
    if (product && isValidDisplayImage(product.image_url)) {
      return product.image_url;
    }
    return null;
  };

  // Format last scraped time
  const formatLastScraped = (dateStr) => {
    if (!dateStr) return 'Unknown';
    const date = parseApiDate(dateStr);
    if (!date) return 'Unknown';
    
    const now = new Date();
    const diffMs = now - date;
    const diffMins = Math.floor(diffMs / 60000);
    const diffHours = Math.floor(diffMins / 60);
    const diffDays = Math.floor(diffHours / 24);
    
    if (diffMins < 1) return 'Just now';
    if (diffMins < 60) return `${diffMins}m ago`;
    if (diffHours < 24) return `${diffHours}h ago`;
    if (diffDays < 7) return `${diffDays}d ago`;
    return date.toLocaleDateString('en-IN', { month: 'short', day: 'numeric' });
  };

  // Get confidence level text
  const getConfidenceLevel = (confidence) => {
    if (!confidence) return null;
    if (confidence >= 0.9) return { text: 'High', color: COLORS.success };
    if (confidence >= 0.7) return { text: 'Medium', color: COLORS.warning };
    return { text: 'Low', color: COLORS.error };
  };

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

    const url = listing.product_url || listing.url;
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
        <View style={styles.headerTitleRow}>
          <Text style={styles.headerTitle}>📊 Cross-Platform Comparison</Text>
          <View style={styles.headerBadge}>
            <Text style={styles.headerBadgeText}>
              {sortedListings.length} Platform{sortedListings.length > 1 ? 's' : ''}
            </Text>
          </View>
        </View>
        <Text style={styles.headerSubtitle}>
          Compare prices, ratings, and delivery across all platforms
        </Text>
      </View>

      {/* Table Header */}
      <View style={styles.tableHeader}>
        <Text style={styles.tableHeaderText}>Platform</Text>
        <Text style={styles.tableHeaderText}>Price</Text>
        <Text style={styles.tableHeaderText}>Rating</Text>
        <Text style={styles.tableHeaderText}>Stock</Text>
        <Text style={styles.tableHeaderText}>Delivery</Text>
        <Text style={styles.tableHeaderText}>Updated</Text>
        <Text style={styles.tableHeaderText}>Action</Text>
      </View>

      {/* Table Rows - Scrollable */}
      <ScrollView horizontal showsHorizontalScrollIndicator={false}>
        <View style={styles.scrollableContent}>
          {sortedListings.map((listing, index) => {
            const isBest = listing.platform === bestPlatform && listing.in_stock;
            const price = listing.current_price || listing.price || 0;
            const originalPrice = listing.original_price || 0;
            const hasDiscount = originalPrice > price && originalPrice > 0;
            const discountPct = listing.discount_percentage || listing.discount_percent || 0;
            const platformColor = getPlatformColor(listing.platform);
            const listingImage = getListingImage(listing);
            const confidence = getConfidenceLevel(listing.extraction_confidence);

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
                    <Ionicons name="trophy" size={12} color={COLORS.white} />
                    <Text style={styles.bestBadgeText}>BEST</Text>
                  </View>
                )}

                {/* Platform Column with Image */}
                <View style={styles.columnPlatform}>
                  <View style={styles.platformRow}>
                    {listingImage ? (
                      <Image source={{ uri: listingImage }} style={styles.productImage} />
                    ) : (
                      <View style={styles.imagePlaceholder}>
                        <Ionicons name="image-outline" size={20} color={COLORS.gray400} />
                      </View>
                    )}
                    <View style={styles.platformInfo}>
                      <PlatformBadge
                        platform={listing.platform || 'amazon'}
                        size="small"
                        showName={true}
                      />
                      {listing.seller_name && (
                        <Text style={styles.sellerName} numberOfLines={1}>
                          {listing.seller_name}
                        </Text>
                      )}
                      {listing.seller_rating && (
                        <View style={styles.sellerRatingRow}>
                          <Ionicons name="star" size={10} color="#FFC107" />
                          <Text style={styles.sellerRatingText}>
                            {typeof listing.seller_rating === 'number' 
                              ? listing.seller_rating.toFixed(1) 
                              : listing.seller_rating}
                          </Text>
                        </View>
                      )}
                    </View>
                  </View>
                </View>

                {/* Price Column */}
                <View style={styles.columnPrice}>
                  {listing.in_stock ? (
                    <View>
                      <Text style={[styles.priceText, isBest && styles.bestPriceText]}>
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
                            -{Math.round(discountPct)}%
                          </Text>
                        </View>
                      )}
                    </View>
                  ) : (
                    <Text style={styles.outOfStockText}>N/A</Text>
                  )}
                </View>

                {/* Rating Column */}
                <View style={styles.columnRating}>
                  {listing.rating !== null && listing.rating !== undefined ? (
                    <View style={styles.ratingContainer}>
                      <View style={styles.ratingStars}>
                        <Ionicons name="star" size={12} color="#FFC107" />
                        <Text style={styles.ratingValue}>
                          {typeof listing.rating === 'number' ? listing.rating.toFixed(1) : listing.rating}
                        </Text>
                      </View>
                      {listing.review_count && listing.review_count > 0 && (
                        <Text style={styles.reviewCount}>
                          ({listing.review_count})
                        </Text>
                      )}
                    </View>
                  ) : (
                    <Text style={styles.notAvailableText}>N/A</Text>
                  )}
                </View>

                {/* Stock Column */}
                <View style={styles.columnStock}>
                  <View style={[
                    styles.stockBadge,
                    { backgroundColor: listing.in_stock ? COLORS.successLight : COLORS.errorLight }
                  ]}>
                    <Ionicons 
                      name={listing.in_stock ? "checkmark-circle" : "close-circle"} 
                      size={14} 
                      color={listing.in_stock ? COLORS.success : COLORS.error} 
                    />
                    <Text style={[
                      styles.stockText,
                      { color: listing.in_stock ? COLORS.success : COLORS.error }
                    ]}>
                      {listing.in_stock ? 'In Stock' : 'Out of Stock'}
                    </Text>
                  </View>
                  {listing.in_stock && listing.stock_count && (
                    <Text style={styles.stockCount}>
                      {listing.stock_count} available
                    </Text>
                  )}
                </View>

                {/* Delivery Column */}
                <View style={styles.columnDelivery}>
                  {listing.delivery_days ? (
                    <View style={styles.deliveryInfo}>
                      <Ionicons name="time" size={12} color={COLORS.info} />
                      <Text style={styles.deliveryText}>
                        {listing.delivery_days} {listing.delivery_days === 1 ? 'day' : 'days'}
                      </Text>
                    </View>
                  ) : (
                    <Text style={styles.notAvailableText}>N/A</Text>
                  )}
                </View>

                {/* Updated Column */}
                <View style={styles.columnUpdated}>
                  <View style={styles.updatedInfo}>
                    <Ionicons name="refresh" size={12} color={COLORS.gray500} />
                    <Text style={styles.updatedText}>
                      {formatLastScraped(listing.last_scraped_at || listing.last_scraped)}
                    </Text>
                  </View>
                  {confidence && (
                    <View style={styles.confidenceBadge}>
                      <Text style={[styles.confidenceText, { color: confidence.color }]}>
                        {confidence.text}
                      </Text>
                    </View>
                  )}
                </View>

                {/* Action Column */}
                <View style={styles.columnAction}>
                  {listing.in_stock ? (
                    <TouchableOpacity
                      style={[
                        styles.buyButton,
                        isBest && { backgroundColor: platformColor },
                      ]}
                      onPress={() => handleBuyPress(listing)}
                      activeOpacity={0.7}
                    >
                      <Ionicons 
                        name="open-outline" 
                        size={16} 
                        color={isBest ? COLORS.white : platformColor} 
                      />
                      <Text style={[
                        styles.buyButtonText,
                        isBest && styles.bestBuyButtonText,
                      ]}>
                        Buy
                      </Text>
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
      </ScrollView>

      {/* Footer */}
      <View style={styles.footer}>
        <View style={styles.footerInfo}>
          <Ionicons name="information-circle" size={14} color={COLORS.info} />
          <Text style={styles.footerText}>
            Prices are updated periodically. Click "Buy" to visit the platform for the latest price.
          </Text>
        </View>
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
    marginVertical: 12,
  },

  header: {
    paddingHorizontal: 16,
    paddingVertical: 16,
    borderBottomWidth: 1,
    borderBottomColor: COLORS.gray100,
    backgroundColor: COLORS.gray50,
  },

  headerTitleRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginBottom: 4,
  },

  headerTitle: {
    fontSize: 18,
    fontWeight: '700',
    color: COLORS.textPrimary,
  },

  headerBadge: {
    backgroundColor: COLORS.primary,
    paddingHorizontal: 10,
    paddingVertical: 4,
    borderRadius: 12,
  },

  headerBadgeText: {
    fontSize: 12,
    fontWeight: '600',
    color: COLORS.white,
  },

  headerSubtitle: {
    fontSize: 13,
    color: COLORS.textSecondary,
  },

  tableHeader: {
    flexDirection: 'row',
    paddingHorizontal: 12,
    paddingVertical: 12,
    backgroundColor: COLORS.gray100,
    borderBottomWidth: 1,
    borderBottomColor: COLORS.gray200,
  },

  tableHeaderText: {
    fontSize: 11,
    fontWeight: '700',
    color: COLORS.textSecondary,
    textTransform: 'uppercase',
    letterSpacing: 0.5,
  },

  scrollableContent: {
    minWidth: 800,
  },

  row: {
    flexDirection: 'row',
    paddingVertical: 16,
    paddingHorizontal: 12,
    borderBottomWidth: 1,
    borderBottomColor: COLORS.gray100,
    position: 'relative',
    backgroundColor: COLORS.white,
  },

  bestRow: {
    backgroundColor: COLORS.successLight + '30',
    borderLeftWidth: 3,
    borderLeftColor: COLORS.success,
  },

  lastRow: {
    borderBottomWidth: 0,
  },

  bestBadge: {
    position: 'absolute',
    top: 8,
    right: 8,
    backgroundColor: COLORS.success,
    paddingHorizontal: 8,
    paddingVertical: 3,
    borderRadius: 12,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
    zIndex: 1,
  },

  bestBadgeText: {
    fontSize: 10,
    fontWeight: '800',
    color: COLORS.white,
    letterSpacing: 0.5,
  },

  // Column widths
  columnPlatform: {
    width: 180,
    marginRight: 12,
  },

  columnPrice: {
    width: 100,
    marginRight: 12,
  },

  columnRating: {
    width: 80,
    marginRight: 12,
  },

  columnStock: {
    width: 100,
    marginRight: 12,
  },

  columnDelivery: {
    width: 80,
    marginRight: 12,
  },

  columnUpdated: {
    width: 100,
    marginRight: 12,
  },

  columnAction: {
    width: 80,
    alignItems: 'flex-end',
  },

  // Platform column
  platformRow: {
    flexDirection: 'row',
    alignItems: 'center',
  },

  productImage: {
    width: 50,
    height: 50,
    borderRadius: 8,
    backgroundColor: COLORS.gray100,
    marginRight: 10,
  },

  imagePlaceholder: {
    width: 50,
    height: 50,
    borderRadius: 8,
    backgroundColor: COLORS.gray100,
    justifyContent: 'center',
    alignItems: 'center',
    marginRight: 10,
  },

  platformInfo: {
    flex: 1,
  },

  sellerName: {
    fontSize: 11,
    color: COLORS.textSecondary,
    marginTop: 2,
  },

  sellerRatingRow: {
    flexDirection: 'row',
    alignItems: 'center',
    marginTop: 2,
  },

  sellerRatingText: {
    fontSize: 10,
    color: COLORS.textSecondary,
    marginLeft: 2,
  },

  // Price column
  priceText: {
    fontSize: 16,
    fontWeight: '700',
    color: COLORS.textPrimary,
  },

  bestPriceText: {
    color: COLORS.success,
    fontSize: 18,
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
    alignSelf: 'flex-start',
  },

  discountText: {
    fontSize: 10,
    fontWeight: '700',
    color: COLORS.error,
  },

  outOfStockText: {
    fontSize: 13,
    fontWeight: '500',
    color: COLORS.error,
  },

  notAvailableText: {
    fontSize: 12,
    color: COLORS.gray400,
  },

  // Rating column
  ratingContainer: {
    flexDirection: 'column',
  },

  ratingStars: {
    flexDirection: 'row',
    alignItems: 'center',
  },

  ratingValue: {
    fontSize: 13,
    fontWeight: '600',
    color: COLORS.textPrimary,
    marginLeft: 4,
  },

  reviewCount: {
    fontSize: 10,
    color: COLORS.textSecondary,
    marginTop: 2,
  },

  // Stock column
  stockBadge: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 8,
    paddingVertical: 4,
    borderRadius: 6,
    alignSelf: 'flex-start',
  },

  stockText: {
    fontSize: 11,
    fontWeight: '600',
    marginLeft: 4,
  },

  stockCount: {
    fontSize: 10,
    color: COLORS.textSecondary,
    marginTop: 4,
  },

  // Delivery column
  deliveryInfo: {
    flexDirection: 'row',
    alignItems: 'center',
  },

  deliveryText: {
    fontSize: 12,
    color: COLORS.textPrimary,
    marginLeft: 4,
  },

  // Updated column
  updatedInfo: {
    flexDirection: 'row',
    alignItems: 'center',
  },

  updatedText: {
    fontSize: 11,
    color: COLORS.textSecondary,
    marginLeft: 4,
  },

  confidenceBadge: {
    marginTop: 4,
  },

  confidenceText: {
    fontSize: 9,
    fontWeight: '600',
  },

  // Action column
  buyButton: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: 16,
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

  // Footer
  footer: {
    paddingHorizontal: 16,
    paddingVertical: 12,
    backgroundColor: COLORS.gray50,
    borderTopWidth: 1,
    borderTopColor: COLORS.gray100,
  },

  footerInfo: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: 6,
  },

  footerText: {
    fontSize: 11,
    color: COLORS.textSecondary,
    flex: 1,
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