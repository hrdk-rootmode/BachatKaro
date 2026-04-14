import React, { useEffect, useCallback, useMemo, useState } from 'react';
import {
  View,
  Text,
  StyleSheet,
  FlatList,
  TouchableOpacity,
  ActivityIndicator,
  RefreshControl,
  Dimensions,
  Image,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useFocusEffect, useNavigation } from '@react-navigation/native';
import { useDispatch, useSelector } from 'react-redux';
import { Ionicons } from '@expo/vector-icons';

import { COLORS, SIZES } from '../utils/constants';
import { selectThemePalette } from '../store/themeSlice';
import { notificationApi } from '../services/notificationApi';
import { selectUser, selectProTrialInfo } from '../store/authSlice';
import { selectWatchlistCount, selectWatchlistLimit } from '../store/watchlistSlice';
import {
  selectNotifications,
  setNotificationOwner,
  setNotificationsForUser,
  markNotificationReadLocal,
  markAllNotificationsReadLocal,
  deleteNotificationLocal,
} from '../store/notificationSlice';

const { width } = Dimensions.get('window');

// =============================================================================
// NOTIFICATIONS SCREEN
// =============================================================================

const NotificationsScreen = () => {
  const navigation = useNavigation();
  const dispatch = useDispatch();
  const themePalette = useSelector(selectThemePalette);
  const user = useSelector(selectUser);
  const proTrialInfo = useSelector(selectProTrialInfo);
  const watchlistCount = useSelector(selectWatchlistCount);
  const watchlistLimit = useSelector(selectWatchlistLimit);
  
  const notifications = useSelector(selectNotifications);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState(null);

  const currentUserId = useMemo(() => String(user?.id || user?.firebase_uid || ''), [user?.id, user?.firebase_uid]);

  const searchesToday = useMemo(
    () => Number(user?.searches_today ?? user?.usage_stats?.searches_today ?? 0),
    [user?.searches_today, user?.usage_stats?.searches_today]
  );

  const dailySearchLimit = useMemo(() => {
    const directLimit = Number(user?.daily_limit ?? user?.usage_stats?.daily_limit ?? NaN);
    if (Number.isFinite(directLimit) && directLimit !== 0) {
      return directLimit;
    }
    return -1;
  }, [user?.daily_limit, user?.usage_stats?.daily_limit]);

  const actionAlerts = useMemo(() => {
    const alerts = [];

    if (dailySearchLimit > 0 && searchesToday >= dailySearchLimit) {
      alerts.push({
        key: 'search-limit-reached',
        type: 'subscription_expiry',
        title: 'Daily search limit reached',
        message: 'Upgrade your plan or wait until tomorrow to continue searching.',
      });
    } else if (dailySearchLimit > 0 && searchesToday / dailySearchLimit >= 0.8) {
      const remaining = Math.max(0, dailySearchLimit - searchesToday);
      alerts.push({
        key: 'search-limit-near',
        type: 'streak_reminder',
        title: 'Search limit almost full',
        message: `${remaining} searches left for today.`,
      });
    }

    if (Number(watchlistLimit || 0) > 0 && Number(watchlistCount || 0) >= Number(watchlistLimit || 0)) {
      alerts.push({
        key: 'watchlist-full',
        type: 'subscription_expiry',
        title: 'Watchlist is full',
        message: 'Remove items or upgrade your plan to add more products.',
      });
    }

    if (proTrialInfo?.isActive && proTrialInfo?.expiresAt) {
      alerts.push({
        key: 'trial-live',
        type: 'streak_reminder',
        title: 'Pro trial is active',
        message: `Expires ${formatTime(proTrialInfo.expiresAt)}.`,
      });
    }

    return alerts;
  }, [dailySearchLimit, proTrialInfo?.expiresAt, proTrialInfo?.isActive, searchesToday, watchlistCount, watchlistLimit]);

  const mergedNotifications = useMemo(() => {
    const systemItems = actionAlerts.map((alert) => ({
      id: `system-${alert.key}`,
      type: alert.type,
      title: alert.title,
      message: alert.message,
      data: {},
      is_read: true,
      created_at: new Date().toISOString(),
      is_system: true,
    }));

    // Filter price-related notifications to only show those with actual price changes
    const filteredNotifications = notifications.filter(notif => {
      // Keep system alerts and non-price notifications
      if (notif.is_system || notif.type !== 'price_drop') {
        return true;
      }

      // For price notifications, check if there's an actual price change
      const notifData = notif.data || {};
      const currentPrice = notifData.price;
      const previousPrice = notifData.previous_price;

      // Only show if we have both prices and they're different
      if (typeof currentPrice === 'number' && typeof previousPrice === 'number') {
        return Math.abs(currentPrice - previousPrice) > 0.01;
      }

      // If we don't have previous price, show the notification (new price alert)
      return true;
    });

    return [...systemItems, ...filteredNotifications];
  }, [actionAlerts, notifications]);

  // Fetch notifications on mount
  useEffect(() => {
    dispatch(setNotificationOwner(currentUserId || null));
    loadNotifications();
  }, [currentUserId]);

  // Fetch notifications on screen focus
  useFocusEffect(
    useCallback(() => {
      loadNotifications();
    }, [])
  );

  const loadNotifications = async () => {
    try {
      setLoading(true);
      setError(null);
      
      const response = await notificationApi.getNotifications(20, 0);
      
      if (response?.success && response?.data) {
        dispatch(
          setNotificationsForUser({
            userId: currentUserId || null,
            notifications: response.data,
          })
        );
      } else {
        console.warn('❌ Failed to load notifications:', response?.error);
        dispatch(
          setNotificationsForUser({
            userId: currentUserId || null,
            notifications: [],
          })
        );
      }
    } catch (err) {
      console.error('❌ Error loading notifications:', err);
      setError('Failed to load notifications');
    } finally {
      setLoading(false);
    }
  };

  const onRefresh = async () => {
    setRefreshing(true);
    await loadNotifications();
    setRefreshing(false);
  };

  const handleMarkAsRead = async (notificationId) => {
    try {
      const response = await notificationApi.markAsRead(notificationId);
      
      if (response?.success) {
        dispatch(markNotificationReadLocal(notificationId));
      }
    } catch (err) {
      console.error('❌ Error marking as read:', err);
    }
  };

  const handleMarkAllAsRead = async () => {
    try {
      const response = await notificationApi.markAllAsRead();
      
      if (response?.success) {
        dispatch(markAllNotificationsReadLocal());
      }
    } catch (err) {
      console.error('❌ Error marking all as read:', err);
    }
  };

  const handleDeleteNotification = async (notificationId) => {
    try {
      const response = await notificationApi.deleteNotification(notificationId);
      
      if (response?.success) {
        dispatch(deleteNotificationLocal(notificationId));
      }
    } catch (err) {
      console.error('❌ Error deleting notification:', err);
    }
  };

  const navigateToProduct = (notificationData) => {
    if (notificationData?.product_id) {
      navigation.navigate('ProductDetail', {
        productId: notificationData.product_id,
      });
    }
  };

  const renderNotificationIcon = (type) => {
    switch (type) {
      case 'price_drop':
        return <Ionicons name="arrow-down-circle" size={32} color="#22c55e" />;
      case 'back_in_stock':
        return <Ionicons name="checkmark-circle" size={32} color="#3b82f6" />;
      case 'streak_reminder':
        return <Ionicons name="flame" size={32} color="#f97316" />;
      case 'subscription_expiry':
        return <Ionicons name="warning" size={32} color="#ef4444" />;
      default:
        return <Ionicons name="notifications" size={32} color="#8b5cf6" />;
    }
  };

  const renderNotificationItem = ({ item }) => {
    const isUnread = !item.is_read;
    const notifData = item.data || {};
    const isSystemAlert = Boolean(item.is_system);
    const productTitle = notifData.product_title || notifData.title;
    const productImageUrl = notifData.product_image_url;
    const hasPrice = typeof notifData.price === 'number';
    const hasTarget = typeof notifData.target_price === 'number';
    const showWatchlistMeta = !isSystemAlert && (item.type === 'price_drop' || item.type === 'back_in_stock');

    // Determine price change direction for background color
    const currentPrice = notifData.price;
    const previousPrice = notifData.previous_price;
    let priceChangeType = null;
    let cardBackgroundColor = isUnread ? themePalette.accent || '#f3f4f6' : themePalette.surface || '#ffffff';
    
    if (!isSystemAlert && item.type === 'price_drop' && typeof currentPrice === 'number' && typeof previousPrice === 'number') {
      if (currentPrice < previousPrice) {
        priceChangeType = 'drop';
        cardBackgroundColor = isUnread ? '#dcfce7' : '#f0fdf4'; // Green background
      } else if (currentPrice > previousPrice) {
        priceChangeType = 'rise';
        cardBackgroundColor = isUnread ? '#fee2e2' : '#fef2f2'; // Red background
      }
    }

    const watchlistMeta = showWatchlistMeta
      ? [
          productTitle ? `Product: ${productTitle}` : null,
          hasPrice ? `Now: INR ${formatPrice(notifData.price)}` : null,
          hasTarget ? `Target: INR ${formatPrice(notifData.target_price)}` : null,
          previousPrice ? `Previous: INR ${formatPrice(previousPrice)}` : null,
        ]
          .filter(Boolean)
          .join(' • ')
      : '';

    return (
      <TouchableOpacity
        style={[
          styles.notificationCard,
          {
            backgroundColor: cardBackgroundColor,
            borderLeftColor: isUnread ? '#3b82f6' : 'transparent',
          },
        ]}
        onPress={() => {
          if (!isSystemAlert) {
            navigateToProduct(notifData);
          }
        }}
        activeOpacity={0.7}
      >
        <View style={styles.notificationContent}>
          <View style={styles.thumbnailContainer}>
            {productImageUrl ? (
              <Image
                source={{ uri: productImageUrl }}
                style={styles.productImage}
                resizeMode="cover"
              />
            ) : (
              <View style={styles.iconContainer}>
                {renderNotificationIcon(item.type)}
              </View>
            )}
            {isUnread && <View style={styles.unreadDot} />}
          </View>

          <View style={styles.textContainer}>
            <Text
              style={[
                styles.title,
                {
                  color: themePalette.text || COLORS.textPrimary,
                  fontWeight: isUnread ? '700' : '600',
                },
              ]}
              numberOfLines={2}
            >
              {item.title}
            </Text>

            <Text
              style={[
                styles.message,
                {
                  color: themePalette.textSecondary || COLORS.textSecondary,
                },
              ]}
              numberOfLines={2}
            >
              {item.message}
            </Text>

            {!!watchlistMeta && (
              <Text
                style={[
                  styles.meta,
                  {
                    color: themePalette.textSecondary || COLORS.textSecondary,
                  },
                ]}
                numberOfLines={2}
              >
                {watchlistMeta}
              </Text>
            )}

            <Text
              style={[
                styles.timestamp,
                {
                  color: themePalette.textTertiary || COLORS.textTertiary,
                },
              ]}
            >
              {formatTime(item.created_at)}
            </Text>
          </View>

          <View style={styles.actions}>
            {!item.is_read && !isSystemAlert && (
              <TouchableOpacity
                style={styles.actionBtn}
                onPress={() => handleMarkAsRead(item.id)}
              >
                <Ionicons name="checkmark" size={18} color="#3b82f6" />
              </TouchableOpacity>
            )}
            
            {!isSystemAlert && (
              <TouchableOpacity
                style={styles.actionBtn}
                onPress={() => handleDeleteNotification(item.id)}
              >
                <Ionicons name="close" size={18} color="#ef4444" />
              </TouchableOpacity>
            )}
          </View>
        </View>
      </TouchableOpacity>
    );
  };

  const renderEmptyState = () => {
    return (
      <View style={styles.emptyContainer}>
        <Ionicons
          name="notifications-off-outline"
          size={64}
          color={themePalette.textTertiary || COLORS.textTertiary}
          style={{ marginBottom: 16 }}
        />
        <Text
          style={[
            styles.emptyTitle,
            { color: themePalette.text || COLORS.textPrimary },
          ]}
        >
          No notifications yet
        </Text>
        <Text
          style={[
            styles.emptyMessage,
            { color: themePalette.textSecondary || COLORS.textSecondary },
          ]}
        >
          You'll get notified when your watchlist items have price drops or back in stock
        </Text>
      </View>
    );
  };

  const renderHeader = () => {
    const unreadCount = notifications.filter(n => !n.is_read).length;

    return (
      <View
        style={[
          styles.header,
          { backgroundColor: themePalette.surface || '#ffffff' },
        ]}
      >
        <TouchableOpacity
          onPress={() => navigation.goBack()}
          style={styles.backBtn}
        >
          <Ionicons
            name="chevron-back"
            size={24}
            color={themePalette.text || COLORS.textPrimary}
          />
        </TouchableOpacity>

        <Text
          style={[
            styles.headerTitle,
            { color: themePalette.text || COLORS.textPrimary },
          ]}
        >
          Notifications
          {unreadCount > 0 && (
            <Text style={styles.unreadBadge}> ({unreadCount})</Text>
          )}
        </Text>

        {unreadCount > 0 && (
          <TouchableOpacity
            onPress={handleMarkAllAsRead}
            style={styles.markAllBtn}
          >
            <Text
              style={[
                styles.markAllText,
                { color: themePalette.accent || '#3b82f6' },
              ]}
            >
              Mark all read
            </Text>
          </TouchableOpacity>
        )}
      </View>
    );
  };

  if (loading && !refreshing) {
    return (
      <SafeAreaView
        style={[
          styles.container,
          { backgroundColor: themePalette.background || COLORS.background },
        ]}
      >
        {renderHeader()}
        <View style={styles.loadingContainer}>
          <ActivityIndicator size="large" color={themePalette.accent || '#3b82f6'} />
        </View>
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView
      style={[
        styles.container,
        { backgroundColor: themePalette.background || COLORS.background },
      ]}
    >
      {renderHeader()}

      {error && (
        <View
          style={[
            styles.errorBanner,
            { backgroundColor: '#fee2e2' },
          ]}
        >
          <Ionicons name="alert-circle" size={18} color="#dc2626" />
          <Text style={styles.errorText}>{error}</Text>
        </View>
      )}

      <FlatList
        data={mergedNotifications}
        renderItem={renderNotificationItem}
        keyExtractor={item => String(item.id)}
        ListEmptyComponent={renderEmptyState}
        refreshControl={
          <RefreshControl
            refreshing={refreshing}
            onRefresh={onRefresh}
            tintColor={themePalette.accent || '#3b82f6'}
          />
        }
        contentContainerStyle={styles.listContent}
      />
    </SafeAreaView>
  );
};

// =============================================================================
// HELPER FUNCTIONS
// =============================================================================

const formatTime = (dateString) => {
  if (!dateString) return '';

  const date = new Date(dateString);
  const now = new Date();
  const diffMs = now - date;
  const diffMins = Math.floor(diffMs / 60000);
  const diffHours = Math.floor(diffMs / 3600000);
  const diffDays = Math.floor(diffMs / 86400000);

  if (diffMins < 1) return 'just now';
  if (diffMins < 60) return `${diffMins}m ago`;
  if (diffHours < 24) return `${diffHours}h ago`;
  if (diffDays < 7) return `${diffDays}d ago`;

  return date.toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    year: date.getFullYear() !== now.getFullYear() ? 'numeric' : undefined,
  });
};

