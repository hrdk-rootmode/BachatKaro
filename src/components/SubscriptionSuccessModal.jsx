import React, { useEffect, useRef } from 'react';
import {
  View,
  Text,
  StyleSheet,
  Modal,
  TouchableOpacity,
  TouchableWithoutFeedback,
  Vibration,
} from 'react-native';
import { useSelector, useDispatch } from 'react-redux';
import { Ionicons } from '@expo/vector-icons';
import { Audio } from 'expo-av';

import {
  selectPaymentStatus,
  dismissPaymentSuccess,
} from '../store/subscriptionSlice';
import { COLORS, SUBSCRIPTION } from '../utils/constants';

const AUTO_DISMISS_MS = 12000;
const SUCCESS_SOUND_URL = 'https://actions.google.com/sounds/v1/cartoon/pop.ogg';

const SubscriptionSuccessModal = () => {
  const dispatch = useDispatch();
  const paymentStatus = useSelector(selectPaymentStatus);
  const soundRef = useRef(null);

  const isVisible = Boolean(paymentStatus?.success && !paymentStatus?.dismissed);

  useEffect(() => {
    if (!isVisible) return;

    const playSuccessSound = async () => {
      try {
        await Audio.setAudioModeAsync({
          allowsRecordingIOS: false,
          playsInSilentModeIOS: true,
          shouldDuckAndroid: true,
          staysActiveInBackground: false,
          playThroughEarpieceAndroid: false,
        });

        const { sound } = await Audio.Sound.createAsync(
          { uri: SUCCESS_SOUND_URL },
          { shouldPlay: true, volume: 1.0 }
        );

        soundRef.current = sound;
        sound.setOnPlaybackStatusUpdate((status) => {
          if (status.didJustFinish) {
            sound.unloadAsync().catch(() => {});
            soundRef.current = null;
          }
        });
      } catch (error) {
        Vibration.vibrate(120);
      }
    };

    playSuccessSound();

    const timer = setTimeout(() => {
      dispatch(dismissPaymentSuccess());
    }, AUTO_DISMISS_MS);

    return () => {
      clearTimeout(timer);
      if (soundRef.current) {
        soundRef.current.unloadAsync().catch(() => {});
        soundRef.current = null;
      }
    };
  }, [dispatch, isVisible]);

  const handleDismiss = () => {
    dispatch(dismissPaymentSuccess());
  };

  if (!isVisible) return null;

  const planType = String(paymentStatus?.planType || 'Pro');
  const durationMonths = Number(paymentStatus?.durationMonths || 1);
  const amount = Number(paymentStatus?.amount || 0);
  const transactionId = paymentStatus?.transactionId || `TXN-${Date.now()}`;

  const features = (SUBSCRIPTION.PLAN_FEATURES[planType.toLowerCase()] || []).slice(0, 3);

  return (
    <Modal
      visible={isVisible}
      transparent
      animationType="fade"
      onRequestClose={handleDismiss}
      statusBarTranslucent
    >
      <View style={styles.overlay}>
        <TouchableWithoutFeedback onPress={handleDismiss}>
          <View style={styles.backdrop} />
        </TouchableWithoutFeedback>

        <View style={styles.card}>
          <View style={styles.iconWrap}>
            <Ionicons name="checkmark-circle" size={64} color="#16A34A" />
          </View>

          <Text style={styles.title}>Subscription Activated</Text>
          <Text style={styles.subtitle}>Welcome to {planType}</Text>

          <View style={styles.detailsBox}>
            <Text style={styles.detailLine}>Amount: ₹{amount}/month</Text>
            <Text style={styles.detailLine}>
              Duration: {durationMonths} month{durationMonths > 1 ? 's' : ''}
            </Text>
            <Text style={styles.detailLine} numberOfLines={1}>
              Txn: {transactionId}
            </Text>
          </View>

          {features.length > 0 && (
            <View style={styles.featureBox}>
              {features.map((feature, index) => (
                <View key={`feature-${index}`} style={styles.featureRow}>
                  <Ionicons name="checkmark" size={14} color="#16A34A" />
                  <Text style={styles.featureText}>{feature.text}</Text>
                </View>
              ))}
            </View>
          )}

          <TouchableOpacity style={styles.button} onPress={handleDismiss} activeOpacity={0.85}>
            <Text style={styles.buttonText}>Continue</Text>
          </TouchableOpacity>
        </View>
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
    backgroundColor: 'rgba(0,0,0,0.55)',
  },
  card: {
    width: '86%',
    maxWidth: 420,
    borderRadius: 16,
    backgroundColor: COLORS.white,
    padding: 20,
    elevation: 12,
    shadowColor: '#000',
    shadowOpacity: 0.25,
    shadowRadius: 14,
    shadowOffset: { width: 0, height: 6 },
  },
  iconWrap: {
    alignItems: 'center',
    marginBottom: 8,
  },
  title: {
    fontSize: 22,
    fontWeight: '800',
    color: COLORS.textPrimary,
    textAlign: 'center',
  },
  subtitle: {
    fontSize: 14,
    color: COLORS.textSecondary,
    textAlign: 'center',
    marginTop: 4,
    marginBottom: 14,
  },
  detailsBox: {
    backgroundColor: '#F8FAFC',
    borderRadius: 10,
    padding: 12,
  },
  detailLine: {
    fontSize: 13,
    color: COLORS.textPrimary,
    marginBottom: 5,
  },
  featureBox: {
    marginTop: 12,
    backgroundColor: '#F0FDF4',
    borderRadius: 10,
    padding: 10,
  },
  featureRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    marginBottom: 6,
  },
  featureText: {
    fontSize: 13,
    color: COLORS.textPrimary,
    flex: 1,
  },
  button: {
    marginTop: 14,
    backgroundColor: '#16A34A',
    borderRadius: 10,
    paddingVertical: 12,
    alignItems: 'center',
  },
  buttonText: {
    color: COLORS.white,
    fontSize: 15,
    fontWeight: '700',
  },
});

export default SubscriptionSuccessModal;
