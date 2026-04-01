// ============================================
// DEALHUNT APP - SKELETON LOADING CARD
// ============================================

import React, { useEffect, useRef } from 'react';
import {
  View,
  StyleSheet,
  Animated,
} from 'react-native';

import { COLORS } from '../../utils/constants';

/**
 * Skeleton loading card with shimmer animation
 * Matches ProductCard layout
 */
const SkeletonCard = () => {
  const shimmerAnim = useRef(new Animated.Value(0)).current;

  useEffect(() => {
    // Continuous shimmer animation
    const shimmer = Animated.loop(
      Animated.sequence([
        Animated.timing(shimmerAnim, {
          toValue: 1,
          duration: 1000,
          useNativeDriver: true,
        }),
        Animated.timing(shimmerAnim, {
          toValue: 0,
          duration: 1000,
          useNativeDriver: true,
        }),
      ])
    );
    shimmer.start();

    return () => shimmer.stop();
  }, [shimmerAnim]);

  const opacity = shimmerAnim.interpolate({
    inputRange: [0, 1],
    outputRange: [0.3, 0.7],
  });

  return (
    <View style={styles.card}>
      {/* Image Placeholder */}
      <Animated.View style={[styles.imagePlaceholder, { opacity }]} />

      {/* Content */}
      <View style={styles.content}>
        {/* Title Lines */}
        <Animated.View style={[styles.titleLine, { opacity }]} />
        <Animated.View style={[styles.titleLineShort, { opacity }]} />

        {/* Price Line */}
        <Animated.View style={[styles.priceLine, { opacity }]} />

        {/* Footer */}
        <View style={styles.footer}>
          <Animated.View style={[styles.badgePlaceholder, { opacity }]} />
          <Animated.View style={[styles.heartPlaceholder, { opacity }]} />
        </View>
      </View>
    </View>
  );
};

/**
 * Grid of skeleton cards
 * @param {number} count - Number of skeletons to show
 */
export const SkeletonGrid = ({ count = 6 }) => {
  return (
    <View style={styles.grid}>
      {Array.from({ length: count }).map((_, index) => (
        <View key={index} style={styles.gridItem}>
          <SkeletonCard />
        </View>
      ))}
    </View>
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

  imagePlaceholder: {
    width: '100%',
    aspectRatio: 1,
    backgroundColor: COLORS.gray200,
  },

  content: {
    padding: 12,
  },

  titleLine: {
    height: 14,
    backgroundColor: COLORS.gray200,
    borderRadius: 4,
    marginBottom: 8,
  },

  titleLineShort: {
    height: 14,
    width: '70%',
    backgroundColor: COLORS.gray200,
    borderRadius: 4,
    marginBottom: 12,
  },

  priceLine: {
    height: 20,
    width: '50%',
    backgroundColor: COLORS.gray200,
    borderRadius: 4,
    marginBottom: 12,
  },

  footer: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },

  badgePlaceholder: {
    height: 24,
    width: 70,
    backgroundColor: COLORS.gray200,
    borderRadius: 12,
  },

  heartPlaceholder: {
    height: 24,
    width: 24,
    backgroundColor: COLORS.gray200,
    borderRadius: 12,
  },

  // Grid styles
  grid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    padding: 8,
  },

  gridItem: {
    width: '50%',
    padding: 8,
  },
});

export default SkeletonCard;