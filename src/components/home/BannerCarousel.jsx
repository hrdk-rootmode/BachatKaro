import React, { useRef, useState, useEffect, useMemo, memo } from 'react';
import {
  View, Text, StyleSheet, FlatList, Dimensions, TouchableOpacity, ActivityIndicator,
} from 'react-native';
import { LinearGradient } from 'expo-linear-gradient';
import { Image } from 'expo-image';
import { Ionicons } from '@expo/vector-icons';
import { homeAPI } from '../../services/homeApi';
import { COLORS } from '../../utils/constants';

const { width: SCREEN_WIDTH } = Dimensions.get('window');
const BANNER_HEIGHT = 180;
const AUTO_SCROLL_INTERVAL = 5000;
const ITEM_WIDTH = SCREEN_WIDTH - 32;
const ITEM_SPACING = 16;
const PLACEHOLDER = 'data:image/gif;base64,R0lGODlhAQABAAAAACw=';

// ✅ Fallback banners if API fails
const FALLBACK_BANNERS = [
  { id: '1', title: 'Mega Electronics Sale', subtitle: 'Up to 70% OFF', gradient: ['#FF6B35', '#FF8555'], emoji: '📱' },
  { id: '2', title: 'Fashion Fiesta', subtitle: 'Best prices', gradient: ['#4ECDC4', '#44B3AB'], emoji: '👗' },
  { id: '3', title: 'Compare & Save', subtitle: 'Lowest price guaranteed', gradient: ['#667EEA', '#764BA2'], emoji: '💰' },
];

const BannerCarousel = ({ products, onBannerPress, isLoading }) => {
  const flatListRef = useRef(null);
  const [activeIndex, setActiveIndex] = useState(0);
  const autoScrollTimer = useRef(null);
  
  // ✅ Convert products to banner format
  const banners = useMemo(() => {
    if (!Array.isArray(products) || products.length === 0) {
      return FALLBACK_BANNERS;
    }
    
    return products.slice(0, 6).map((product, idx) => ({
      id: product.product_id || idx.toString(),
      product_id: product.product_id,
      title: product.title || `Product ${idx + 1}`,
      subtitle: product.best_platform ? `${String(product.best_platform).toUpperCase()} - ₹${Math.floor(product.best_price || 0).toLocaleString('en-IN')}` : `₹${Math.floor(product.best_price || 0).toLocaleString('en-IN')}`,
      image_url: product.image_url,
      platform: product.best_platform,
      discount_percent: product.discount_percentage || 0,
      gradient: [
        ['#FF6B35', '#FF8555'],
        ['#4ECDC4', '#44B3AB'],
        ['#667EEA', '#764BA2'],
        ['#F093FB', '#F5576C'],
        ['#4FACFE', '#00F2FE'],
        ['#43E97B', '#38F9D7'],
      ][idx % 6],
      emoji: ['📦', '🎁', '💝', '🛍️', '🏆', '⭐'][idx % 6],
    }));
  }, [products]);

  // ✅ Auto-scroll carousel
  const scrollToIndex = (index) => {
    if (flatListRef.current && banners.length > 0) {
      const offset = index * (ITEM_WIDTH + ITEM_SPACING);
      flatListRef.current.scrollToOffset({ offset, animated: true });
    }
  };

  useEffect(() => {
    if (banners.length === 0) return;
    
    if (autoScrollTimer.current) {
      clearInterval(autoScrollTimer.current);
    }

    autoScrollTimer.current = setInterval(() => {
      const nextIndex = (activeIndex + 1) % banners.length;
      scrollToIndex(nextIndex);
      setActiveIndex(nextIndex);
    }, AUTO_SCROLL_INTERVAL);

    return () => {
      if (autoScrollTimer.current) {
        clearInterval(autoScrollTimer.current);
      }
    };
  }, [activeIndex, banners.length]);

  const onViewableItemsChanged = useRef(({ viewableItems }) => {
    if (viewableItems.length > 0) {
      setActiveIndex(viewableItems[0].index || 0);
    }
  }).current;

  const renderBanner = ({ item }) => (
    <TouchableOpacity
      style={styles.bannerContainer}
      activeOpacity={0.9}
      onPress={() => onBannerPress?.(item)}
    >
      <LinearGradient 
        colors={item.gradient} 
        style={styles.bannerGradient} 
        start={{ x: 0, y: 0 }} 
        end={{ x: 1, y: 1 }}
      >
        <View style={styles.bannerContent}>
          <View style={styles.bannerImageWrap}>
            {item.image_url ? (
              <Image
                source={{ uri: item.image_url }}
                placeholder={PLACEHOLDER}
                style={styles.bannerImage}
                contentFit="cover"
                transition={200}
              />
            ) : (
              <View style={styles.bannerEmojiFallback}>
                <Text style={styles.bannerEmoji}>{item.emoji}</Text>
              </View>
            )}
          </View>
          <View style={styles.bannerTextContainer}>
            <Text style={styles.bannerTitle} numberOfLines={2}>{item.title}</Text>
            <Text style={styles.bannerSubtitle} numberOfLines={1}>{item.subtitle}</Text>
            {item.discount_percent > 0 && (
              <View style={styles.discountTag}>
                <Text style={styles.discountText}>{Math.round(item.discount_percent)}% OFF</Text>
              </View>
            )}
          </View>
        </View>
        <View style={styles.bannerCTA}>
          <Ionicons name="chevron-forward" size={24} color={COLORS.white} />
        </View>
      </LinearGradient>
    </TouchableOpacity>
  );

  if (isLoading) {
    return (
      <View style={[styles.container, { justifyContent: 'center', alignItems: 'center' }]}>
        <ActivityIndicator size="small" color={COLORS.primary} />
      </View>
    );
  }

  return (
    <View style={styles.container}>
      <FlatList
        ref={flatListRef}
        data={banners}
        renderItem={renderBanner}
        keyExtractor={(item) => item.id}
        horizontal
        pagingEnabled={false}
        showsHorizontalScrollIndicator={false}
        onViewableItemsChanged={onViewableItemsChanged}
        scrollEventThrottle={16}
        decelerationRate="fast"
        snapToInterval={ITEM_WIDTH + ITEM_SPACING}
        snapToAlignment="start"
        contentContainerStyle={styles.flatListContent}
        viewabilityConfig={{ viewAreaCoveragePercentThreshold: 50 }}
        getItemLayout={(_, index) => ({
          length: ITEM_WIDTH,
          offset: (ITEM_WIDTH + ITEM_SPACING) * index,
          index,
        })}
      />
      <View style={styles.pagination}>
        {banners.map((_, index) => (
          <View 
            key={`dot-${index}`} 
            style={[styles.dot, activeIndex === index && styles.dotActive]} 
          />
        ))}
      </View>
    </View>
  );
};

