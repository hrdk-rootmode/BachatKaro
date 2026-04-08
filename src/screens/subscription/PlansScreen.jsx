// ============================================
// DEALHUNT APP - PLANS SCREEN
// Part 5: Subscription Plans & Mock Checkout
// ============================================

import React, { useEffect, useState, useCallback } from 'react';
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  TouchableOpacity,
  ActivityIndicator,
  Modal,
  Animated,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useFocusEffect, useNavigation, useRoute } from '@react-navigation/native';
import { useDispatch, useSelector } from 'react-redux';
import { Ionicons } from '@expo/vector-icons';
import { LinearGradient } from 'expo-linear-gradient';

import {
  fetchPlans,
  subscribeToPlan,
  selectPlans,
  selectPaymentInProgress,
  selectPaymentError,
  selectIsVerifying,
  clearError,
  clearPaymentDetails,
} from '../../store/subscriptionSlice';
import { selectUser, selectIsPro } from '../../store/authSlice';
import { COLORS, APP, SUBSCRIPTION } from '../../utils/constants';
import { getPaymentServiceStatus } from '../../services/razorpayService';
import { selectThemePalette } from '../../store/themeSlice';

// --------------------------------------------
// PLAN CARD COMPONENT
// --------------------------------------------

const PlanCard = ({
  plan,
  isCurrentPlan,
  isHighlighted,
  isRecommended,
  isBestValue,
  onSelect,
  disabled,
  themePalette,
}) => {
  const badge = SUBSCRIPTION.PLAN_BADGES[plan.id];

  const resolveFeatures = () => {
    const limits = plan?.limits || {};
    const sourceFeatures = plan?.features || {};

    const searches = Number(limits?.searches_per_day ?? sourceFeatures?.daily_searches);
    const watchlist = Number(limits?.watchlist_limit ?? sourceFeatures?.watchlist_limit);

    const dynamic = [];
    if (!Number.isNaN(searches)) {
      dynamic.push({
        icon: searches === -1 ? 'infinite-outline' : 'search-outline',
        text: searches === -1 ? 'Unlimited searches' : `${searches} searches per day`,
      });
    }

    if (!Number.isNaN(watchlist)) {
      dynamic.push({
        icon: 'heart-outline',
        text: watchlist === -1 ? 'Unlimited watchlist items' : `${watchlist} watchlist items`,
      });
    }

    if (sourceFeatures?.ad_free === true) {
      dynamic.push({ icon: 'ban-outline', text: 'No ads' });
    }

    if (sourceFeatures?.priority_support === true) {
      dynamic.push({ icon: 'headset-outline', text: 'Priority support' });
    }

    if (sourceFeatures?.ai_chat === true) {
      dynamic.push({ icon: 'chatbubbles-outline', text: 'AI chat access' });
    }

    if (dynamic.length) {
      return dynamic;
    }

    return SUBSCRIPTION.PLAN_FEATURES[plan.id] || [];
  };

  const features = resolveFeatures();
  
  const getGradientColors = () => {
    if (plan.id === 'premium') return [themePalette.primary || COLORS.premium, themePalette.accent || COLORS.premiumDark];
    if (plan.id === 'pro') return [themePalette.primary || COLORS.pro, themePalette.accent || COLORS.proDark];
    return [themePalette.surfaceMuted || COLORS.gray100, themePalette.border || COLORS.gray200];
  };

  const isPaid = plan.price > 0;
  
  return (
    <View style={[
      styles.planCard,
      { backgroundColor: themePalette.surface || COLORS.white, borderColor: themePalette.border || COLORS.gray200, shadowColor: themePalette.primary || '#000' },
      isHighlighted && styles.planCardHighlighted,
      isCurrentPlan && styles.planCardCurrent,
    ]}>
      {/* Badge */}
      {badge && (
        <View style={[styles.planBadge, { backgroundColor: badge.color }]}>
          <Text style={styles.planBadgeText}>{badge.text}</Text>
        </View>
      )}
      
      {/* Header */}
      <View style={styles.planHeader}>
        <Text style={styles.planName}>{plan.name}</Text>
        <View style={styles.priceContainer}>
          <Text style={styles.priceSymbol}>₹</Text>
          <Text style={styles.priceAmount}>{plan.price}</Text>
          {isPaid && <Text style={styles.priceInterval}>/month</Text>}
        </View>
      </View>
      
      {/* Features */}
      <View style={styles.featuresContainer}>
        {features.map((feature, index) => (
          <View key={index} style={styles.featureRow}>
            <Ionicons
              name={feature.icon}
              size={18}
              color={isPaid ? (themePalette.primary || COLORS.primary) : COLORS.gray500}
            />
            <Text style={[
              styles.featureText,
              !isPaid && styles.featureTextFree,
            ]}>
              {feature.text}
            </Text>
          </View>
        ))}
      </View>
      
      {/* Action Button */}
      {isCurrentPlan ? (
        <View style={styles.currentPlanButton}>
          <Ionicons name="checkmark-circle" size={20} color={themePalette.accent || COLORS.success} />
          <Text style={styles.currentPlanText}>Current Plan</Text>
        </View>
      ) : isPaid ? (
        <TouchableOpacity
          style={[
            styles.subscribeButton,
            plan.id === 'premium' && styles.subscribePremiumButton,
            disabled && styles.subscribeButtonDisabled,
          ]}
          onPress={() => onSelect(plan)}
          disabled={disabled}
          activeOpacity={0.85}
        >
          <LinearGradient
            colors={getGradientColors()}
            start={{ x: 0, y: 0 }}
            end={{ x: 1, y: 0 }}
            style={styles.subscribeButtonGradient}
          >
            <Text style={styles.subscribeButtonText}>
              Subscribe Now
            </Text>
          </LinearGradient>
        </TouchableOpacity>
      ) : (
        <View style={styles.freePlanIndicator}>
          <Text style={styles.freePlanText}>Included by default</Text>
        </View>
      )}
    </View>
  );
};

