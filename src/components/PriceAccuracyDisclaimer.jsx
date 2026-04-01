import React from 'react';
import { View, Text, StyleSheet } from 'react-native';
import Ionicons from '@expo/vector-icons/Ionicons';
import { COLORS } from '../utils/constants';

const PriceAccuracyDisclaimer = ({ lastUpdatedAt, freshness_status }) => {
  if (!lastUpdatedAt) return null;

  const getHoursAgo = () => {
    const updateTime = new Date(lastUpdatedAt);
    const now = new Date();
    const diffHours = Math.floor((now - updateTime) / (1000 * 60 * 60));
    
    if (diffHours === 0) return 'Just now';
    if (diffHours === 1) return '1 hour ago';
    return `${diffHours} hours ago`;
  };

  const getFreshnessColor = () => {
    switch (freshness_status) {
      case 'fresh':
        return '#4CAF50'; // Green
      case 'stale':
        return '#FF9800'; // Orange
      case 'very_stale':
        return '#F44336'; // Red
      default:
        return COLORS.gray;
    }
  };

  const getFreshnessLabel = () => {
    switch (freshness_status) {
      case 'fresh':
        return 'Current Price';
      case 'stale':
        return 'Price may have changed';
      case 'very_stale':
        return 'Price likely outdated';
      default:
        return 'Price Status Unknown';
    }
  };

  return (
    <View style={styles.container}>
      <View style={styles.disclaimerBox}>
        <View style={styles.header}>
          <Ionicons
            name="information-circle"
            size={18}
            color={getFreshnessColor()}
            style={styles.icon}
          />
          <Text style={[styles.freshnessLabel, { color: getFreshnessColor() }]}>
            {getFreshnessLabel()}
          </Text>
        </View>
        
        <Text style={styles.disclaimerText}>
          Prices updated {getHoursAgo()}
        </Text>
        
        <Text style={styles.warningText}>
          💡 Prices may differ on the actual website. Please verify before purchase.
        </Text>
        
        <Text style={styles.currencyNote}>
          All prices are in Indian Rupees (INR) as per platform at time of update.
        </Text>
      </View>
    </View>
  );
};

const styles = StyleSheet.create({
  container: {
    marginVertical: 12,
    paddingHorizontal: 16,
  },
  disclaimerBox: {
    backgroundColor: '#F5F5F5',
    borderLeftWidth: 4,
    borderLeftColor: COLORS.primary,
    borderRadius: 8,
    padding: 12,
  },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    marginBottom: 8,
  },
  icon: {
    marginRight: 8,
  },
  freshnessLabel: {
    fontSize: 13,
    fontWeight: '600',
  },
  disclaimerText: {
    fontSize: 12,
    color: COLORS.darkGray,
    marginBottom: 6,
    lineHeight: 16,
  },
  warningText: {
    fontSize: 12,
    color: COLORS.darkGray,
    marginBottom: 6,
    lineHeight: 16,
  },
  currencyNote: {
    fontSize: 11,
    color: COLORS.gray,
    fontStyle: 'italic',
    lineHeight: 15,
  },
});

export default PriceAccuracyDisclaimer;
