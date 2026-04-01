import React, { memo } from 'react';
import { View, Text, StyleSheet, ScrollView, TouchableOpacity } from 'react-native';
import { COLORS } from '../../utils/constants';

const CATEGORIES = [
  { id: 'trending', label: 'Trending', emoji: '🔥', query: 'trending deals', homeSectionId: 'trending-now', bg: '#FFF2E6', border: '#FFBE99' },
  { id: 'phones', label: 'Phones', emoji: '📱', query: 'smartphone', homeSectionId: 'mobiles', bg: '#E8F2FF', border: '#A6C8FF' },
  { id: 'laptops', label: 'Laptops', emoji: '💻', query: 'laptop', homeSectionId: 'laptops', bg: '#EAF9F4', border: '#9FE3C9' },
  { id: 'fashion', label: 'Fashion', emoji: '👗', query: 'fashion clothing', homeSectionId: 'fashion', bg: '#FFF2E8', border: '#FFC9A3' },
  { id: 'beauty', label: 'Beauty', emoji: '💄', query: 'beauty skincare', homeSectionId: 'beauty', bg: '#FFEAF1', border: '#FFB2C8' },
  { id: 'home', label: 'Home', emoji: '🏠', query: 'home kitchen', homeSectionId: 'home', bg: '#F3F0FF', border: '#CABDFF' },
  { id: 'sports', label: 'Sports', emoji: '🏃', query: 'sports fitness', bg: '#FFF9E8', border: '#FDE08A' },
  { id: 'audio', label: 'Audio', emoji: '🎧', query: 'headphones earbuds', bg: '#EAF6FF', border: '#9FD8FF' },
  { id: 'tv', label: 'TV', emoji: '📺', query: 'smart tv', bg: '#F0FAF7', border: '#9EDFCF' },
];

const QuickCategories = ({ onCategoryPress, categories = CATEGORIES }) => (
  <View style={styles.container}>
    <View style={styles.headerRow}>
      <Text style={styles.heading}>Top Categories</Text>
      <Text style={styles.caption}>Matched from live feed</Text>
    </View>
    <ScrollView
      horizontal
      showsHorizontalScrollIndicator={false}
      contentContainerStyle={styles.scrollContent}
      nestedScrollEnabled
      keyboardShouldPersistTaps="handled"
    >
      {categories.map((cat) => (
        <TouchableOpacity key={cat.id} style={styles.categoryItem} onPress={() => onCategoryPress?.(cat)} activeOpacity={0.8}>
          <View style={[styles.iconContainer, { backgroundColor: cat.bg, borderColor: cat.border }]}>
            <Text style={styles.emoji}>{cat.emoji}</Text>
            {typeof cat.count === 'number' && (
              <View style={styles.countBadge}>
                <Text style={styles.countText}>{cat.count}</Text>
              </View>
            )}
          </View>
          <Text style={styles.label}>{cat.label}</Text>
        </TouchableOpacity>
      ))}
    </ScrollView>
  </View>
);

const styles = StyleSheet.create({
  container: { marginBottom: 20 },
  headerRow: {
    paddingHorizontal: 16,
    marginBottom: 10,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  heading: { fontSize: 16, fontWeight: '700', color: COLORS.textPrimary },
  caption: { fontSize: 12, color: COLORS.textSecondary, fontWeight: '500' },
  scrollContent: { paddingHorizontal: 12, paddingBottom: 2 },
  categoryItem: { alignItems: 'center', marginHorizontal: 6, width: 72 },
  iconContainer: {
    width: 52,
    height: 52,
    borderRadius: 26,
    position: 'relative',
    borderWidth: 1,
    alignItems: 'center',
    justifyContent: 'center',
    marginBottom: 5,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.05,
    shadowRadius: 2,
    elevation: 1,
  },
  emoji: { fontSize: 23 },
  countBadge: {
    position: 'absolute',
    right: -2,
    top: -2,
    minWidth: 18,
    height: 18,
    borderRadius: 9,
    paddingHorizontal: 4,
    backgroundColor: COLORS.primary,
    alignItems: 'center',
    justifyContent: 'center',
  },
  countText: { color: COLORS.white, fontSize: 10, fontWeight: '700' },
  label: { fontSize: 10.5, fontWeight: '600', color: COLORS.textPrimary, textAlign: 'center' },
});

export default memo(QuickCategories);