// --------------------------------------------
// MOCK CHECKOUT MODAL
// --------------------------------------------

const MockCheckoutModal = ({
  visible,
  plan,
  onClose,
  onConfirm,
  isProcessing,
}) => {
  const paymentStatus = getPaymentServiceStatus();
  
  if (!plan) return null;
  
  return (
    <Modal
      visible={visible}
      transparent
      animationType="slide"
      onRequestClose={onClose}
    >
      <View style={styles.modalOverlay}>
        <View style={styles.modalContent}>
          {/* Header */}
          <View style={styles.modalHeader}>
            <Text style={styles.modalTitle}>Complete Purchase</Text>
            <TouchableOpacity
              onPress={onClose}
              disabled={isProcessing}
              hitSlop={{ top: 10, bottom: 10, left: 10, right: 10 }}
            >
              <Ionicons name="close" size={24} color={COLORS.gray500} />
            </TouchableOpacity>
          </View>
          
          {/* Plan Summary */}
          <View style={styles.orderSummary}>
            <View style={styles.orderRow}>
              <Text style={styles.orderLabel}>{plan.name} Plan</Text>
              <Text style={styles.orderValue}>₹{plan.price}/month</Text>
            </View>
            <View style={styles.orderDivider} />
            <View style={styles.orderRow}>
              <Text style={styles.orderTotalLabel}>Total</Text>
              <Text style={styles.orderTotalValue}>₹{plan.price}</Text>
            </View>
          </View>
          
          {/* Demo Notice */}
          <View style={styles.demoNotice}>
            <Ionicons name="information-circle" size={20} color={COLORS.info} />
            <Text style={styles.demoNoticeText}>
              {paymentStatus.message}. This is a simulated payment for demonstration.
            </Text>
          </View>
          
          {/* Test Card Info */}
          <View style={styles.testCardInfo}>
            <Text style={styles.testCardTitle}>Test Card Details</Text>
            <Text style={styles.testCardDetail}>
              Card: {paymentStatus.testCard?.number || '4111 1111 1111 1111'}
            </Text>
            <Text style={styles.testCardDetail}>
              CVV: {paymentStatus.testCard?.cvv || '123'} | Expiry: {paymentStatus.testCard?.expiry || '12/25'}
            </Text>
          </View>
          
          {/* Action Buttons */}
          <TouchableOpacity
            style={[
              styles.confirmButton,
              isProcessing && styles.confirmButtonDisabled,
            ]}
            onPress={onConfirm}
            disabled={isProcessing}
            activeOpacity={0.85}
          >
            {isProcessing ? (
              <View style={styles.processingContainer}>
                <ActivityIndicator size="small" color={COLORS.white} />
                <Text style={styles.confirmButtonText}>Processing...</Text>
              </View>
            ) : (
              <>
                <Ionicons name="card" size={20} color={COLORS.white} />
                <Text style={styles.confirmButtonText}>Pay ₹{plan.price}</Text>
              </>
            )}
          </TouchableOpacity>
          
          <TouchableOpacity
            style={styles.cancelButton}
            onPress={onClose}
            disabled={isProcessing}
          >
            <Text style={styles.cancelButtonText}>Cancel</Text>
          </TouchableOpacity>
        </View>
      </View>
    </Modal>
  );
};

