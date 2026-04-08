// ============================================
// DEALHUNT APP - UPGRADE PROMPT COMPONENT
// Part 5: Gentle Upgrade Banner
// ============================================

import React from 'react';
import {
  View,
  Text,
  StyleSheet,
  TouchableOpacity,
  Animated,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useNavigation } from '@react-navigation/native';
import { useDispatch, useSelector } from 'react-redux';
import { LinearGradient } from 'expo-linear-gradient';

import { COLORS, SUBSCRIPTION, APP } from '../utils/constants';
import { hideUpgradePrompt, setSelectedPlan, selectPlans, fetchPlans } from '../store/subscriptionSlice';
import { selectThemePalette } from '../store/themeSlice';

// --------------------------------------------
// UPGRADE PROMPT COMPONENT
// --------------------------------------------

/**
 * UpgradePrompt - A gentle, non-intrusive banner to encourage upgrades
 * 
 * @param {Object} props
 * @param {string} props.reason - Why the prompt is showing ('watchlist_limit' | 'search_limit')
 * @param {string} props.targetPlan - Which plan to highlight ('pro' | 'premium')
 * @param {boolean} props.dismissible - Whether user can dismiss the banner
 * @param {Function} props.onDismiss - Callback when dismissed
 * @param {string} props.variant - Visual variant ('banner' | 'card' | 'inline')
 */
const UpgradePrompt = ({
  reason = SUBSCRIPTION.UPGRADE_REASONS.WATCHLIST_LIMIT,
  targetPlan = 'pro',
  dismissible = true,
  onDismiss,
  variant = 'banner',
}) => {
  const navigation = useNavigation();
  const dispatch = useDispatch();
  const themePalette = useSelector(selectThemePalette);
  const plans = useSelector(selectPlans);
  const fadeAnim = React.useRef(new Animated.Value(0)).current;

  const proPlan = React.useMemo(() => {
    const fromState = Array.isArray(plans)
      ? plans.find((p) => String(p?.id || '').toLowerCase() === 'pro')
      : null;
    return fromState || APP.PLANS.PRO;
  }, [plans]);

  // Animate in on mount
  React.useEffect(() => {
    Animated.timing(fadeAnim, {
      toValue: 1,
      duration: 300,
      useNativeDriver: true,
    }).start();
  }, [fadeAnim]);

  React.useEffect(() => {
    if (!Array.isArray(plans) || plans.length === 0) {
      dispatch(fetchPlans());
    }
  }, [dispatch, plans]);

  // Get message based on reason
  const getMessage = () => {
    switch (reason) {
      case SUBSCRIPTION.UPGRADE_REASONS.WATCHLIST_LIMIT:
        const watchlistLimit = proPlan.watchlist_limit;
        return {
          icon: 'heart',
          title: 'Watchlist Limit Reached',
          subtitle: `Upgrade to Pro for ${watchlistLimit} items`,
        };
      case SUBSCRIPTION.UPGRADE_REASONS.SEARCH_LIMIT:
        const searchLimit = proPlan.searches_per_day;
        return {
          icon: 'search',
          title: 'Daily Search Limit Reached',
          subtitle: `Upgrade to Pro for ${searchLimit} searches/day`,
        };
      default:
        return {
          icon: 'sparkles',
          title: 'Unlock More Features',
          subtitle: 'Upgrade your plan for enhanced access',
        };
    }
  };

  const message = getMessage();

  // Handle upgrade button press
  const handleUpgrade = () => {
    dispatch(setSelectedPlan(targetPlan));
    navigation.navigate('Plans', { highlightedPlan: targetPlan });
  };

  // Handle dismiss
  const handleDismiss = () => {
    Animated.timing(fadeAnim, {
      toValue: 0,
      duration: 200,
      useNativeDriver: true,
    }).start(() => {
      dispatch(hideUpgradePrompt());
      onDismiss?.();
    });
  };

  // Get plan-specific colors
  const planColors = targetPlan === 'premium'
    ? [themePalette.primary || COLORS.premium, themePalette.accent || COLORS.premiumDark]
    : [themePalette.primary || COLORS.pro, themePalette.accent || COLORS.proDark];

  // Render based on variant
  if (variant === 'inline') {
    return (
      <Animated.View style={[styles.inlineContainer, { opacity: fadeAnim, backgroundColor: themePalette.surfaceMuted || COLORS.warning + '15' }]}>
        <View style={styles.inlineContent}>
          <Ionicons name={message.icon} size={16} color={COLORS.warning} />
          <Text style={styles.inlineText}>{message.subtitle}</Text>
        </View>
        <TouchableOpacity
          style={styles.inlineButton}
          onPress={handleUpgrade}
          activeOpacity={0.7}
        >
          <Text style={styles.inlineButtonText}>Upgrade</Text>
        </TouchableOpacity>
      </Animated.View>
    );
  }

  if (variant === 'card') {
    return (
      <Animated.View style={[styles.cardContainer, { opacity: fadeAnim }]}>
        <LinearGradient
          colors={planColors}
          start={{ x: 0, y: 0 }}
          end={{ x: 1, y: 1 }}
          style={styles.cardGradient}
        >
          {dismissible && (
            <TouchableOpacity
              style={styles.cardDismiss}
              onPress={handleDismiss}
              hitSlop={{ top: 10, bottom: 10, left: 10, right: 10 }}
            >
              <Ionicons name="close" size={18} color={COLORS.white} />
            </TouchableOpacity>
          )}
          
          <View style={styles.cardIcon}>
            <Ionicons name={message.icon} size={32} color={COLORS.white} />
          </View>
          
          <Text style={styles.cardTitle}>{message.title}</Text>
          <Text style={styles.cardSubtitle}>{message.subtitle}</Text>
          
          <TouchableOpacity
            style={styles.cardButton}
            onPress={handleUpgrade}
            activeOpacity={0.85}
          >
            <Text style={styles.cardButtonText}>View Plans</Text>
            <Ionicons name="arrow-forward" size={16} color={planColors[0]} />
          </TouchableOpacity>
        </LinearGradient>
      </Animated.View>
    );
  }

  // Default: banner variant
  return (
    <Animated.View style={[styles.bannerContainer, { opacity: fadeAnim, backgroundColor: themePalette.surface || COLORS.white, borderColor: themePalette.border || COLORS.gray200 }]}>
      <View style={styles.bannerContent}>
        <View style={[styles.bannerIcon, { backgroundColor: planColors[0] + '20' }]}>
          <Ionicons name={message.icon} size={18} color={planColors[0]} />
        </View>
        
        <View style={styles.bannerText}>
          <Text style={styles.bannerTitle}>{message.title}</Text>
          <Text style={styles.bannerSubtitle}>{message.subtitle}</Text>
        </View>
      </View>
      
      <View style={styles.bannerActions}>
        <TouchableOpacity
          style={[styles.bannerButton, { backgroundColor: planColors[0] }]}
          onPress={handleUpgrade}
          activeOpacity={0.85}
        >
          <Text style={styles.bannerButtonText}>Upgrade</Text>
        </TouchableOpacity>
        
        {dismissible && (
          <TouchableOpacity
            style={styles.bannerDismiss}
            onPress={handleDismiss}
            hitSlop={{ top: 10, bottom: 10, left: 10, right: 10 }}
          >
            <Ionicons name="close" size={18} color={COLORS.gray500} />
          </TouchableOpacity>
        )}
      </View>
    </Animated.View>
  );
};

