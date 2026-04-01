// ============================================
// DEALHUNT APP - REWARD MODAL COMPONENT
// Part 4: Streak Reward Notification
// ============================================

import React, { useEffect, useRef } from 'react';
import {
  View,
  Text,
  StyleSheet,
  Modal,
  TouchableOpacity,
  Animated,
  Dimensions,
} from 'react-native';
import { useSelector, useDispatch } from 'react-redux';
import { Ionicons } from '@expo/vector-icons';
import { LinearGradient } from 'expo-linear-gradient';

import {
  selectUnlockedReward,
  selectIsRewardModalVisible,
  claimStreakReward,
} from '../store/streakSlice';
import { COLORS } from '../utils/constants';

const { width } = Dimensions.get('window');

// --------------------------------------------
// REWARD MODAL COMPONENT
// --------------------------------------------

const RewardModal = () => {
  const dispatch = useDispatch();
  const reward = useSelector(selectUnlockedReward);
  const isVisible = useSelector(selectIsRewardModalVisible);

  // Animations
  const scaleAnim = useRef(new Animated.Value(0)).current;
  const fadeAnim = useRef(new Animated.Value(0)).current;
  const confettiAnim = useRef(new Animated.Value(0)).current;

  useEffect(() => {
    if (isVisible) {
      // Entrance animation
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
      // Reset animations
      scaleAnim.setValue(0);
      fadeAnim.setValue(0);
      confettiAnim.setValue(0);
    }
  }, [confettiAnim, fadeAnim, isVisible, scaleAnim]);

  const handleClaim = () => {
    if (reward) {
      dispatch(claimStreakReward(reward));
    }
  };

  if (!isVisible || !reward) return null;

  const rewardDetails = reward.details || {};
  const durationHours = rewardDetails.duration_hours || 24;
  const message = rewardDetails.message || "You've unlocked a reward!";
  const milestone = reward.milestone || 7;

  return (
    <Modal
      visible={isVisible}
      transparent
      animationType="none"
      statusBarTranslucent
    >
      <View style={styles.overlay}>
        <Animated.View
          style={[
            styles.backdrop,
            {
              opacity: fadeAnim,
            },
          ]}
        />

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
            {/* Confetti/Sparkles */}
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
                <Text style={styles.rewardValue}>
                  {durationHours} Hour{durationHours > 1 ? 's' : ''} of PRO Access
                </Text>
                <Text style={styles.rewardSubtitle}>
                  Unlimited searches • Full watchlist • Ad-free
                </Text>
              </View>

              <Text style={styles.message}>{message}</Text>

              {/* Claim Button */}
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
                  <Text style={styles.claimText}>Claim My Reward</Text>
                  <Ionicons name="arrow-forward" size={20} color={COLORS.primary} />
                </LinearGradient>
              </TouchableOpacity>
            </View>
          </LinearGradient>
        </Animated.View>
      </View>
    </Modal>
  );
};

// --------------------------------------------
// STYLES
// --------------------------------------------

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
    borderRadius: 24,
    overflow: 'hidden',
    shadowColor: '#FF6B35',
    shadowOffset: { width: 0, height: 8 },
    shadowOpacity: 0.4,
    shadowRadius: 16,
    elevation: 12,
  },
  gradient: {
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