// --------------------------------------------
// SUCCESS MODAL
// --------------------------------------------

const SuccessModal = ({ visible, plan, onClose }) => {
  const scaleAnim = React.useRef(new Animated.Value(0)).current;
  
  useEffect(() => {
    if (visible) {
      Animated.spring(scaleAnim, {
        toValue: 1,
        tension: 50,
        friction: 7,
        useNativeDriver: true,
      }).start();
    } else {
      scaleAnim.setValue(0);
    }
  }, [visible, scaleAnim]);
  
  if (!plan) return null;
  
  return (
    <Modal
      visible={visible}
      transparent
      animationType="fade"
      onRequestClose={onClose}
    >
      <View style={styles.modalOverlay}>
        <Animated.View style={[
          styles.successModalContent,
          { transform: [{ scale: scaleAnim }] },
        ]}>
          <View style={styles.successIconContainer}>
            <Ionicons name="checkmark-circle" size={64} color={COLORS.success} />
          </View>
          
          <Text style={styles.successTitle}>Welcome to {plan.name}! 🎉</Text>
          <Text style={styles.successSubtitle}>
            Your subscription is now active. Enjoy your enhanced features!
          </Text>
          
          <View style={styles.successFeatures}>
            {(SUBSCRIPTION.PLAN_FEATURES[plan.id] || []).slice(0, 3).map((feature, index) => (
              <View key={index} style={styles.successFeatureRow}>
                <Ionicons name="checkmark" size={16} color={COLORS.success} />
                <Text style={styles.successFeatureText}>{feature.text}</Text>
              </View>
            ))}
          </View>
          
          <TouchableOpacity
            style={styles.successButton}
            onPress={onClose}
            activeOpacity={0.85}
          >
            <Text style={styles.successButtonText}>Start Exploring</Text>
          </TouchableOpacity>
        </Animated.View>
      </View>
    </Modal>
  );
};

// --------------------------------------------
// PLANS SCREEN
// --------------------------------------------

