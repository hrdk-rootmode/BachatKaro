// ============================================
// DEALHUNT APP - PRICE HISTORY CHART
// ============================================

import React, { memo, useMemo } from 'react';
import {
  View,
  Text,
  StyleSheet,
  Dimensions,
  ActivityIndicator,
} from 'react-native';
import {
  VictoryChart,
  VictoryLine,
  VictoryArea,
  VictoryAxis,
  VictoryScatter,
  VictoryTheme,
  VictoryVoronoiContainer,
  VictoryTooltip,
} from 'victory-native';

import { COLORS } from '../utils/constants';
import {
  formatPrice,
  parsePrice,
  formatShortDate,
} from '../utils/formatters';

const SCREEN_WIDTH = Dimensions.get('window').width;
const CHART_HEIGHT = 220;
const CHART_PADDING = { top: 20, bottom: 40, left: 50, right: 20 };

/**
 * Price history chart component
 * Uses Victory Native for rendering
 * 
 * @param {Object} priceHistory - Price history data from API
 * @param {boolean} isLoading - Loading state
 * @param {string} platform - Current platform name
 */
const PriceChart = ({ priceHistory, isLoading, platform }) => {
  const history = priceHistory?.history || [];

  // Process chart data
  const chartData = useMemo(() => {
    // ✅ CRITICAL: Backend sends .history array with { date, price } objects
    if (!history || history.length === 0) {
      return null;
    }

    // Convert to Victory format
    const data = history.map((point, index) => ({
      x: index,
      y: parsePrice(point.price),
      date: point.date,
      label: `${formatShortDate(point.date)}\n${formatPrice(point.price)}`,
    }));

    // Calculate stats
    const prices = data.map(d => d.y);
    const minPrice = Math.min(...prices);
    const maxPrice = Math.max(...prices);
    const avgPrice = prices.reduce((a, b) => a + b, 0) / prices.length;

    // Find min/max indices
    const minIndex = prices.indexOf(minPrice);
    const maxIndex = prices.indexOf(maxPrice);

    // Domain padding
    const pricePadding = (maxPrice - minPrice) * 0.15 || 1000;

    return {
      data,
      minPrice,
      maxPrice,
      avgPrice,
      minIndex,
      maxIndex,
      domain: {
        x: [0, data.length - 1],
        y: [minPrice - pricePadding, maxPrice + pricePadding],
      },
      // X-axis tick values (show ~5 dates)
      xTicks: data
        .filter((_, i) => i % Math.ceil(data.length / 5) === 0 || i === data.length - 1)
        .map(d => d.x),
    };
  }, [history]);

  // Loading state
  if (isLoading) {
    return (
      <View style={styles.container}>
        <View style={styles.header}>
          <Text style={styles.headerTitle}>📈 Price History</Text>
        </View>
        <View style={styles.loadingContainer}>
          <ActivityIndicator size="large" color={COLORS.primary} />
          <Text style={styles.loadingText}>Loading price history...</Text>
        </View>
      </View>
    );
  }

  // No data state
if (!chartData) {
  return (
    <View style={styles.container}>
      <View style={styles.header}>
        <Text style={styles.headerTitle}>📈 Price History</Text>
      </View>
      <View style={styles.emptyContainer}>
        <Text style={styles.emptyEmoji}>📊</Text>
        <Text style={styles.emptyTitle}>No History Available</Text>
        <Text style={styles.emptyText}>
          Price history will appear once we start tracking this product.
        </Text>
      </View>
    </View>
  );
}

// ✅ NEW: Single-point history fallback (Item 1: fallback rendering)
if (history.length === 1) {
  const point = history[0];
  return (
    <View style={styles.container}>
      <View style={styles.header}>
        <Text style={styles.headerTitle}>📈 Price History</Text>
        <Text style={styles.headerSubtitle}>
          🆕 First data point • {platform || 'Best Price'}
        </Text>
      </View>
      <View style={[styles.chartWrapper, styles.singlePointWrapper]}>
        <View style={styles.horizontalLine} />
        <View style={styles.singlePointInfo}>
          <Text style={styles.singlePointLabel}>Current Price</Text>
          <Text style={styles.singlePointPrice}>{formatPrice(parsePrice(point.price))}</Text>
          <Text style={styles.singlePointDate}>
            {formatShortDate(point.date)}
          </Text>
        </View>
      </View>
      {/* Item 2: Clear tracking started message */}
      <View style={styles.trackingMessage}>
        <Text style={styles.trackingText}>
          🆕 Tracking started. Chart will appear with more data points.
        </Text>
      </View>
    </View>
  );
}

  return (
    <View style={styles.container}>
      {/* Header */}
      <View style={styles.header}>
        <Text style={styles.headerTitle}>📈 Price History</Text>
        <Text style={styles.headerSubtitle}>
          Last {chartData.data.length} days • {platform || 'Best Price'}
        </Text>
      </View>

      {/* Chart */}
      <View style={styles.chartWrapper}>
        <VictoryChart
          width={SCREEN_WIDTH - 32}
          height={CHART_HEIGHT}
          padding={CHART_PADDING}
          domain={chartData.domain}
          containerComponent={
            <VictoryVoronoiContainer
              voronoiDimension="x"
              labels={({ datum }) => datum.label}
              labelComponent={
                <VictoryTooltip
                  flyoutStyle={styles.tooltipFlyout}
                  style={styles.tooltipText}
                  cornerRadius={8}
                  flyoutPadding={{ top: 8, bottom: 8, left: 12, right: 12 }}
                />
              }
            />
          }
        >
          {/* X Axis */}
          <VictoryAxis
            tickValues={chartData.xTicks}
            tickFormat={(t) => {
              const point = chartData.data[t];
              return point ? formatShortDate(point.date) : '';
            }}
            style={{
              axis: { stroke: COLORS.gray200 },
              tickLabels: {
                fontSize: 10,
                fill: COLORS.textSecondary,
                angle: 0,
              },
              grid: { stroke: 'transparent' },
            }}
          />

          {/* Y Axis */}
          <VictoryAxis
            dependentAxis
            tickFormat={(t) => `₹${(t / 1000).toFixed(0)}k`}
            style={{
              axis: { stroke: COLORS.gray200 },
              tickLabels: {
                fontSize: 10,
                fill: COLORS.textSecondary,
              },
              grid: {
                stroke: COLORS.gray100,
                strokeDasharray: '5,5',
              },
            }}
          />

          {/* Area Fill */}
          <VictoryArea
            data={chartData.data}
            style={{
              data: {
                fill: COLORS.primary + '20',
                stroke: 'transparent',
              },
            }}
            interpolation="monotoneX"
          />

          {/* Line */}
          <VictoryLine
            data={chartData.data}
            style={{
              data: {
                stroke: COLORS.primary,
                strokeWidth: 2.5,
              },
            }}
            interpolation="monotoneX"
          />

          {/* Data Points */}
          <VictoryScatter
            data={chartData.data}
            size={3}
            style={{
              data: {
                fill: COLORS.primary,
              },
            }}
          />

          {/* Min Point Marker */}
          <VictoryScatter
            data={[chartData.data[chartData.minIndex]]}
            size={6}
            style={{
              data: {
                fill: COLORS.success,
                stroke: COLORS.white,
                strokeWidth: 2,
              },
            }}
          />

          {/* Max Point Marker */}
          <VictoryScatter
            data={[chartData.data[chartData.maxIndex]]}
            size={6}
            style={{
              data: {
                fill: COLORS.error,
                stroke: COLORS.white,
                strokeWidth: 2,
              },
            }}
          />
        </VictoryChart>
      </View>

      {/* Stats Row */}
      <View style={styles.statsContainer}>
        {/* Lowest Price */}
        <View style={styles.statItem}>
          <View style={[styles.statIndicator, { backgroundColor: COLORS.success }]} />
          <View>
            <Text style={styles.statLabel}>Lowest</Text>
            <Text style={[styles.statValue, { color: COLORS.success }]}>
              {formatPrice(chartData.minPrice)}
            </Text>
            <Text style={styles.statDate}>
              {formatShortDate(chartData.data[chartData.minIndex]?.date)}
            </Text>
          </View>
        </View>

        {/* Average Price */}
        <View style={styles.statItem}>
          <View style={[styles.statIndicator, { backgroundColor: COLORS.primary }]} />
          <View>
            <Text style={styles.statLabel}>Average</Text>
            <Text style={[styles.statValue, { color: COLORS.primary }]}>
              {formatPrice(chartData.avgPrice)}
            </Text>
            <Text style={styles.statDate}>Last {chartData.data.length} days</Text>
          </View>
        </View>

        {/* Highest Price */}
        <View style={styles.statItem}>
          <View style={[styles.statIndicator, { backgroundColor: COLORS.error }]} />
          <View>
            <Text style={styles.statLabel}>Highest</Text>
            <Text style={[styles.statValue, { color: COLORS.error }]}>
              {formatPrice(chartData.maxPrice)}
            </Text>
            <Text style={styles.statDate}>
              {formatShortDate(chartData.data[chartData.maxIndex]?.date)}
            </Text>
          </View>
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
  },

  header: {
    paddingHorizontal: 16,
    paddingVertical: 14,
    borderBottomWidth: 1,
    borderBottomColor: COLORS.gray100,
  },

  headerTitle: {
    fontSize: 16,
    fontWeight: '700',
    color: COLORS.textPrimary,
  },

  headerSubtitle: {
    fontSize: 12,
    color: COLORS.textSecondary,
    marginTop: 2,
  },

  chartWrapper: {
    alignItems: 'center',
    paddingTop: 8,
  },

  tooltipFlyout: {
    fill: COLORS.gray800,
    stroke: COLORS.gray800,
  },

  tooltipText: {
    fill: COLORS.white,
    fontSize: 11,
    fontWeight: '600',
  },

  statsContainer: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    paddingHorizontal: 16,
    paddingVertical: 16,
    backgroundColor: COLORS.gray50,
    borderTopWidth: 1,
    borderTopColor: COLORS.gray100,
  },

  statItem: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    flex: 1,
  },

  statIndicator: {
    width: 4,
    height: 32,
    borderRadius: 2,
    marginRight: 10,
    marginTop: 2,
  },

  statLabel: {
    fontSize: 11,
    color: COLORS.textSecondary,
    marginBottom: 2,
  },

  statValue: {
    fontSize: 14,
    fontWeight: '700',
  },

  statDate: {
    fontSize: 10,
    color: COLORS.gray400,
    marginTop: 2,
  },

  loadingContainer: {
    height: 200,
    alignItems: 'center',
    justifyContent: 'center',
  },

  loadingText: {
    fontSize: 13,
    color: COLORS.textSecondary,
    marginTop: 12,
  },

  emptyContainer: {
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: 40,
    paddingHorizontal: 20,
  },

  emptyEmoji: {
    fontSize: 40,
    marginBottom: 12,
  },

  emptyTitle: {
    fontSize: 16,
    fontWeight: '600',
    color: COLORS.textPrimary,
    marginBottom: 6,
  },

  emptyText: {
    fontSize: 13,
    color: COLORS.textSecondary,
    textAlign: 'center',
    lineHeight: 18,
  },
});

export default memo(PriceChart);