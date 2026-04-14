// ============================================
// DEALHUNT APP - REWARD MODAL COMPONENT
// Clean, simple - defaults to hidden
// ============================================

import React, { useEffect, useRef } from 'react';
import {
  View,
  Text,
  StyleSheet,
  Modal,
  TouchableOpacity,
  TouchableWithoutFeedback,
  Animated,
  Dimensions,
  ScrollView,
  AppState,
} from 'react-native';
import { useSelector, useDispatch } from 'react-redux';
import { Ionicons } from '@expo/vector-icons';
import { LinearGradient } from 'expo-linear-gradient';

import {
  selectUnlockedReward,
  selectIsRewardModalVisible,
  claimStreakReward,
  hideRewardModal,
} from '../store/streakSlice';
import { COLORS } from '../utils/constants';

const { width, height } = Dimensions.get('window');

const RewardModal = () => {
  const dispatch = useDispatch();
  const reward = useSelector(selectUnlockedReward);
  const isVisible = useSelector(selectIsRewardModalVisible);

  const scaleAnim = useRef(new Animated.Value(isVisible ? 1 : 0)).current;
  const fadeAnim = useRef(new Animated.Value(isVisible ? 1 : 0)).current;
  const confettiAnim = useRef(new Animated.Value(isVisible ? 1 : 0)).current;

  useEffect(() => {
    if (isVisible) {
      Animated.parallel([
        Animated.spring(scaleAnim, {
          toValue: 1,
          friction: 6,
          tension: 40,
          useNativeDriver: true,
        }),
        Animated.timing(fadeAnim, {
          toValue: 1,
          duration: 300,
          useNativeDriver: true,
        }),
        Animated.timing(confettiAnim, {
          toValue: 1,
          duration: 800,
          useNativeDriver: true,
        }),
      ]).start();
    } else {
      scaleAnim.setValue(0);
      fadeAnim.setValue(0);
      confettiAnim.setValue(0);
    }
  }, [confettiAnim, fadeAnim, isVisible, scaleAnim]);

  useEffect(() => {
    if (!isVisible) return undefined;

    const sub = AppState.addEventListener('change', (nextState) => {
      if (nextState === 'inactive' || nextState === 'background') {
        dispatch(hideRewardModal());
      }
    });

    const failsafe = setTimeout(() => {
      dispatch(hideRewardModal());
    }, 30000);

    return () => {
      sub?.remove();
      clearTimeout(failsafe);
    };
  }, [dispatch, isVisible]);

  const handleClaim = () => {
    if (reward) {
      dispatch(claimStreakReward(reward));
    }
  };

  const handleDismiss = () => {
    dispatch(hideRewardModal());
  };

  // Don't render modal if no reward or not visible
  if (!isVisible || !reward) return null;

  const rewardDetails = reward.details || {};
  const rewardType = reward.reward_type || reward.rewardType || reward.type || rewardDetails.reward_type || null;
  const rewardValue = Number(reward.reward_value || reward.rewardValue || rewardDetails.reward_value || 0);
  const durationHours = rewardDetails.duration_hours || (rewardType === 'premium_days' ? rewardValue * 24 : rewardValue);
  const message = rewardDetails.message || reward.description || rewardDetails.description || "You've unlocked a reward!";
  const milestone = reward.milestone || 7;

  let rewardHeadline = 'Reward Unlocked';
  let rewardSubtitle = 'Keep your streak alive to unlock more rewards.';

  if (rewardType === 'watchlist_slots') {
    rewardHeadline = `+${rewardValue || 1} Watchlist Slot${(rewardValue || 1) > 1 ? 's' : ''}`;
    rewardSubtitle = 'Your watchlist limit has been increased for this account.';
  } else if (rewardType === 'searches') {
    rewardHeadline = `+${rewardValue || 1} Daily Search Bonus`;
    rewardSubtitle = 'You can run more searches each day with this streak reward.';
  } else if (rewardType === 'unlimited_search_hours') {
    rewardHeadline = `${durationHours || rewardValue || 1} Hour${(durationHours || rewardValue || 1) > 1 ? 's' : ''} Unlimited Search`;
    rewardSubtitle = 'Search without daily limits during this reward window.';
  } else if (rewardType === 'premium_days') {
    rewardHeadline = `${rewardValue || 1} Premium Day${(rewardValue || 1) > 1 ? 's' : ''}`;
    rewardSubtitle = 'Premium features are activated for your account.';
  } else if (rewardType === 'free_month') {
    rewardHeadline = `${rewardValue || 1} Free Month${(rewardValue || 1) > 1 ? 's' : ''}`;
    rewardSubtitle = 'You have unlocked a free subscription period.';
  }

  return (
    <Modal
      visible={isVisible}
      transparent={true}
      animationType="none"
      statusBarTranslucent={true}
      onRequestClose={handleDismiss}
    >
      <View style={styles.overlay}>
        <TouchableWithoutFeedback onPress={handleDismiss}>
          <Animated.View
            style={[
              styles.backdrop,
              {
                opacity: fadeAnim,
              },
            ]}
          />
        </TouchableWithoutFeedback>

        <Animated.View
          style={[
            styles.container,
            {
              transform: [{ scale: scaleAnim }],
              opacity: fadeAnim,
            },
          ]}
        >
          <LinearGradient
            colors={['#FF6B35', '#F97316', '#FB923C']}
            start={{ x: 0, y: 0 }}
            end={{ x: 1, y: 1 }}
            style={styles.gradient}
          >
            <TouchableOpacity
              style={styles.closeButton}
              onPress={handleDismiss}
              hitSlop={{ top: 10, bottom: 10, left: 10, right: 10 }}
            >
              <Ionicons name="close" size={22} color={COLORS.white} />
            </TouchableOpacity>

            <ScrollView
              showsVerticalScrollIndicator={false}
              contentContainerStyle={styles.modalScrollContent}
            >
              {/* Confetti */}
              <View style={styles.confettiContainer}>
                {[...Array(8)].map((_, i) => (
                  <Animated.View
                    key={i}
                    style={[
                      styles.confetti,
                      {
                        left: `${(i + 1) * 12}%`,
                        opacity: confettiAnim,
                        transform: [
                          {
                            translateY: confettiAnim.interpolate({
                              inputRange: [0, 1],
                              outputRange: [0, 100 + Math.random() * 50],
                            }),
                          },
                          {
                            rotate: confettiAnim.interpolate({
                              inputRange: [0, 1],
                              outputRange: ['0deg', `${Math.random() * 360}deg`],
                            }),
                          },
                        ],
                      },
                    ]}
                  >
                    <Text style={styles.confettiEmoji}>
                      {['🎉', '✨', '🎊', '⭐'][i % 4]}
                    </Text>
                  </Animated.View>
                ))}
              </View>

              {/* Icon */}
              <View style={styles.iconContainer}>
                <View style={styles.iconCircle}>
                  <Ionicons name="trophy" size={48} color="#FFD700" />
                </View>
              </View>

              {/* Content */}
              <View style={styles.content}>
                <Text style={styles.title}>Congratulations! 🎉</Text>
                <Text style={styles.milestone}>
                  {milestone}-Day Streak Milestone!
                </Text>

                <View style={styles.rewardBox}>
                  <Ionicons name="gift" size={24} color={COLORS.white} />
                  <Text style={styles.rewardTitle}>You've Unlocked:</Text>
                  <Text style={styles.rewardValue}>{rewardHeadline}</Text>
                  <Text style={styles.rewardSubtitle}>{rewardSubtitle}</Text>
                </View>

                <Text style={styles.message}>{message}</Text>

                <TouchableOpacity
                  style={styles.claimButton}
                  onPress={handleClaim}
                  activeOpacity={0.9}
                >
                  <LinearGradient
                    colors={['#FFFFFF', '#F0F0F0']}
                    start={{ x: 0, y: 0 }}
                    end={{ x: 1, y: 1 }}
                    style={styles.claimGradient}
                  >
                    <Ionicons name="star" size={20} color={COLORS.primary} />
                    <Text style={styles.claimText}>Awesome!</Text>
                    <Ionicons name="arrow-forward" size={20} color={COLORS.primary} />
                  </LinearGradient>
                </TouchableOpacity>
              </View>
            </ScrollView>
          </LinearGradient>
        </Animated.View>
      </View>
    </Modal>
  );
};