const PlansScreen = () => {
  const navigation = useNavigation();
  const route = useRoute();
  const dispatch = useDispatch();
  
  // Redux state
  const plans = useSelector(selectPlans);
  const paymentInProgress = useSelector(selectPaymentInProgress);
  const paymentError = useSelector(selectPaymentError);
  const isVerifying = useSelector(selectIsVerifying);
  const user = useSelector(selectUser);
  const isPro = useSelector(selectIsPro);
  const themePalette = useSelector(selectThemePalette);
  
  // Local state
  const [selectedPlan, setSelectedPlan] = useState(null);
  const [showCheckout, setShowCheckout] = useState(false);
  const [showSuccess, setShowSuccess] = useState(false);
  const [subscribedPlan, setSubscribedPlan] = useState(null);
  
  // Get highlighted plan from navigation params
  const highlightedPlanId = route.params?.highlightedPlan || 'pro';
  
  // Current user plan
  const currentPlanId = user?.plan?.toLowerCase() || 'free';
  
  // Refresh plans whenever this modal/screen becomes active.
  useFocusEffect(
    useCallback(() => {
      dispatch(fetchPlans());
    }, [dispatch])
  );
  
  // Clear errors on unmount
  useEffect(() => {
    return () => {
      dispatch(clearError());
    };
  }, [dispatch]);
  
  // Build plans list with Free plan
  const allPlans = React.useMemo(() => {
    const fallback = [APP.PLANS.FREE, APP.PLANS.PRO, APP.PLANS.PREMIUM];
    const source = Array.isArray(plans) && plans.length ? plans : fallback;

    const byId = {};
    source.forEach((plan) => {
      if (!plan?.id) return;
      byId[String(plan.id).toLowerCase()] = {
        ...plan,
        id: String(plan.id).toLowerCase(),
      };
    });

    if (!byId.free) {
      byId.free = APP.PLANS.FREE;
    }

    const orderedIds = ['free', 'pro', 'premium'];
    const ordered = orderedIds
      .filter((id) => byId[id])
      .map((id) => byId[id]);

    const others = Object.values(byId)
      .filter((plan) => !orderedIds.includes(plan.id))
      .sort((a, b) => Number(a.price || 0) - Number(b.price || 0));

    return [...ordered, ...others];
  }, [plans]);
  
  // Handle plan selection
  const handleSelectPlan = useCallback((plan) => {
    setSelectedPlan(plan);
    setShowCheckout(true);
  }, []);
  
  // Handle checkout confirmation
  const handleConfirmPayment = useCallback(async () => {
    if (!selectedPlan) return;
    
    try {
      const result = await dispatch(subscribeToPlan({
        planId: selectedPlan.id,
        userInfo: {
          email: user?.email,
          name: user?.email?.split('@')[0],
        },
      })).unwrap();
      
      // Success!
      setShowCheckout(false);
      setSubscribedPlan(selectedPlan);
      setShowSuccess(true);
    } catch (error) {
      console.error('[PlansScreen] Payment failed:', error);
      // Error is handled by Redux state
    }
  }, [dispatch, selectedPlan, user]);
  
  // Handle checkout close
  const handleCloseCheckout = useCallback(() => {
    if (!paymentInProgress) {
      setShowCheckout(false);
      setSelectedPlan(null);
      dispatch(clearError());
    }
  }, [paymentInProgress, dispatch]);
  
  // Handle success close
  const handleCloseSuccess = useCallback(() => {
    setShowSuccess(false);
    setSubscribedPlan(null);
    navigation.goBack();
  }, [navigation]);
  
  // Handle back press
  const handleBack = useCallback(() => {
    navigation.goBack();
  }, [navigation]);

  const handleClearPaymentState = useCallback(() => {
    dispatch(clearError());
    dispatch(clearPaymentDetails());
  }, [dispatch]);
  
  return (
    <SafeAreaView style={[styles.container, { backgroundColor: themePalette.background || styles.container.backgroundColor }]} edges={['top']}>
      {/* Header */}
      <View style={[styles.header, { backgroundColor: themePalette.surface || COLORS.white, borderBottomColor: themePalette.border || COLORS.gray200 }]}>
        <TouchableOpacity
          style={styles.backButton}
          onPress={handleBack}
          hitSlop={{ top: 10, bottom: 10, left: 10, right: 10 }}
        >
          <Ionicons name="arrow-back" size={24} color={COLORS.textPrimary} />
        </TouchableOpacity>
        <Text style={styles.headerTitle}>Choose Your Plan</Text>
        <View style={styles.headerSpacer} />
      </View>
      
      {/* Content */}
      <ScrollView
        style={styles.scrollView}
        contentContainerStyle={styles.scrollContent}
        showsVerticalScrollIndicator={false}
      >
        {/* Intro */}
        <View style={[styles.introSection, { backgroundColor: themePalette.surface || COLORS.white }]}>
          <Text style={styles.introTitle}>Unlock More Features</Text>
          <Text style={styles.introSubtitle}>
            Choose the plan that works best for you
          </Text>
        </View>
        
        {/* Error Message */}
        {paymentError && (
          <View style={styles.errorContainer}>
            <Ionicons name="alert-circle" size={20} color={COLORS.error} />
            <Text style={styles.errorText}>{paymentError}</Text>
            <TouchableOpacity
              onPress={handleClearPaymentState}
              style={styles.clearErrorButton}
              activeOpacity={0.8}
            >
              <Text style={styles.clearErrorText}>Clear</Text>
            </TouchableOpacity>
          </View>
        )}
        
        {/* Plan Cards */}
        <View style={styles.plansContainer}>
          {allPlans.map((plan) => (
            <PlanCard
              key={plan.id}
              plan={plan}
              isCurrentPlan={currentPlanId === plan.id}
              isHighlighted={highlightedPlanId === plan.id}
              isRecommended={plan.id === 'pro'}
              isBestValue={plan.id === 'premium'}
              onSelect={handleSelectPlan}
              disabled={paymentInProgress || currentPlanId === plan.id}
              themePalette={themePalette}
            />
          ))}
        </View>
        
        {/* Trial Info (if applicable) */}
        {isPro && (
          <View style={styles.trialInfo}>
            <Ionicons name="sparkles" size={18} color={COLORS.pro} />
            <Text style={styles.trialInfoText}>
              You have Pro access via trial or subscription
            </Text>
          </View>
        )}
        
        {/* Footer Info */}
        <View style={styles.footerInfo}>
          <Text style={styles.footerText}>
            • Cancel anytime from your profile
          </Text>
          <Text style={styles.footerText}>
            • Secure payment via Razorpay
          </Text>
          <Text style={styles.footerText}>
            • Instant activation after payment
          </Text>
        </View>
      </ScrollView>
      
      {/* Checkout Modal */}
      <MockCheckoutModal
        visible={showCheckout}
        plan={selectedPlan}
        onClose={handleCloseCheckout}
        onConfirm={handleConfirmPayment}
        isProcessing={paymentInProgress || isVerifying}
      />
      
      {/* Success Modal */}
      <SuccessModal
        visible={showSuccess}
        plan={subscribedPlan}
        onClose={handleCloseSuccess}
      />
    </SafeAreaView>
  );
};

