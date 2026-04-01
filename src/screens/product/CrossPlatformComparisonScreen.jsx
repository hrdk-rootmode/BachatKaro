// ============================================
// CROSS-PLATFORM COMPARISON SCREEN
// ============================================

import React, { useEffect, useState } from 'react';
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  Image,
  TouchableOpacity,
  ActivityIndicator,
  Linking,
  Alert,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';

import homeAPI from '../../services/homeApi';
import { COLORS } from '../../utils/constants';
import { formatPrice, formatDate } from '../../utils/formatters';

// ============================================
// CROSS-PLATFORM COMPARISON SCREEN
// ============================================

const CrossPlatformComparisonScreen = ({ navigation, route }) => {
  const productId = route.params?.productId || route.params?.product_id;
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [expandedVariantId, setExpandedVariantId] = useState(0);

  useEffect(() => {
    loadCrossPlatformData();
  }, [productId]);

  const loadCrossPlatformData = async () => {
    try {
      setLoading(true);
      const response = await homeAPI.getCrossPlatformVariants(productId);

      if (!response.success) {
        setError(response.error || 'Failed to load comparison data');
        return;
      }

      setData(response.data);
      setError(null);
    } catch (err) {
      setError('An error occurred while loading comparison data');
      console.error('Cross-platform error:', err);
    } finally {
      setLoading(false);
    }
  };

  const openProductLink = (url) => {
    if (!url) {
      Alert.alert('Error', 'Product URL not available');
      return;
    }
    Linking.openURL(url).catch(() => {
      Alert.alert('Error', 'Could not open product link');
    });
  };

  if (loading) {
    return (
      <SafeAreaView style={styles.container}>
        <View style={styles.header}>
          <TouchableOpacity onPress={() => navigation.goBack()}>
            <Ionicons name="chevron-back" size={24} color={COLORS.text} />
          </TouchableOpacity>
          <Text style={styles.headerTitle}>All Variants</Text>
          <View style={{ width: 24 }} />
        </View>
        <View style={styles.centerContainer}>
          <ActivityIndicator size="large" color={COLORS.primary} />
          <Text style={styles.loadingText}>Loading comparison...</Text>
        </View>
      </SafeAreaView>
    );
  }

  if (error || !data) {
    return (
      <SafeAreaView style={styles.container}>
        <View style={styles.header}>
          <TouchableOpacity onPress={() => navigation.goBack()}>
            <Ionicons name="chevron-back" size={24} color={COLORS.text} />
          </TouchableOpacity>
          <Text style={styles.headerTitle}>All Variants</Text>
          <View style={{ width: 24 }} />
        </View>
        <View style={styles.centerContainer}>
          <Ionicons name="alert-circle" size={48} color={COLORS.error} />
          <Text style={styles.errorText}>{error || 'Failed to load data'}</Text>
          <TouchableOpacity
            style={styles.retryButton}
            onPress={loadCrossPlatformData}
          >
            <Text style={styles.retryButtonText}>Retry</Text>
          </TouchableOpacity>
        </View>
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView style={styles.container}>
      {/* Header */}
      <View style={styles.header}>
        <TouchableOpacity onPress={() => navigation.goBack()}>
          <Ionicons name="chevron-back" size={24} color={COLORS.text} />
        </TouchableOpacity>
        <Text style={styles.headerTitle}>All Variants</Text>
        <View style={{ width: 24 }} />
      </View>

      <ScrollView showsVerticalScrollIndicator={false}>
        {/* Product Info */}
        <View style={styles.productInfoSection}>
          <Text style={styles.productBrand}>{data.brand || 'Product'}</Text>
          <Text style={styles.productTitle}>{data.title}</Text>
          <Text style={styles.productCategory}>{data.category}</Text>
          <View style={styles.statsRow}>
            <View style={styles.statBox}>
              <Text style={styles.statLabel}>Platforms</Text>
              <Text style={styles.statValue}>{data.total_platforms}</Text>
            </View>
            <View style={styles.statBox}>
              <Text style={styles.statLabel}>Listings</Text>
              <Text style={styles.statValue}>{data.total_listings}</Text>
            </View>
          </View>
        </View>

        {/* Variants */}
        <View style={styles.variantsSection}>
          <Text style={styles.sectionTitle}>Available Variants ({data.variants?.length || 0})</Text>

          {data.variants && data.variants.length > 0 ? (
            data.variants.map((variant, index) => (
              <View key={index} style={styles.variantCard}>
                {/* Variant Header */}
                <TouchableOpacity
                  style={styles.variantHeader}
                  onPress={() => setExpandedVariantId(expandedVariantId === index ? -1 : index)}
                >
                  <View style={styles.variantInfo}>
                    <Text style={styles.variantName}>
                      {variant.variant_fingerprint || 'Standard'}
                    </Text>
                    <Text style={styles.variantPrice}>
                      ₹{Math.floor(variant.cheapest_price)}
                    </Text>
                  </View>
                  <View style={styles.variantBadge}>
                    <Text style={styles.platformCount}>{variant.platform_count}</Text>
                    <Ionicons
                      name={expandedVariantId === index ? 'chevron-up' : 'chevron-down'}
                      size={20}
                      color={COLORS.primary}
                    />
                  </View>
                </TouchableOpacity>

                {/* Expanded Platform Details */}
                {expandedVariantId === index && (
                  <View style={styles.platformsList}>
                    {variant.platforms.map((platform, pIndex) => (
                      <View key={pIndex} style={styles.platformCard}>
                        {/* Platform Header */}
                        <View style={styles.platformHeader}>
                          <View>
                            <Text style={styles.platformName}>
                              {platform.platform.toUpperCase()}
                            </Text>
                            <Text style={styles.platformMeta}>
                              {platform.in_stock ? '✅ In Stock' : '❌ Out of Stock'} • {platform.rating} ⭐
                            </Text>
                          </View>
                          <Text style={styles.platformPrice}>
                            ₹{Math.floor(platform.price)}
                          </Text>
                        </View>

                        {/* Pricing Details */}
                        <View style={styles.pricingDetails}>
                          {platform.original_price && (
                            <Text style={styles.originalPrice}>
                              MRP: ₹{Math.floor(platform.original_price)}
                            </Text>
                          )}
                          {platform.discount_percent !== null && (
                            <View style={styles.discountBadge}>
                              <Text style={styles.discountText}>
                                {platform.discount_percent}% OFF
                              </Text>
                            </View>
                          )}
                        </View>

                        {/* Last Scraped */}
                        {platform.last_scraped && (
                          <Text style={styles.lastScraped}>
                            Updated: {formatDate(platform.last_scraped)}
                          </Text>
                        )}

                        {/* Open Button */}
                        <TouchableOpacity
                          style={styles.openButton}
                          onPress={() => openProductLink(platform.url)}
                        >
                          <Ionicons name="open" size={16} color="white" />
                          <Text style={styles.openButtonText}>
                            Buy on {platform.platform.toUpperCase()}
                          </Text>
                        </TouchableOpacity>
                      </View>
                    ))}
                  </View>
                )}
              </View>
            ))
          ) : (
            <View style={styles.emptyState}>
              <Text style={styles.emptyText}>No variants found</Text>
            </View>
          )}
        </View>

        <View style={{ height: 30 }} />
      </ScrollView>
    </SafeAreaView>
  );
};

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#f8f9fa',
  },
  header: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingHorizontal: 16,
    paddingVertical: 12,
    backgroundColor: 'white',
    borderBottomWidth: 1,
    borderBottomColor: '#e0e0e0',
  },
  headerTitle: {
    fontSize: 18,
    fontWeight: '600',
    color: COLORS.text,
  },
  centerContainer: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
  },
  loadingText: {
    marginTop: 12,
    fontSize: 14,
    color: COLORS.textSecondary,
  },
  errorText: {
    marginTop: 12,
    fontSize: 14,
    color: COLORS.error,
    textAlign: 'center',
    paddingHorizontal: 20,
  },
  retryButton: {
    marginTop: 16,
    paddingHorizontal: 24,
    paddingVertical: 10,
    backgroundColor: COLORS.primary,
    borderRadius: 8,
  },
  retryButtonText: {
    color: 'white',
    fontWeight: '600',
  },
  productInfoSection: {
    backgroundColor: 'white',
    padding: 16,
    borderBottomWidth: 8,
    borderBottomColor: '#f0f0f0',
  },
  productBrand: {
    fontSize: 12,
    color: COLORS.textSecondary,
    fontWeight: '500',
    marginBottom: 4,
  },
  productTitle: {
    fontSize: 16,
    fontWeight: '600',
    color: COLORS.text,
    marginBottom: 4,
  },
  productCategory: {
    fontSize: 12,
    color: COLORS.textSecondary,
    marginBottom: 12,
  },
  statsRow: {
    flexDirection: 'row',
    justifyContent: 'space-around',
  },
  statBox: {
    flex: 1,
    paddingVertical: 8,
    paddingHorizontal: 12,
    backgroundColor: '#f5f5f5',
    borderRadius: 8,
    marginHorizontal: 4,
    alignItems: 'center',
  },
  statLabel: {
    fontSize: 11,
    color: COLORS.textSecondary,
    marginBottom: 4,
  },
  statValue: {
    fontSize: 16,
    fontWeight: '600',
    color: COLORS.primary,
  },
  variantsSection: {
    padding: 12,
  },
  sectionTitle: {
    fontSize: 14,
    fontWeight: '600',
    color: COLORS.text,
    marginBottom: 12,
    paddingHorizontal: 4,
  },
  variantCard: {
    backgroundColor: 'white',
    borderRadius: 12,
    marginBottom: 12,
    overflow: 'hidden',
    borderWidth: 1,
    borderColor: '#e0e0e0',
  },
  variantHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingHorizontal: 12,
    paddingVertical: 12,
  },
  variantInfo: {
    flex: 1,
  },
  variantName: {
    fontSize: 14,
    fontWeight: '600',
    color: COLORS.text,
    marginBottom: 2,
  },
  variantPrice: {
    fontSize: 13,
    fontWeight: '500',
    color: COLORS.primary,
  },
  variantBadge: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#e8f4f8',
    paddingHorizontal: 8,
    paddingVertical: 6,
    borderRadius: 6,
  },
  platformCount: {
    fontSize: 12,
    fontWeight: '600',
    color: COLORS.primary,
    marginRight: 4,
  },
  platformsList: {
    borderTopWidth: 1,
    borderTopColor: '#e0e0e0',
    paddingVertical: 12,
  },
  platformCard: {
    paddingHorizontal: 12,
    paddingVertical: 10,
    marginHorizontal: 0,
    marginVertical: 6,
    backgroundColor: '#fafafa',
    borderRadius: 8,
    borderLeftWidth: 3,
    borderLeftColor: COLORS.primary,
  },
  platformHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'flex-start',
    marginBottom: 8,
  },
  platformName: {
    fontSize: 13,
    fontWeight: '600',
    color: COLORS.text,
  },
  platformMeta: {
    fontSize: 11,
    color: COLORS.textSecondary,
    marginTop: 2,
  },
  platformPrice: {
    fontSize: 14,
    fontWeight: '600',
    color: COLORS.primary,
  },
  pricingDetails: {
    flexDirection: 'row',
    alignItems: 'center',
    marginBottom: 8,
  },
  originalPrice: {
    fontSize: 11,
    color: COLORS.textSecondary,
    textDecorationLine: 'line-through',
    marginRight: 8,
  },
  discountBadge: {
    backgroundColor: '#ff6b6b',
    paddingHorizontal: 6,
    paddingVertical: 2,
    borderRadius: 4,
  },
  discountText: {
    fontSize: 10,
    fontWeight: '600',
    color: 'white',
  },
  lastScraped: {
    fontSize: 10,
    color: COLORS.textSecondary,
    marginBottom: 10,
  },
  openButton: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: COLORS.primary,
    paddingVertical: 10,
    borderRadius: 8,
  },
  openButtonText: {
    color: 'white',
    fontWeight: '600',
    fontSize: 13,
    marginLeft: 6,
  },
  emptyState: {
    paddingVertical: 40,
    alignItems: 'center',
  },
  emptyText: {
    fontSize: 14,
    color: COLORS.textSecondary,
  },
});

export default CrossPlatformComparisonScreen;
