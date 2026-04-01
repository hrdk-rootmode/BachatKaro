import React, { memo } from 'react';
import { View, Text, StyleSheet, FlatList, TouchableOpacity } from 'react-native';
import { Image } from 'expo-image';
import { Ionicons } from '@expo/vector-icons';
import { COLORS } from '../../utils/constants';
import { formatPrice, parsePrice, getPlatformColor, getPlatformName, calculateDiscount } from '../../utils/formatters';

const PLACEHOLDER = 'L6PZfSi_.AyE_3t7t7R**0o#DgR4';

const MiniProductCard = memo(({ item, onPress }) => {
  const title = item?.title || item?.listings?.[0]?.title || item?.ai_generated_essence || 'Product';
  const imageUrl = item?.image_url || item?.listings?.[0]?.image_url;
  const price = parsePrice(item?.best_price || item?.listings?.[0]?.current_price);
  const originalPrice = parsePrice(item?.listings?.[0]?.original_price);
  const platform = item?.best_platform || item?.listings?.[0]?.platform;
  const category = item?.category || item?.subcategory || null;
  const discount = item?.discount_percentage || calculateDiscount(originalPrice, price);
  // ✅ NEW: Use platform_count from backend (or fallback to listings count)
  const platformCount = item?.platform_count || (Array.isArray(item?.listings) ? item.listings.length : 1);

  return (
    <TouchableOpacity style={styles.card} onPress={() => onPress?.(item)} activeOpacity={0.7}>
      <View style={styles.imageBox}>
        {imageUrl ? (
          <Image source={{ uri: imageUrl }} placeholder={PLACEHOLDER} style={styles.image} contentFit="cover" transition={200} />
        ) : (
          <View style={styles.imgPlaceholder}>
            <Ionicons name="image-outline" size={24} color={COLORS.gray300} />
          </View>
        )}
        {discount >= 5 && (
          <View style={styles.discBadge}>
            <Text style={styles.discText}>{Math.round(discount)}%</Text>
          </View>
        )}
        {/* ✅ NEW: Platform Count Badge */}
        {platformCount > 1 && (
          <View style={styles.platformCountBadge}>
            <Ionicons name="layers" size={10} color={COLORS.white} />
            <Text style={styles.platformCountBadgeText}>{platformCount}</Text>
          </View>
        )}
      </View>
      <View style={styles.info}>
        <Text style={styles.title} numberOfLines={2}>{title}</Text>
        {!!category && <Text style={styles.categoryText} numberOfLines={1}>{category}</Text>}
        <Text style={styles.price}>{formatPrice(price)}</Text>
        {originalPrice > price && <Text style={styles.origPrice}>{formatPrice(originalPrice)}</Text>}
        {platformCount > 1 && (
          <Text style={styles.compareHint}>Available on {platformCount} platforms</Text>
        )}
        {platform && (
          <View style={[styles.platBadge, { backgroundColor: getPlatformColor(platform) + '15' }]}>
            <Text style={[styles.platText, { color: getPlatformColor(platform) }]}>{getPlatformName(platform)}</Text>
          </View>
        )}
      </View>
    </TouchableOpacity>
  );
});