// --------------------------------------------
// STYLES
// --------------------------------------------

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#F3F6FA',
  },
  
  // Header
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: 16,
    paddingVertical: 12,
    backgroundColor: COLORS.white,
    borderBottomWidth: 1,
    borderBottomColor: COLORS.gray200,
  },
  
  backButton: {
    width: 40,
    height: 40,
    borderRadius: 20,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: COLORS.gray100,
  },
  
  headerTitle: {
    fontSize: 18,
    fontWeight: '700',
    color: COLORS.textPrimary,
  },
  
  headerSpacer: {
    width: 40,
  },
  
  // Scroll
  scrollView: {
    flex: 1,
  },
  
  scrollContent: {
    padding: 16,
    paddingBottom: 32,
  },
  
  // Intro
  introSection: {
    alignItems: 'center',
    marginBottom: 24,
  },
  
  introTitle: {
    fontSize: 24,
    fontWeight: '800',
    color: COLORS.textPrimary,
    marginBottom: 8,
  },
  
  introSubtitle: {
    fontSize: 15,
    color: COLORS.textSecondary,
  },
  
  // Error
  errorContainer: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: COLORS.errorLight,
    padding: 12,
    borderRadius: 10,
    marginBottom: 16,
    gap: 8,
  },
  
  errorText: {
    flex: 1,
    fontSize: 13,
    color: COLORS.error,
  },

  clearErrorButton: {
    backgroundColor: '#FCD6D6',
    paddingHorizontal: 10,
    paddingVertical: 6,
    borderRadius: 8,
  },

  clearErrorText: {
    fontSize: 12,
    fontWeight: '700',
    color: COLORS.error,
  },
  
  // Plans
  plansContainer: {
    gap: 16,
  },
  
  // Plan Card
  planCard: {
    backgroundColor: COLORS.white,
    borderRadius: 16,
    padding: 20,
    borderWidth: 2,
    borderColor: COLORS.gray200,
  },
  
  planCardHighlighted: {
    borderColor: COLORS.pro,
    shadowColor: COLORS.pro,
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.2,
    shadowRadius: 12,
    elevation: 5,
  },
  
  planCardCurrent: {
    borderColor: COLORS.success,
    backgroundColor: COLORS.successLight + '30',
  },
  
  planBadge: {
    position: 'absolute',
    top: -10,
    right: 16,
    paddingHorizontal: 10,
    paddingVertical: 4,
    borderRadius: 12,
  },
  
  planBadgeText: {
    fontSize: 11,
    fontWeight: '700',
    color: COLORS.white,
  },
  
  planHeader: {
    marginBottom: 16,
  },
  
  planName: {
    fontSize: 20,
    fontWeight: '800',
    color: COLORS.textPrimary,
    marginBottom: 8,
  },
  
  priceContainer: {
    flexDirection: 'row',
    alignItems: 'baseline',
  },
  
  priceSymbol: {
    fontSize: 18,
    fontWeight: '700',
    color: COLORS.textPrimary,
  },
  
  priceAmount: {
    fontSize: 36,
    fontWeight: '800',
    color: COLORS.textPrimary,
  },
  
  priceInterval: {
    fontSize: 14,
    color: COLORS.textSecondary,
    marginLeft: 4,
  },
  
  featuresContainer: {
    marginBottom: 20,
    gap: 12,
  },
  
  featureRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
  },
  
  featureText: {
    fontSize: 14,
    color: COLORS.textPrimary,
  },
  
  featureTextFree: {
    color: COLORS.textSecondary,
  },
  
  // Buttons
  currentPlanButton: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: COLORS.successLight,
    paddingVertical: 14,
    borderRadius: 12,
    gap: 8,
  },
  
  currentPlanText: {
    fontSize: 15,
    fontWeight: '700',
    color: COLORS.success,
  },
  
  subscribeButton: {
    borderRadius: 12,
    overflow: 'hidden',
  },
  
  subscribePremiumButton: {},
  
  subscribeButtonDisabled: {
    opacity: 0.6,
  },
  
  subscribeButtonGradient: {
    paddingVertical: 14,
    alignItems: 'center',
  },
  
  subscribeButtonText: {
    fontSize: 15,
    fontWeight: '700',
    color: COLORS.white,
  },
  
  freePlanIndicator: {
    alignItems: 'center',
    paddingVertical: 14,
  },
  
  freePlanText: {
    fontSize: 14,
    color: COLORS.textSecondary,
  },
  
  // Trial Info
  trialInfo: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: COLORS.pro + '15',
    padding: 12,
    borderRadius: 10,
    marginTop: 20,
    gap: 8,
  },
  
  trialInfoText: {
    fontSize: 13,
    color: COLORS.proDark,
    fontWeight: '500',
  },
  
  // Footer
  footerInfo: {
    marginTop: 24,
    paddingHorizontal: 8,
  },
  
  footerText: {
    fontSize: 12,
    color: COLORS.textSecondary,
    marginBottom: 6,
  },
  
  // Modal
  modalOverlay: {
    flex: 1,
    backgroundColor: 'rgba(0,0,0,0.5)',
    justifyContent: 'flex-end',
  },
  
  modalContent: {
    backgroundColor: COLORS.white,
    borderTopLeftRadius: 24,
    borderTopRightRadius: 24,
    padding: 24,
    paddingBottom: 34,
  },
  
  modalHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginBottom: 20,
  },
  
  modalTitle: {
    fontSize: 20,
    fontWeight: '800',
    color: COLORS.textPrimary,
  },
  
  orderSummary: {
    backgroundColor: COLORS.gray50,
    borderRadius: 12,
    padding: 16,
    marginBottom: 16,
  },
  
  orderRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  
  orderLabel: {
    fontSize: 15,
    color: COLORS.textPrimary,
  },
  
  orderValue: {
    fontSize: 15,
    color: COLORS.textSecondary,
  },
  
  orderDivider: {
    height: 1,
    backgroundColor: COLORS.gray200,
    marginVertical: 12,
  },
  
  orderTotalLabel: {
    fontSize: 16,
    fontWeight: '700',
    color: COLORS.textPrimary,
  },
  
  orderTotalValue: {
    fontSize: 18,
    fontWeight: '800',
    color: COLORS.primary,
  },
  
  demoNotice: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    backgroundColor: COLORS.infoLight,
    padding: 12,
    borderRadius: 10,
    marginBottom: 12,
    gap: 8,
  },
  
  demoNoticeText: {
    flex: 1,
    fontSize: 12,
    color: COLORS.info,
    lineHeight: 18,
  },
  
  testCardInfo: {
    backgroundColor: COLORS.gray100,
    padding: 12,
    borderRadius: 10,
    marginBottom: 20,
  },
  
  testCardTitle: {
    fontSize: 12,
    fontWeight: '700',
    color: COLORS.textSecondary,
    marginBottom: 6,
  },
  
  testCardDetail: {
    fontSize: 12,
    color: COLORS.textSecondary,
    fontFamily: 'monospace',
  },
  
  confirmButton: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: COLORS.primary,
    paddingVertical: 16,
    borderRadius: 12,
    gap: 8,
    marginBottom: 12,
  },
  
  confirmButtonDisabled: {
    backgroundColor: COLORS.gray400,
  },
  
  confirmButtonText: {
    fontSize: 16,
    fontWeight: '700',
    color: COLORS.white,
  },
  
  processingContainer: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
  },
  
  cancelButton: {
    alignItems: 'center',
    paddingVertical: 12,
  },
  
  cancelButtonText: {
    fontSize: 15,
    color: COLORS.textSecondary,
    fontWeight: '600',
  },
  
  // Success Modal
  successModalContent: {
    backgroundColor: COLORS.white,
    marginHorizontal: 24,
    marginVertical: 'auto',
    borderRadius: 24,
    padding: 32,
    alignItems: 'center',
  },
  
  successIconContainer: {
    marginBottom: 20,
  },
  
  successTitle: {
    fontSize: 22,
    fontWeight: '800',
    color: COLORS.textPrimary,
    textAlign: 'center',
    marginBottom: 8,
  },
  
  successSubtitle: {
    fontSize: 14,
    color: COLORS.textSecondary,
    textAlign: 'center',
    marginBottom: 24,
    lineHeight: 20,
  },
  
  successFeatures: {
    alignSelf: 'stretch',
    backgroundColor: COLORS.successLight + '50',
    borderRadius: 12,
    padding: 16,
    marginBottom: 24,
    gap: 10,
  },
  
  successFeatureRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
  },
  
  successFeatureText: {
    fontSize: 14,
    color: COLORS.textPrimary,
  },
  
  successButton: {
    backgroundColor: COLORS.primary,
    paddingVertical: 14,
    paddingHorizontal: 32,
    borderRadius: 12,
  },
  
  successButtonText: {
    fontSize: 15,
    fontWeight: '700',
    color: COLORS.white,
  },
});

export default PlansScreen;