const formatPrice = (value) => {
  const price = Number(value);
  if (!Number.isFinite(price)) return '--';
  return Math.round(price).toLocaleString('en-IN');
};

// =============================================================================
// STYLES
// =============================================================================

const styles = StyleSheet.create({
  container: {
    flex: 1,
  },

  header: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 16,
    paddingVertical: 12,
    borderBottomWidth: 1,
    borderBottomColor: '#e5e7eb',
  },

  backBtn: {
    padding: 8,
    marginRight: 8,
  },

  headerTitle: {
    fontSize: 18,
    fontWeight: '700',
    flex: 1,
  },

  unreadBadge: {
    fontSize: 14,
    fontWeight: '600',
    color: '#ef4444',
  },

  markAllBtn: {
    paddingHorizontal: 12,
    paddingVertical: 6,
  },

  markAllText: {
    fontSize: 12,
    fontWeight: '600',
  },

  loadingContainer: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
  },

  errorBanner: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 12,
    paddingVertical: 10,
    marginHorizontal: 12,
    marginTop: 8,
    borderRadius: 8,
    gap: 8,
  },

  errorText: {
    fontSize: 13,
    color: '#dc2626',
    flex: 1,
  },

  listContent: {
    paddingHorizontal: 8,
    paddingTop: 8,
    paddingBottom: 16,
    flexGrow: 1,
  },

  notificationCard: {
    marginHorizontal: 8,
    marginVertical: 6,
    borderRadius: 12,
    borderLeftWidth: 4,
    overflow: 'hidden',
    elevation: 2,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.1,
    shadowRadius: 4,
  },

  notificationContent: {
    flexDirection: 'row',
    padding: 12,
    alignItems: 'flex-start',
    gap: 12,
  },

  thumbnailContainer: {
    position: 'relative',
    width: 60,
    height: 60,
    alignItems: 'center',
    justifyContent: 'center',
  },

  productImage: {
    width: 60,
    height: 60,
    borderRadius: 8,
    backgroundColor: '#f3f4f6',
  },

  iconContainer: {
    position: 'relative',
  },

  unreadDot: {
    position: 'absolute',
    top: -4,
    right: -4,
    width: 12,
    height: 12,
    borderRadius: 6,
    backgroundColor: '#3b82f6',
    borderWidth: 2,
    borderColor: '#ffffff',
  },

  textContainer: {
    flex: 1,
    gap: 4,
  },

  title: {
    fontSize: 14,
    lineHeight: 20,
  },

  message: {
    fontSize: 12,
    lineHeight: 16,
  },

  meta: {
    fontSize: 11,
    lineHeight: 15,
  },

  timestamp: {
    fontSize: 11,
    marginTop: 2,
  },

  actions: {
    flexDirection: 'row',
    gap: 8,
    alignItems: 'center',
  },

  actionBtn: {
    padding: 6,
    borderRadius: 6,
    backgroundColor: '#f3f4f6',
  },

  emptyContainer: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    paddingHorizontal: 24,
  },

  emptyTitle: {
    fontSize: 16,
    fontWeight: '600',
    marginBottom: 8,
    textAlign: 'center',
  },

  emptyMessage: {
    fontSize: 13,
    textAlign: 'center',
    lineHeight: 18,
  },
});

export default NotificationsScreen;