const styles = StyleSheet.create({
  overlay: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
  },
  backdrop: {
    ...StyleSheet.absoluteFillObject,
    backgroundColor: 'rgba(0,0,0,0.7)',
  },
  container: {
    width: width - 48,
    maxWidth: 400,
    maxHeight: height * 0.88,
    borderRadius: 24,
    overflow: 'hidden',
    shadowColor: '#FF6B35',
    shadowOffset: { width: 0, height: 8 },
    shadowOpacity: 0.4,
    shadowRadius: 16,
    elevation: 12,
  },
  gradient: {
    flex: 1,
  },
  closeButton: {
    position: 'absolute',
    top: 10,
    right: 10,
    zIndex: 3,
    width: 32,
    height: 32,
    borderRadius: 16,
    backgroundColor: 'rgba(0,0,0,0.25)',
    alignItems: 'center',
    justifyContent: 'center',
  },
  modalScrollContent: {
    paddingTop: 40,
    paddingBottom: 32,
    paddingHorizontal: 24,
  },
  confettiContainer: {
    position: 'absolute',
    top: 0,
    left: 0,
    right: 0,
    height: 200,
  },
  confetti: {
    position: 'absolute',
    top: 20,
  },
  confettiEmoji: {
    fontSize: 20,
  },
  iconContainer: {
    alignItems: 'center',
    marginBottom: 20,
  },
  iconCircle: {
    width: 96,
    height: 96,
    borderRadius: 48,
    backgroundColor: 'rgba(255,255,255,0.25)',
    alignItems: 'center',
    justifyContent: 'center',
    borderWidth: 3,
    borderColor: 'rgba(255,255,255,0.4)',
  },
  content: {
    alignItems: 'center',
  },
  title: {
    fontSize: 28,
    fontWeight: '800',
    color: COLORS.white,
    textAlign: 'center',
    marginBottom: 8,
    letterSpacing: 0.5,
  },
  milestone: {
    fontSize: 16,
    fontWeight: '600',
    color: 'rgba(255,255,255,0.95)',
    textAlign: 'center',
    marginBottom: 24,
  },
  rewardBox: {
    backgroundColor: 'rgba(255,255,255,0.2)',
    borderRadius: 16,
    padding: 20,
    alignItems: 'center',
    width: '100%',
    borderWidth: 2,
    borderColor: 'rgba(255,255,255,0.3)',
    marginBottom: 20,
    gap: 8,
  },
  rewardTitle: {
    fontSize: 14,
    fontWeight: '600',
    color: 'rgba(255,255,255,0.9)',
    marginTop: 12,
    marginBottom: 4,
  },
  rewardValue: {
    fontSize: 22,
    fontWeight: '800',
    color: COLORS.white,
    textAlign: 'center',
    marginBottom: 8,
    letterSpacing: 0.5,
  },
  rewardSubtitle: {
    fontSize: 12,
    color: 'rgba(255,255,255,0.85)',
    textAlign: 'center',
  },
  message: {
    fontSize: 14,
    color: 'rgba(255,255,255,0.9)',
    textAlign: 'center',
    marginBottom: 24,
    lineHeight: 20,
  },
  claimButton: {
    width: '100%',
    borderRadius: 12,
    overflow: 'hidden',
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.2,
    shadowRadius: 8,
    elevation: 4,
  },
  claimGradient: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: 16,
    paddingHorizontal: 24,
    gap: 8,
  },
  claimText: {
    fontSize: 18,
    fontWeight: '700',
    color: COLORS.primary,
    letterSpacing: 0.5,
  },
});

export default RewardModal;