// --------------------------------------------
// STYLES
// --------------------------------------------

const styles = StyleSheet.create({
  // Banner variant (default)
  bannerContainer: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    backgroundColor: COLORS.white,
    paddingHorizontal: 12,
    paddingVertical: 10,
    borderRadius: 12,
    marginHorizontal: 16,
    marginVertical: 8,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.08,
    shadowRadius: 8,
    elevation: 3,
    borderWidth: 1,
    borderColor: COLORS.gray200,
  },
  
  bannerContent: {
    flex: 1,
    flexDirection: 'row',
    alignItems: 'center',
  },
  
  bannerIcon: {
    width: 36,
    height: 36,
    borderRadius: 10,
    alignItems: 'center',
    justifyContent: 'center',
    marginRight: 10,
  },
  
  bannerText: {
    flex: 1,
  },
  
  bannerTitle: {
    fontSize: 13,
    fontWeight: '700',
    color: COLORS.textPrimary,
  },
  
  bannerSubtitle: {
    fontSize: 11,
    color: COLORS.textSecondary,
    marginTop: 1,
  },
  
  bannerActions: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  
  bannerButton: {
    paddingHorizontal: 14,
    paddingVertical: 8,
    borderRadius: 8,
  },
  
  bannerButtonText: {
    fontSize: 12,
    fontWeight: '700',
    color: COLORS.white,
  },
  
  bannerDismiss: {
    padding: 4,
  },
  
  // Card variant
  cardContainer: {
    marginHorizontal: 16,
    marginVertical: 12,
    borderRadius: 16,
    overflow: 'hidden',
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.15,
    shadowRadius: 12,
    elevation: 5,
  },
  
  cardGradient: {
    paddingHorizontal: 20,
    paddingVertical: 24,
    alignItems: 'center',
  },
  
  cardDismiss: {
    position: 'absolute',
    top: 12,
    right: 12,
    width: 28,
    height: 28,
    borderRadius: 14,
    backgroundColor: 'rgba(255,255,255,0.2)',
    alignItems: 'center',
    justifyContent: 'center',
  },
  
  cardIcon: {
    width: 64,
    height: 64,
    borderRadius: 32,
    backgroundColor: 'rgba(255,255,255,0.2)',
    alignItems: 'center',
    justifyContent: 'center',
    marginBottom: 16,
  },
  
  cardTitle: {
    fontSize: 18,
    fontWeight: '800',
    color: COLORS.white,
    textAlign: 'center',
  },
  
  cardSubtitle: {
    fontSize: 14,
    color: 'rgba(255,255,255,0.9)',
    textAlign: 'center',
    marginTop: 6,
    marginBottom: 20,
  },
  
  cardButton: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    backgroundColor: COLORS.white,
    paddingHorizontal: 24,
    paddingVertical: 14,
    borderRadius: 12,
  },
  
  cardButtonText: {
    fontSize: 15,
    fontWeight: '700',
    color: COLORS.textPrimary,
  },
  
  // Inline variant
  inlineContainer: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: 12,
    paddingVertical: 8,
    borderRadius: 8,
    gap: 8,
  },
  
  inlineContent: {
    flex: 1,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
  },
  
  inlineText: {
    flex: 1,
    fontSize: 12,
    color: COLORS.warning,
    fontWeight: '500',
  },
  
  inlineButton: {
    paddingHorizontal: 12,
    paddingVertical: 6,
    backgroundColor: COLORS.warning,
    borderRadius: 6,
  },
  
  inlineButtonText: {
    fontSize: 11,
    fontWeight: '700',
    color: COLORS.white,
  },
});

export default UpgradePrompt;