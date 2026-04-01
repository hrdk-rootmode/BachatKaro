import React from 'react';
import { View, Text, StyleSheet } from 'react-native';
import Ionicons from '@expo/vector-icons/Ionicons';
import { COLORS } from '../utils/constants';

const FreshnessIndicator = ({ freshness_status, lastUpdatedAt }) => {
  const getIndicatorStyle = () => {
    switch (freshness_status) {
      case 'fresh':
        return {
          color: '#4CAF50',
          label: '● Fresh',
          description: 'Updated within 2 hours',
        };
      case 'stale':
        return {
          color: '#FF9800',
          label: '● Stale',
          description: 'Updated 2-12 hours ago',
        };
      case 'very_stale':
        return {
          color: '#F44336',
          label: '● Outdated',
          description: 'Updated more than 12 hours ago',
        };
      default:
        return {
          color: COLORS.gray,
          label: '● Unknown',
          description: 'Status unknown',
        };
    }
  };

  const getTimeSinceUpdate = () => {
    if (!lastUpdatedAt) return 'Time unknown';

    const updateTime = new Date(lastUpdatedAt);
    const now = new Date();
    const diffMs = now - updateTime;
    const diffMinutes = Math.floor(diffMs / 60000);
    const diffHours = Math.floor(diffMs / 3600000);
    const diffDays = Math.floor(diffMs / 86400000);

    if (diffMinutes < 60) return `${diffMinutes}m ago`;
    if (diffHours < 24) return `${diffHours}h ago`;
    return `${diffDays}d ago`;
  };

  const info = getIndicatorStyle();

  return (
    <View style={styles.container}>
      <View style={styles.indicatorRow}>
        <View style={[styles.dot, { backgroundColor: info.color }]} />
        <View style={styles.textContainer}>
          <Text style={[styles.label, { color: info.color }]}>
            {info.label}
          </Text>
          <Text style={styles.timeAgo}>{getTimeSinceUpdate()}</Text>
        </View>
      </View>
      <Text style={styles.description}>{info.description}</Text>
    </View>
  );
};

const styles = StyleSheet.create({
  container: {
    marginHorizontal: 16,
    marginVertical: 8,
    paddingHorizontal: 12,
    paddingVertical: 10,
    backgroundColor: 'rgba(0, 0, 0, 0.02)',
    borderRadius: 6,
  },
  indicatorRow: {
    flexDirection: 'row',
    alignItems: 'center',
    marginBottom: 4,
  },
  dot: {
    width: 10,
    height: 10,
    borderRadius: 5,
    marginRight: 8,
  },
  textContainer: {
    flex: 1,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  label: {
    fontSize: 13,
    fontWeight: '600',
  },
  timeAgo: {
    fontSize: 12,
    color: COLORS.gray,
    marginLeft: 8,
  },
  description: {
    fontSize: 11,
    color: COLORS.darkGray,
    marginLeft: 18,
    marginTop: 2,
    fontStyle: 'italic',
  },
});

export default FreshnessIndicator;