const styles = StyleSheet.create({
  container: { 
    marginBottom: 20,
  },
  flatListContent: {
    paddingHorizontal: 16,
  },
  bannerContainer: { 
    width: ITEM_WIDTH, 
    marginRight: ITEM_SPACING,
    borderRadius: 16, 
    overflow: 'hidden' 
  },
  bannerGradient: { 
    height: BANNER_HEIGHT, 
    padding: 20, 
    justifyContent: 'space-between' 
  },
  bannerContent: { 
    flexDirection: 'row', 
    alignItems: 'center' 
  },
  bannerImageWrap: {
    width: 72,
    height: 72,
    borderRadius: 18,
    overflow: 'hidden',
    marginRight: 14,
    backgroundColor: 'rgba(255,255,255,0.18)',
    borderWidth: 1,
    borderColor: 'rgba(255,255,255,0.2)',
    justifyContent: 'center',
    alignItems: 'center',
  },
  bannerImage: {
    width: '100%',
    height: '100%',
  },
  bannerEmojiFallback: {
    width: '100%',
    height: '100%',
    justifyContent: 'center',
    alignItems: 'center',
  },
  bannerEmoji: {
    fontSize: 40,
  },
  bannerTextContainer: { 
    flex: 1 
  },
  bannerTitle: { 
    fontSize: 22, 
    fontWeight: '800', 
    color: COLORS.white, 
    marginBottom: 4 
  },
  bannerSubtitle: { 
    fontSize: 14, 
    color: 'rgba(255,255,255,0.9)', 
    fontWeight: '500',
    marginBottom: 6,
  },
  discountTag: {
    backgroundColor: 'rgba(255,255,255,0.3)',
    paddingHorizontal: 8,
    paddingVertical: 4,
    borderRadius: 6,
    alignSelf: 'flex-start',
  },
  discountText: {
    color: COLORS.white,
    fontSize: 11,
    fontWeight: '700',
  },
  bannerCTA: { 
    alignSelf: 'flex-end', 
    backgroundColor: 'rgba(255,255,255,0.25)', 
    paddingHorizontal: 16, 
    paddingVertical: 8, 
    borderRadius: 20 
  },
  bannerCTAText: { 
    color: COLORS.white, 
    fontSize: 13, 
    fontWeight: '700' 
  },
  pagination: { 
    flexDirection: 'row', 
    justifyContent: 'center', 
    marginTop: 12 
  },
  dot: { 
    width: 8, 
    height: 8, 
    borderRadius: 4, 
    backgroundColor: COLORS.gray300, 
    marginHorizontal: 4 
  },
  dotActive: { 
    backgroundColor: COLORS.primary, 
    width: 24 
  },
});

export default memo(BannerCarousel);