const ProductSection = ({ title, subtitle, emoji, products, onProductPress, onSeeAll, isLoading, accentColor = COLORS.primary, maxItems = 10 }) => {
  if (!products || products.length === 0) {
    if (isLoading) {
      return (
        <View style={styles.section}>
          <View style={styles.header}>
            <View style={styles.titleWrap}>
              <View style={[styles.titleAccent, { backgroundColor: accentColor }]} />
              <Text style={styles.sectionTitle}>{emoji} {title}</Text>
            </View>
          </View>
          <View style={styles.loadingRow}>
            {[1, 2, 3].map(i => <View key={i} style={styles.skeletonCard} />)}
          </View>
        </View>
      );
    }
    return null;
  }

  return (
    <View style={styles.section}>
      <View style={styles.header}>
        <View>
          <View style={styles.titleWrap}>
            <View style={[styles.titleAccent, { backgroundColor: accentColor }]} />
            <Text style={styles.sectionTitle}>{emoji} {title}</Text>
          </View>
          {!!subtitle && <Text style={styles.subtitle}>{subtitle}</Text>}
        </View>
        {onSeeAll && (
          <TouchableOpacity onPress={onSeeAll}>
            <Text style={styles.seeAll}>See All →</Text>
          </TouchableOpacity>
        )}
      </View>
      <FlatList
        data={products.slice(0, Math.max(1, maxItems))}
        renderItem={({ item }) => <MiniProductCard item={item} onPress={onProductPress} />}
        keyExtractor={(item, index) => `${title}-${item?.id || item?.product_id || index}`}
        horizontal
        showsHorizontalScrollIndicator={false}
        contentContainerStyle={styles.listContent}
      />
    </View>
  );
};

const styles = StyleSheet.create({
  section: { marginBottom: 24 },
  header: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', paddingHorizontal: 16, marginBottom: 12 },
  titleWrap: { flexDirection: 'row', alignItems: 'center' },
  titleAccent: { width: 4, height: 18, borderRadius: 6, marginRight: 8 },
  sectionTitle: { fontSize: 18, fontWeight: '700', color: COLORS.textPrimary },
  subtitle: { fontSize: 12, color: COLORS.textSecondary, marginTop: 4, marginLeft: 12 },
  seeAll: { fontSize: 14, fontWeight: '600', color: COLORS.primary },
  listContent: { paddingLeft: 16, paddingRight: 8 },
  card: { width: 150, marginRight: 12, backgroundColor: COLORS.white, borderRadius: 12, overflow: 'hidden', shadowColor: '#000', shadowOffset: { width: 0, height: 1 }, shadowOpacity: 0.08, shadowRadius: 4, elevation: 2 },
  imageBox: { width: '100%', height: 130, backgroundColor: COLORS.gray50, position: 'relative' },
  image: { width: '100%', height: '100%' },
  imgPlaceholder: { width: '100%', height: '100%', alignItems: 'center', justifyContent: 'center' },
  discBadge: { position: 'absolute', top: 6, left: 6, backgroundColor: COLORS.error, paddingHorizontal: 6, paddingVertical: 2, borderRadius: 4 },
  discText: { color: COLORS.white, fontSize: 10, fontWeight: '700' },
  platformCountBadge: { position: 'absolute', bottom: 6, right: 6, backgroundColor: COLORS.primary, flexDirection: 'row', alignItems: 'center', gap: 3, paddingHorizontal: 6, paddingVertical: 3, borderRadius: 6 },
  platformCountBadgeText: { color: COLORS.white, fontSize: 9, fontWeight: '700' },
  info: { padding: 10 },
  title: { fontSize: 12, fontWeight: '500', color: COLORS.textPrimary, lineHeight: 16, minHeight: 32, marginBottom: 4 },
  categoryText: { fontSize: 10, color: COLORS.gray600, marginBottom: 2 },
  price: { fontSize: 15, fontWeight: '700', color: COLORS.primary },
  origPrice: { fontSize: 11, color: COLORS.gray500, textDecorationLine: 'line-through', marginTop: 2 },
  compareHint: { fontSize: 10, color: COLORS.info, marginTop: 4, fontWeight: '600' },
  platBadge: { marginTop: 6, alignSelf: 'flex-start', paddingHorizontal: 6, paddingVertical: 2, borderRadius: 4 },
  platText: { fontSize: 10, fontWeight: '600' },
  loadingRow: { flexDirection: 'row', paddingLeft: 16 },
  skeletonCard: { width: 150, height: 200, marginRight: 12, backgroundColor: COLORS.gray100, borderRadius: 12 },
});

export default memo(ProductSection);