// ============================================
// DEALHUNT APP - PLATFORM BADGE COMPONENT
// ============================================

import React, { memo } from 'react';
import {
  View,
  Text,
  StyleSheet,
} from 'react-native';

import { COLORS } from '../utils/constants';
import { getPlatformName, getPlatformColor } from '../utils/formatters';

// Platform configurations with icons
const PLATFORM_CONFIG = {
  amazon: {
    letter: 'A',
    fullName: 'Amazon',
    color: '#FF9900',
  },
  flipkart: {
    letter: 'F',
    fullName: 'Flipkart',
    color: '#2874F0',
  },
  meesho: {
    letter: 'M',
    fullName: 'Meesho',
    color: '#F43397',
  },
  croma: {
    letter: 'C',
    fullName: 'Croma',
    color: '#00A650',
  },
  reliance: {
    letter: 'R',
    fullName: 'Reliance Digital',
    color: '#E42529',
  },
  vijay: {
    letter: 'V',
    fullName: 'Vijay Sales',
    color: '#FF6B00',
  },
};

/**
 * Platform badge component
 * Shows platform logo/letter with optional name
 * 
 * @param {string} platform - Platform key (amazon, flipkart, etc.)
 * @param {string} size - 'small' | 'medium' | 'large'
 * @param {boolean} showName - Whether to show platform name
 * @param {boolean} showFullName - Show full name vs short name
 * @param {Object} style - Additional container styles
 */
const PlatformBadge = ({
  platform,
  size = 'medium',
  showName = true,
  showFullName = false,
  style,
}) => {
  const config = PLATFORM_CONFIG[platform?.toLowerCase()] || {
    letter: '?',
    fullName: platform || 'Unknown',
    color: COLORS.gray500,
  };

  // Size configurations
  const sizeConfig = {
    small: {
      container: 20,
      fontSize: 10,
      nameFontSize: 11,
    },
    medium: {
      container: 28,
      fontSize: 14,
      nameFontSize: 13,
    },
    large: {
      container: 36,
      fontSize: 18,
      nameFontSize: 15,
    },
  };

  const currentSize = sizeConfig[size] || sizeConfig.medium;

  return (
    <View style={[styles.container, style]}>
      {/* Platform Icon */}
      <View
        style={[
          styles.iconContainer,
          {
            width: currentSize.container,
            height: currentSize.container,
            borderRadius: currentSize.container / 2,
            backgroundColor: config.color,
          },
        ]}
      >
        <Text
          style={[
            styles.iconText,
            { fontSize: currentSize.fontSize },
          ]}
        >
          {config.letter}
        </Text>
      </View>

      {/* Platform Name */}
      {showName && (
        <Text
          style={[
            styles.nameText,
            {
              fontSize: currentSize.nameFontSize,
              color: config.color,
            },
          ]}
          numberOfLines={1}
        >
          {showFullName ? config.fullName : getPlatformName(platform)}
        </Text>
      )}
    </View>
  );
};

/**
 * Compact platform badge (just the icon)
 */
export const PlatformIcon = memo(({ platform, size = 'medium' }) => (
  <PlatformBadge platform={platform} size={size} showName={false} />
));

/**
 * Platform badge with background
 */
export const PlatformChip = memo(({ platform, size = 'small' }) => {
  const config = PLATFORM_CONFIG[platform?.toLowerCase()] || {
    color: COLORS.gray500,
  };

  return (
    <View
      style={[
        styles.chipContainer,
        { backgroundColor: config.color + '15' },
      ]}
    >
      <PlatformBadge platform={platform} size={size} showName={true} />
    </View>
  );
});

// --------------------------------------------
// STYLES
// --------------------------------------------

const styles = StyleSheet.create({
  container: {
    flexDirection: 'row',
    alignItems: 'center',
  },

  iconContainer: {
    alignItems: 'center',
    justifyContent: 'center',
  },

  iconText: {
    color: COLORS.white,
    fontWeight: '700',
  },

  nameText: {
    fontWeight: '600',
    marginLeft: 8,
  },

  chipContainer: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 10,
    paddingVertical: 6,
    borderRadius: 16,
  },
});

export default memo(PlatformBadge);