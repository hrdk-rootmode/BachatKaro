// ============================================
// DEALHUNT APP - PRICE CHANGE INDICATOR
// Part 3: Watchlist & Price Alerts
// ============================================

import React, { memo } from 'react';
import {
  View,
  Text,
  StyleSheet,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { COLORS, FONTS } from '../utils/constants';

// --------------------------------------------
// PRICE CHANGE INDICATOR COMPONENT
// --------------------------------------------

/**
 * Displays price change with direction arrow and color coding
 * 
 * @param {Object} props
 * @param {number} props.priceChange - Absolute price change (e.g., -500 or 200)
 * @param {number} props.percentageChange - Percentage change (e.g., -3.8 or 1.5)
 * @param {string} props.sinceDate - Date string when tracking started
 * @param {string} props.size - 'small' | 'medium' | 'large'
 * @param {boolean} props.showAmount - Whether to show absolute amount
 * @param {boolean} props.showPercentage - Whether to show percentage
 * @param {boolean} props.showDate - Whether to show "since" date
 * @param {boolean} props.compact - Compact mode for tight spaces
 * @param {Object} props.style - Additional container styles
 */
const PriceChangeIndicator = ({
  priceChange = 0,
  percentageChange = 0,
  sinceDate = null,
  size = 'medium',
  showAmount = true,
  showPercentage = true,
  showDate = false,
  compact = false,
  style = {},
}) => {
  // Determine direction
  const direction = priceChange < 0 ? 'down' : priceChange > 0 ? 'up' : 'same';
  
  // Get styling based on direction
  const getDirectionStyle = () => {
    switch (direction) {
      case 'down':
        return {
          color: COLORS.success || '#10B981',
          backgroundColor: (COLORS.success || '#10B981') + '15',
          icon: 'arrow-down',
          prefix: '↓',
        };
      case 'up':
        return {
          color: COLORS.error || '#EF4444',
          backgroundColor: (COLORS.error || '#EF4444') + '15',
          icon: 'arrow-up',
          prefix: '↑',
        };
      default:
        return {
          color: COLORS.textSecondary || '#6B7280',
          backgroundColor: (COLORS.textSecondary || '#6B7280') + '15',
          icon: 'remove',
          prefix: '→',
        };
    }
  };
  
  const directionStyle = getDirectionStyle();
  
  // Get size-based styling
  const getSizeStyle = () => {
    switch (size) {
      case 'small':
        return {
          fontSize: 10,
          iconSize: 10,
          padding: 2,
          paddingHorizontal: 4,
        };
      case 'large':
        return {
          fontSize: 14,
          iconSize: 14,
          padding: 6,
          paddingHorizontal: 10,
        };
      default: // medium
        return {
          fontSize: 12,
          iconSize: 12,
          padding: 4,
          paddingHorizontal: 8,
        };
    }
  };
  
  const sizeStyle = getSizeStyle();
  
  // Format price change
  const formatPriceChange = (value) => {
    const absValue = Math.abs(value);
    if (absValue >= 100000) {
      return `₹${(absValue / 100000).toFixed(1)}L`;
    } else if (absValue >= 1000) {
      return `₹${(absValue / 1000).toFixed(1)}K`;
    }
    return `₹${absValue.toLocaleString('en-IN')}`;
  };
  
  // Format percentage
  const formatPercentage = (value) => {
    const absValue = Math.abs(value);
    return `${absValue.toFixed(1)}%`;
  };
  
  // Format date
  const formatDate = (dateString) => {
    if (!dateString) return '';
    
    try {
      const date = new Date(dateString);
      const now = new Date();
      const diffDays = Math.floor((now - date) / (1000 * 60 * 60 * 24));
      
      if (diffDays === 0) return 'today';
      if (diffDays === 1) return 'yesterday';
      if (diffDays < 7) return `${diffDays}d ago`;
      if (diffDays < 30) return `${Math.floor(diffDays / 7)}w ago`;
      
      return date.toLocaleDateString('en-IN', { 
        day: 'numeric', 
        month: 'short' 
      });
    } catch {
      return '';
    }
  };
  
  // Build display text
  const buildDisplayText = () => {
    const parts = [];
    
    if (direction === 'same') {
      return 'Same price';
    }
    
    if (showAmount && priceChange !== 0) {
      parts.push(formatPriceChange(priceChange));
    }
    
    if (showPercentage && percentageChange !== 0) {
      parts.push(`(${formatPercentage(percentageChange)})`);
    }
    
    return parts.join(' ');
  };
  
  const displayText = buildDisplayText();
  const formattedDate = showDate ? formatDate(sinceDate) : '';
  
  // Compact mode - just icon and percentage
  if (compact) {
    return (
      <View style={[styles.compactContainer, style]}>
        <Text style={[styles.compactText, { color: directionStyle.color }]}>
          {directionStyle.prefix}
          {showPercentage && percentageChange !== 0 
            ? ` ${formatPercentage(percentageChange)}`
            : direction === 'same' ? ' Same' : ''
          }
        </Text>
      </View>
    );
  }
  
  return (
    <View style={[styles.container, style]}>
      <View
        style={[
          styles.badge,
          {
            backgroundColor: directionStyle.backgroundColor,
            paddingVertical: sizeStyle.padding,
            paddingHorizontal: sizeStyle.paddingHorizontal,
          },
        ]}
      >
        <Ionicons
          name={directionStyle.icon}
          size={sizeStyle.iconSize}
          color={directionStyle.color}
          style={styles.icon}
        />
        <Text
          style={[
            styles.text,
            {
              color: directionStyle.color,
              fontSize: sizeStyle.fontSize,
            },
          ]}
          numberOfLines={1}
        >
          {displayText}
        </Text>
      </View>
      
      {showDate && formattedDate ? (
        <Text style={[styles.dateText, { fontSize: sizeStyle.fontSize - 2 }]}>
          since {formattedDate}
        </Text>
      ) : null}
    </View>
  );
};

// --------------------------------------------
// QUICK VARIANTS
// --------------------------------------------

/**
 * Small inline price change indicator
 */
export const PriceChangeSmall = memo((props) => (
  <PriceChangeIndicator {...props} size="small" showDate={false} />
));

/**
 * Compact badge for cards
 */
export const PriceChangeBadge = memo((props) => (
  <PriceChangeIndicator {...props} size="small" compact showDate={false} />
));

/**
 * Full price change with date
 */
export const PriceChangeFull = memo((props) => (
  <PriceChangeIndicator {...props} size="medium" showDate />
));

// --------------------------------------------
// STYLES
// --------------------------------------------

const styles = StyleSheet.create({
  container: {
    flexDirection: 'column',
    alignItems: 'flex-start',
  },
  
  badge: {
    flexDirection: 'row',
    alignItems: 'center',
    borderRadius: 4,
  },
  
  icon: {
    marginRight: 2,
  },
  
  text: {
    fontFamily: FONTS?.medium || 'System',
    fontWeight: '500',
  },
  
  dateText: {
    color: COLORS?.textSecondary || '#6B7280',
    fontFamily: FONTS?.regular || 'System',
    marginTop: 2,
  },
  
  compactContainer: {
    flexDirection: 'row',
    alignItems: 'center',
  },
  
  compactText: {
    fontSize: 11,
    fontFamily: FONTS?.medium || 'System',
    fontWeight: '500',
  },
});

// --------------------------------------------
// EXPORTS
// --------------------------------------------

export default memo(PriceChangeIndicator);