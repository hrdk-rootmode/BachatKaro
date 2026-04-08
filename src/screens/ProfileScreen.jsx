// ============================================
// DEALHUNT APP - PROFILE SCREEN (REFINED)
// Clean luxury layout with collapsible debug tools
// ============================================

import React, { useMemo, useState, useEffect, useCallback } from 'react';
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  Alert,
  TouchableOpacity,
  ActivityIndicator,
  RefreshControl,
  TextInput,
  Modal,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useDispatch, useSelector } from 'react-redux';
import { useFocusEffect, useNavigation } from '@react-navigation/native';
import { Ionicons } from '@expo/vector-icons';
import { LinearGradient } from 'expo-linear-gradient';

import Button from '../components/common/Button';
import { useAuth } from '../hooks/useAuth';
import firebaseService from '../services/firebase';
import {
  selectIsPro,
  selectProTrialInfo,
  debugAdjustProTrialMinutesForDev,
  refreshUserData,
} from '../store/authSlice';
import {
  fetchPaymentHistory,
  fetchPlans,
  fetchSubscriptionStatus,
  deletePaymentHistoryItem,
  clearPaymentHistory,
  selectPaymentHistory,
  selectPaymentDetails,
  selectPlans,
  selectIsDeletingHistoryItem,
  selectIsClearingHistory,
  selectHistoryActionError,
  clearHistoryActionError,
} from '../store/subscriptionSlice';
import { fetchWatchlist } from '../store/watchlistSlice';
import {
  selectPreferredThemeMode,
  selectThemePalette,
  setPreferredThemeMode,
} from '../store/themeSlice';
import {
  selectCurrentStreak,
  debugIncreaseStreakForDev,
  debugResetStreakForDev,
} from '../store/streakSlice';
import { COLORS, APP } from '../utils/constants';

const formatDateTime = (value, fallback = 'Not available yet') => {
  if (!value) return fallback;
  const dt = new Date(value);
  if (Number.isNaN(dt.getTime())) return fallback;
  return dt.toLocaleString();
};

const formatDateOnly = (value, fallback = 'Not available yet') => {
  if (!value) return fallback;
  const dt = new Date(value);
  if (Number.isNaN(dt.getTime())) return fallback;
  return dt.toLocaleDateString();
};

const formatTrialTimeRemaining = (expiresAt) => {
  if (!expiresAt) return null;
  const remainingMs = new Date(expiresAt).getTime() - Date.now();
  if (remainingMs <= 0) return null;

  const hours = Math.floor(remainingMs / (1000 * 60 * 60));
  const minutes = Math.floor((remainingMs % (1000 * 60 * 60)) / (1000 * 60));
  const seconds = Math.floor((remainingMs % (1000 * 60)) / 1000);
  return `${hours}:${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`;
};

const planGradient = (plan) => {
  const lower = String(plan || 'free').toLowerCase();
  if (lower === 'premium') return ['#0B1220', '#C8A45D'];
  if (lower === 'pro') return ['#B7791F', '#F59E0B'];
  return ['#6B7280', '#9CA3AF'];
};

const ProfileScreen = () => {
  const dispatch = useDispatch();
  const navigation = useNavigation();
  const { user, signOut, isLoading } = useAuth();

  const isPro = useSelector(selectIsPro);
  const proTrialInfo = useSelector(selectProTrialInfo);
  const paymentHistory = useSelector(selectPaymentHistory);
  const paymentDetails = useSelector(selectPaymentDetails);
  const plans = useSelector(selectPlans);
  const isDeletingHistoryItem = useSelector(selectIsDeletingHistoryItem);
  const isClearingHistory = useSelector(selectIsClearingHistory);
  const historyActionError = useSelector(selectHistoryActionError);
  const preferredThemeMode = useSelector(selectPreferredThemeMode);
  const activeTheme = useSelector(selectThemePalette);
  const currentStreak = useSelector(selectCurrentStreak);

  const [trialTimeRemaining, setTrialTimeRemaining] = useState(null);
  const [refreshing, setRefreshing] = useState(false);
  const [debugExpanded, setDebugExpanded] = useState(false);
  
  // Password change state
  const [passwordModalVisible, setPasswordModalVisible] = useState(false);
  const [currentPassword, setCurrentPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [isChangingPassword, setIsChangingPassword] = useState(false);

  const transactions = useMemo(
    () => (Array.isArray(paymentHistory?.transactions) ? paymentHistory.transactions : []),
    [paymentHistory]
  );

  const paymentServices = paymentHistory?.payment_services || {};
  const currentPlan = String(user?.plan || 'free').toLowerCase();
  const canUseSubscriptionTheme = ['pro', 'premium'].includes(currentPlan);
  const planInfo = useMemo(() => {
    const planMap = {};
    if (Array.isArray(plans)) {
      plans.forEach((plan) => {
        if (!plan?.id) return;
        planMap[String(plan.id).toLowerCase()] = plan;
      });
    }

    return (
      planMap[currentPlan] ||
      APP.PLANS[currentPlan.toUpperCase()] ||
      APP.PLANS.FREE
    );
  }, [plans, currentPlan]);

  const displayName =
    user?.display_name ||
    user?.name ||
    user?.full_name ||
    user?.email?.split('@')?.[0] ||
    'DealHunt User';

  const memberSince =
    user?.created_at ||
    user?.createdAt ||
    user?.joined_at ||
    user?.signup_at ||
    user?.last_login ||
    null;

  const lastActive = user?.last_active || user?.last_login || user?.updated_at || null;

  useEffect(() => {
    if (!proTrialInfo?.isActive || !proTrialInfo?.expiresAt) {
      setTrialTimeRemaining(null);
      return;
    }

    const updateTimer = () => {
      setTrialTimeRemaining(formatTrialTimeRemaining(proTrialInfo.expiresAt));
    };

    updateTimer();
    const interval = setInterval(updateTimer, 1000);
    return () => clearInterval(interval);
  }, [proTrialInfo?.expiresAt, proTrialInfo?.isActive]);

  useEffect(() => {
    dispatch(fetchPlans());
    dispatch(fetchPaymentHistory({ limit: 100 }));
  }, [dispatch]);

  useFocusEffect(
    useCallback(() => {
      dispatch(fetchPlans());
    }, [dispatch])
  );

  const handleRefreshAll = useCallback(async () => {
    setRefreshing(true);
    try {
      await Promise.all([
        dispatch(refreshUserData()),
        dispatch(fetchPlans()),
        dispatch(fetchSubscriptionStatus()),
        dispatch(fetchPaymentHistory({ limit: 100 })),
        dispatch(fetchWatchlist()),
      ]);
    } finally {
      setRefreshing(false);
    }
  }, [dispatch]);

  const handleManageSubscription = useCallback(() => {
    navigation.navigate('Plans');
  }, [navigation]);

  const handleSetDefaultTheme = () => {
    dispatch(setPreferredThemeMode('default'));
  };

  const handleSetSubscriptionTheme = () => {
    if (!canUseSubscriptionTheme) {
      Alert.alert('Theme Locked', 'Subscription theme is available for Pro and Premium users.');
      return;
    }
    dispatch(setPreferredThemeMode('subscription'));
  };

  const handleDeleteTransaction = (transaction) => {
    if (!transaction?.id) return;

    Alert.alert(
      'Delete transaction?',
      'This removes the selected transaction from history.',
      [
        { text: 'Cancel', style: 'cancel' },
        {
          text: 'Delete',
          style: 'destructive',
          onPress: async () => {
            await dispatch(deletePaymentHistoryItem({ transactionId: transaction.id }));
            dispatch(fetchPaymentHistory({ limit: 100 }));
          },
        },
      ]
    );
  };

  const handleRollbackSubscription = () => {
    Alert.alert(
      'Reset Subscription Data?',
      'This will roll back your plan to Free and clear subscription payment history for debugging.',
      [
        { text: 'Cancel', style: 'cancel' },
        {
          text: 'Reset',
          style: 'destructive',
          onPress: async () => {
            await dispatch(clearPaymentHistory());
            dispatch(fetchPaymentHistory({ limit: 100 }));
          },
        },
      ]
    );
  };

  const handleLogout = () => {
    Alert.alert('Logout', 'Are you sure you want to logout?', [
      { text: 'Cancel', style: 'cancel' },
      {
        text: 'Logout',
        style: 'destructive',
        onPress: async () => {
          await signOut();
        },
      },
    ]);
  };

  const handleChangePassword = useCallback(async () => {
    // Validation
    if (!currentPassword.trim()) {
      Alert.alert('Error', 'Please enter your current password');
      return;
    }
    
    if (!newPassword.trim()) {
      Alert.alert('Error', 'Please enter a new password');
      return;
    }
    
    if (newPassword.length < 6) {
      Alert.alert('Error', 'New password must be at least 6 characters long');
      return;
    }
    
    if (newPassword !== confirmPassword) {
      Alert.alert('Error', 'New passwords do not match');
      return;
    }

    setIsChangingPassword(true);
    
    try {
      const result = await firebaseService.changePassword(currentPassword, newPassword);
      
      if (result.success) {
        Alert.alert('Success', 'Password changed successfully!', [
          {
            text: 'OK',
            onPress: () => {
              // Reset form and close modal
              setCurrentPassword('');
              setNewPassword('');
              setConfirmPassword('');
              setPasswordModalVisible(false);
            }
          }
        ]);
      } else {
        Alert.alert('Error', result.error || 'Failed to change password');
      }
    } catch (error) {
      Alert.alert('Error', 'Failed to change password. Please try again.');
    } finally {
      setIsChangingPassword(false);
    }
  }, [currentPassword, newPassword, confirmPassword]);

  const openPasswordModal = () => {
    setCurrentPassword('');
    setNewPassword('');
    setConfirmPassword('');
    setPasswordModalVisible(true);
  };

  const closePasswordModal = () => {
    setCurrentPassword('');
    setNewPassword('');
    setConfirmPassword('');
    setPasswordModalVisible(false);
  };

  return (
    <SafeAreaView style={[styles.container, { backgroundColor: activeTheme.background || COLORS.background }]}> 
      <ScrollView
        contentContainerStyle={styles.content}
        showsVerticalScrollIndicator={false}
        refreshControl={
          <RefreshControl
            refreshing={refreshing}
            onRefresh={handleRefreshAll}
            tintColor={activeTheme.primary || COLORS.primary}
            colors={[activeTheme.primary || COLORS.primary]}
          />
        }
      >
        <View style={styles.headerRow}>
          <Text style={[styles.title, { color: activeTheme.text || COLORS.textPrimary }]}>Profile</Text>
          <View style={[styles.planChip, { borderColor: activeTheme.border || COLORS.gray200, backgroundColor: activeTheme.surface || COLORS.white }]}> 
            <Text style={[styles.planChipText, { color: activeTheme.primary || COLORS.primary }]}>{currentPlan.toUpperCase()}</Text>
          </View>
        </View>

        <LinearGradient
          colors={planGradient(currentPlan)}
          start={{ x: 0, y: 0 }}
          end={{ x: 1, y: 1 }}
          style={styles.profileHero}
        >
          <View style={styles.avatarWrap}>
            <Ionicons name="person" size={36} color={COLORS.white} />
          </View>
          <View style={styles.heroTextWrap}>
            <Text style={styles.heroName}>{displayName}</Text>
            <Text style={styles.heroEmail}>{user?.email || 'No email linked'}</Text>
            <Text style={styles.heroMeta}>Member since {formatDateOnly(memberSince, 'Recently joined')}</Text>
            <Text style={styles.heroMeta}>Last active {formatDateTime(lastActive, 'Active now')}</Text>
          </View>
        </LinearGradient>

        <View style={[styles.card, { backgroundColor: activeTheme.surface || COLORS.white, borderColor: activeTheme.border || COLORS.gray200 }]}> 
          <Text style={[styles.sectionTitle, { color: activeTheme.text || COLORS.textPrimary }]}>Subscription & Access</Text>

          <View style={styles.metricRow}>
            <View style={styles.metricItem}>
              <Text style={styles.metricLabel}>Searches / day</Text>
              <Text style={styles.metricValue}>{planInfo.searches_per_day === -1 ? 'Unlimited' : planInfo.searches_per_day}</Text>
            </View>
            <View style={styles.metricItem}>
              <Text style={styles.metricLabel}>Watchlist limit</Text>
              <Text style={styles.metricValue}>{planInfo.watchlist_limit}</Text>
            </View>
          </View>

          {proTrialInfo?.isActive && (
            <View style={styles.trialBox}>
              <Text style={styles.trialLabel}>Trial Active</Text>
              <Text style={styles.trialTime}>{trialTimeRemaining || '0:00:00'} remaining</Text>
              <Text style={styles.trialExpiry}>Expires: {formatDateTime(proTrialInfo.expiresAt)}</Text>
            </View>
          )}

          <Button title="Manage Subscription" onPress={handleManageSubscription} variant="outline" />
        </View>

        <View style={[styles.card, { backgroundColor: activeTheme.surface || COLORS.white, borderColor: activeTheme.border || COLORS.gray200 }]}> 
          <Text style={[styles.sectionTitle, { color: activeTheme.text || COLORS.textPrimary }]}>Theme Preference</Text>
          <Text style={styles.sectionHint}>Switch to subscription theme for a premium visual experience.</Text>

          <View style={styles.themeRow}>
            <TouchableOpacity
              style={[styles.themeBtn, preferredThemeMode === 'default' && styles.themeBtnActive]}
              onPress={handleSetDefaultTheme}
              activeOpacity={0.85}
            >
              <Text style={styles.themeBtnText}>Default</Text>
            </TouchableOpacity>

            <TouchableOpacity
              style={[
                styles.themeBtn,
                preferredThemeMode === 'subscription' && styles.themeBtnActive,
                !canUseSubscriptionTheme && styles.themeBtnDisabled,
              ]}
              onPress={handleSetSubscriptionTheme}
              activeOpacity={0.85}
            >
              <Text style={styles.themeBtnText}>Subscription</Text>
            </TouchableOpacity>
          </View>

          {!canUseSubscriptionTheme && (
            <Text style={styles.lockText}>Upgrade to Pro/Premium to unlock subscription theme.</Text>
          )}
        </View>

        <View style={[styles.card, { backgroundColor: activeTheme.surface || COLORS.white, borderColor: activeTheme.border || COLORS.gray200 }]}> 
          <View style={styles.sectionHeaderRow}>
            <Text style={[styles.sectionTitle, { color: activeTheme.text || COLORS.textPrimary }]}>Transaction History</Text>
            {__DEV__ && transactions.length > 0 && (
              <TouchableOpacity onPress={handleRollbackSubscription} disabled={isClearingHistory} style={styles.clearDemoBtn} activeOpacity={0.8}>
                {isClearingHistory ? (
                  <ActivityIndicator size="small" color={COLORS.error} />
                ) : (
                  <>
                    <Ionicons name="trash-outline" size={14} color={COLORS.error} />
                    <Text style={styles.clearDemoText}>Reset</Text>
                  </>
                )}
              </TouchableOpacity>
            )}
          </View>

          <Text style={styles.sectionHint}>
            {transactions.length} transaction{transactions.length === 1 ? '' : 's'} • Razorpay {paymentServices?.razorpay?.mock_mode ? 'mock' : 'live'}
          </Text>

          {historyActionError ? <Text style={styles.errorText}>{historyActionError}</Text> : null}

          {transactions.length === 0 ? (
            <View style={styles.emptyWrap}>
              <Ionicons name="receipt-outline" size={26} color={COLORS.gray400} />
              <Text style={styles.emptyText}>No transactions yet</Text>
            </View>
          ) : (
            transactions.map((tx) => (
              <View key={String(tx.id)} style={styles.txCard}>
                <View style={styles.txTopRow}>
                  <Text style={styles.txTitle}>{tx.plan || 'Subscription payment'}</Text>
                  <Text style={styles.txAmount}>₹{Number(tx.amount || 0).toFixed(2)}</Text>
                </View>
                <Text style={styles.txMeta}>{String(tx.status || 'pending').toUpperCase()} • {String(tx.platform || 'web').toUpperCase()}</Text>
                <Text style={styles.txMeta}>Date: {formatDateTime(tx.created_at, 'Timestamp syncing')}</Text>
                <Text numberOfLines={1} style={styles.txId}>{tx.razorpay_payment_id || tx.google_order_id || tx.id}</Text>

                {__DEV__ && (
                  <TouchableOpacity
                    style={styles.txDeleteBtn}
                    onPress={() => handleDeleteTransaction(tx)}
                    disabled={isDeletingHistoryItem}
                    activeOpacity={0.8}
                  >
                    <Ionicons name="trash" size={14} color={COLORS.error} />
                    <Text style={styles.txDeleteText}>Delete</Text>
                  </TouchableOpacity>
                )}
              </View>
            ))
          )}
        </View>

        {__DEV__ && (
          <View style={[styles.card, { backgroundColor: activeTheme.surface || COLORS.white, borderColor: activeTheme.border || COLORS.gray200 }]}> 
            <TouchableOpacity
              style={styles.debugHeader}
              onPress={() => setDebugExpanded((prev) => !prev)}
              activeOpacity={0.85}
            >
              <View style={styles.debugHeaderLeft}>
                <Ionicons name={debugExpanded ? 'eye' : 'eye-off'} size={16} color={activeTheme.primary || COLORS.primary} />
                <Text style={[styles.sectionTitle, { marginBottom: 0, color: activeTheme.text || COLORS.textPrimary }]}>Debug Tools</Text>
              </View>
              <Ionicons name={debugExpanded ? 'chevron-up' : 'chevron-down'} size={18} color={COLORS.gray500} />
            </TouchableOpacity>

            {debugExpanded && (
              <>
                <Text style={styles.sectionHint}>Hidden by default for a clean profile view.</Text>

                <View style={styles.debugLogsBox}>
                  <Text style={styles.debugLogText}>Payment attempts: {Number(paymentDetails?.attemptsCount || 0)}</Text>
                  <Text style={styles.debugLogText}>Last attempt: {formatDateTime(paymentDetails?.lastAttempt?.at)}</Text>
                  <Text style={styles.debugLogText}>Last success: {formatDateTime(paymentDetails?.lastSuccess?.at)}</Text>
                  <Text style={styles.debugLogText}>Last failure: {formatDateTime(paymentDetails?.lastFailure?.at)}</Text>
                </View>

                <View style={styles.debugButtonRow}>
                  <TouchableOpacity style={[styles.debugBtn, styles.debugPrimary]} onPress={() => dispatch(debugIncreaseStreakForDev({ days: 1 }))}>
                    <Text style={styles.debugBtnText}>+1 Day</Text>
                  </TouchableOpacity>
                  <TouchableOpacity style={[styles.debugBtn, styles.debugSecondary]} onPress={() => dispatch(debugIncreaseStreakForDev({ days: 3 }))}>
                    <Text style={styles.debugBtnText}>+3 Days</Text>
                  </TouchableOpacity>
                </View>

                <TouchableOpacity style={[styles.debugBtn, styles.debugDanger]} onPress={() => dispatch(debugResetStreakForDev())}>
                  <Text style={styles.debugBtnText}>Reset Streak</Text>
                </TouchableOpacity>

                <View style={styles.debugButtonRow}>
                  <TouchableOpacity style={[styles.debugBtn, styles.debugPrimary]} onPress={() => dispatch(debugAdjustProTrialMinutesForDev({ minutesDelta: 15 }))}>
                    <Text style={styles.debugBtnText}>+15m Trial</Text>
                  </TouchableOpacity>
                  <TouchableOpacity style={[styles.debugBtn, styles.debugSecondary]} onPress={() => dispatch(debugAdjustProTrialMinutesForDev({ minutesDelta: -15 }))}>
                    <Text style={styles.debugBtnText}>-15m Trial</Text>
                  </TouchableOpacity>
                </View>
              </>
            )}
          </View>
        )}

        <View style={[styles.card, { backgroundColor: activeTheme.surface || COLORS.white, borderColor: activeTheme.border || COLORS.gray200 }]}> 
          <Text style={[styles.sectionTitle, { color: activeTheme.text || COLORS.textPrimary }]}>Account Settings</Text>
          <Text style={styles.sectionHint}>Manage your account security and preferences.</Text>

          <TouchableOpacity 
            style={styles.settingRow} 
            onPress={openPasswordModal}
            activeOpacity={0.7}
          >
            <View style={styles.settingLeft}>
              <Ionicons name="lock-closed" size={20} color={activeTheme.primary || COLORS.primary} />
              <Text style={[styles.settingText, { color: activeTheme.text || COLORS.textPrimary }]}>Change Password</Text>
            </View>
            <Ionicons name="chevron-forward" size={16} color={COLORS.gray400} />
          </TouchableOpacity>
        </View>

        <View style={styles.logoutContainer}>
          <Button title="Logout" onPress={handleLogout} variant="outline" loading={isLoading} />
        </View>

        <Text style={styles.version}>v{APP.VERSION}</Text>
      </ScrollView>

      {/* Password Change Modal */}
      <Modal
        visible={passwordModalVisible}
        animationType="slide"
        presentationStyle="pageSheet"
        onRequestClose={closePasswordModal}
      >
        <SafeAreaView style={[styles.container, { backgroundColor: activeTheme.background || COLORS.background }]}>
          <View style={styles.modalHeader}>
            <TouchableOpacity onPress={closePasswordModal} style={styles.closeButton}>
              <Ionicons name="close" size={24} color={activeTheme.text || COLORS.textPrimary} />
            </TouchableOpacity>
            <Text style={[styles.modalTitle, { color: activeTheme.text || COLORS.textPrimary }]}>Change Password</Text>
            <View style={styles.placeholder} />
          </View>

          <ScrollView style={styles.modalContent} showsVerticalScrollIndicator={false}>
            <View style={[styles.card, { backgroundColor: activeTheme.surface || COLORS.white, borderColor: activeTheme.border || COLORS.gray200 }]}>
              <Text style={[styles.sectionTitle, { color: activeTheme.text || COLORS.textPrimary }]}>Security Settings</Text>
              <Text style={styles.sectionHint}>Enter your current password and choose a new one.</Text>

              <View style={styles.inputGroup}>
                <Text style={[styles.inputLabel, { color: activeTheme.text || COLORS.textPrimary }]}>Current Password</Text>
                <TextInput
                  style={[styles.textInput, { 
                    backgroundColor: activeTheme.surface || COLORS.white,
                    borderColor: activeTheme.border || COLORS.gray200,
                    color: activeTheme.text || COLORS.textPrimary
                  }]}
                  value={currentPassword}
                  onChangeText={setCurrentPassword}
                  placeholder="Enter current password"
                  placeholderTextColor={COLORS.gray400}
                  secureTextEntry
                  autoCapitalize="none"
                />
              </View>

              <View style={styles.inputGroup}>
                <Text style={[styles.inputLabel, { color: activeTheme.text || COLORS.textPrimary }]}>New Password</Text>
                <TextInput
                  style={[styles.textInput, { 
                    backgroundColor: activeTheme.surface || COLORS.white,
                    borderColor: activeTheme.border || COLORS.gray200,
                    color: activeTheme.text || COLORS.textPrimary
                  }]}
                  value={newPassword}
                  onChangeText={setNewPassword}
                  placeholder="Enter new password (min. 6 characters)"
                  placeholderTextColor={COLORS.gray400}
                  secureTextEntry
                  autoCapitalize="none"
                />
              </View>

              <View style={styles.inputGroup}>
                <Text style={[styles.inputLabel, { color: activeTheme.text || COLORS.textPrimary }]}>Confirm New Password</Text>
                <TextInput
                  style={[styles.textInput, { 
                    backgroundColor: activeTheme.surface || COLORS.white,
                    borderColor: activeTheme.border || COLORS.gray200,
                    color: activeTheme.text || COLORS.textPrimary
                  }]}
                  value={confirmPassword}
                  onChangeText={setConfirmPassword}
                  placeholder="Confirm new password"
                  placeholderTextColor={COLORS.gray400}
                  secureTextEntry
                  autoCapitalize="none"
                />
              </View>

              <View style={styles.modalButtonContainer}>
                <Button
                  title="Cancel"
                  onPress={closePasswordModal}
                  variant="outline"
                  style={styles.modalButton}
                />
                <Button
                  title="Update Password"
                  onPress={handleChangePassword}
                  loading={isChangingPassword}
                  style={styles.modalButton}
                />
              </View>
            </View>
          </ScrollView>
        </SafeAreaView>
      </Modal>
    </SafeAreaView>
  );
};

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: COLORS.background,
  },
  content: {
    flexGrow: 1,
    paddingHorizontal: 18,
    paddingTop: 12,
    paddingBottom: 24,
  },
  headerRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 12,
  },
  title: {
    fontSize: 30,
    fontWeight: '800',
    color: COLORS.textPrimary,
  },
  planChip: {
    borderWidth: 1,
    borderColor: COLORS.gray200,
    borderRadius: 999,
    paddingHorizontal: 10,
    paddingVertical: 5,
  },
  planChipText: {
    fontSize: 11,
    fontWeight: '800',
    color: COLORS.primary,
  },
  profileHero: {
    borderRadius: 18,
    padding: 16,
    marginBottom: 16,
    flexDirection: 'row',
    alignItems: 'center',
  },
  avatarWrap: {
    width: 62,
    height: 62,
    borderRadius: 31,
    backgroundColor: 'rgba(255,255,255,0.25)',
    justifyContent: 'center',
    alignItems: 'center',
  },
  heroTextWrap: {
    marginLeft: 14,
    flex: 1,
  },
  heroName: {
    color: COLORS.white,
    fontSize: 20,
    fontWeight: '800',
  },
  heroEmail: {
    marginTop: 2,
    color: COLORS.white,
    fontSize: 13,
    opacity: 0.95,
  },
  heroMeta: {
    marginTop: 3,
    color: COLORS.white,
    fontSize: 12,
    opacity: 0.95,
  },
  card: {
    backgroundColor: COLORS.white,
    borderRadius: 14,
    borderWidth: 1,
    borderColor: COLORS.gray200,
    padding: 14,
    marginBottom: 14,
  },
  sectionHeaderRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 2,
  },
  sectionTitle: {
    fontSize: 16,
    fontWeight: '800',
    color: COLORS.textPrimary,
    marginBottom: 10,
  },
  sectionHint: {
    fontSize: 12,
    color: COLORS.textSecondary,
    marginBottom: 10,
  },
  metricRow: {
    flexDirection: 'row',
    gap: 10,
    marginBottom: 12,
  },
  metricItem: {
    flex: 1,
    backgroundColor: '#F8FAFC',
    borderRadius: 10,
    borderWidth: 1,
    borderColor: '#E2E8F0',
    paddingVertical: 10,
    paddingHorizontal: 10,
  },
  metricLabel: {
    fontSize: 11,
    color: COLORS.textSecondary,
    marginBottom: 4,
  },
  metricValue: {
    fontSize: 16,
    color: COLORS.textPrimary,
    fontWeight: '800',
  },
  trialBox: {
    backgroundColor: '#FFF7ED',
    borderColor: '#FED7AA',
    borderWidth: 1,
    borderRadius: 10,
    paddingHorizontal: 10,
    paddingVertical: 10,
    marginBottom: 12,
  },
  trialLabel: {
    fontSize: 11,
    fontWeight: '800',
    color: '#B45309',
    textTransform: 'uppercase',
    letterSpacing: 0.5,
  },
  trialTime: {
    fontSize: 15,
    fontWeight: '800',
    color: '#9A3412',
    marginTop: 4,
  },
  trialExpiry: {
    marginTop: 4,
    fontSize: 12,
    color: '#B45309',
  },
  themeRow: {
    flexDirection: 'row',
    gap: 8,
  },
  themeBtn: {
    flex: 1,
    borderRadius: 10,
    borderWidth: 1,
    borderColor: COLORS.gray300,
    backgroundColor: COLORS.gray50,
    paddingVertical: 10,
    alignItems: 'center',
  },
  themeBtnActive: {
    borderColor: COLORS.primary,
    backgroundColor: COLORS.primary + '15',
  },
  themeBtnDisabled: {
    opacity: 0.55,
  },
  themeBtnText: {
    fontSize: 12,
    color: COLORS.textPrimary,
    fontWeight: '700',
  },
  lockText: {
    marginTop: 8,
    fontSize: 11,
    color: COLORS.warning,
    fontWeight: '600',
  },
  clearDemoBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 5,
    paddingHorizontal: 8,
    paddingVertical: 6,
    borderRadius: 8,
    backgroundColor: COLORS.errorLight,
  },
  clearDemoText: {
    fontSize: 12,
    color: COLORS.error,
    fontWeight: '700',
  },
  errorText: {
    marginBottom: 8,
    fontSize: 12,
    color: COLORS.error,
    fontWeight: '600',
  },
  emptyWrap: {
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: 14,
  },
  emptyText: {
    marginTop: 8,
    fontSize: 13,
    color: COLORS.textSecondary,
    fontWeight: '600',
  },
  txCard: {
    marginTop: 8,
    borderRadius: 10,
    borderWidth: 1,
    borderColor: COLORS.gray200,
    padding: 10,
    backgroundColor: '#FFFFFF',
  },
  txTopRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  txTitle: {
    fontSize: 14,
    color: COLORS.textPrimary,
    fontWeight: '700',
  },
  txAmount: {
    fontSize: 13,
    color: COLORS.textPrimary,
    fontWeight: '800',
  },
  txMeta: {
    marginTop: 4,
    fontSize: 11,
    color: COLORS.textSecondary,
  },
  txId: {
    marginTop: 4,
    fontSize: 10,
    color: COLORS.gray500,
  },
  txDeleteBtn: {
    marginTop: 8,
    alignSelf: 'flex-end',
    flexDirection: 'row',
    alignItems: 'center',
    gap: 5,
    paddingHorizontal: 8,
    paddingVertical: 6,
    borderRadius: 8,
    backgroundColor: COLORS.errorLight,
  },
  txDeleteText: {
    fontSize: 11,
    fontWeight: '700',
    color: COLORS.error,
  },
  debugHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  debugHeaderLeft: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  debugLogsBox: {
    borderWidth: 1,
    borderColor: '#BFDBFE',
    backgroundColor: '#EFF6FF',
    borderRadius: 10,
    padding: 10,
    marginBottom: 10,
  },
  debugLogText: {
    fontSize: 11,
    color: '#1E3A8A',
    marginBottom: 2,
  },
  debugButtonRow: {
    flexDirection: 'row',
    gap: 8,
    marginBottom: 8,
  },
  debugBtn: {
    borderRadius: 9,
    paddingVertical: 10,
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: 10,
    flex: 1,
  },
  debugPrimary: {
    backgroundColor: '#2563EB',
  },
  debugSecondary: {
    backgroundColor: '#3B82F6',
  },
  debugDanger: {
    backgroundColor: '#DC2626',
    marginBottom: 8,
  },
  debugBtnText: {
    fontSize: 12,
    color: COLORS.white,
    fontWeight: '700',
  },
  debugFootText: {
    fontSize: 11,
    color: '#1E40AF',
    fontWeight: '600',
  },
  logoutContainer: {
    marginTop: 2,
    marginBottom: 12,
  },
  version: {
    textAlign: 'center',
    fontSize: 12,
    color: COLORS.gray400,
  },
  // Password change styles
  settingRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingVertical: 12,
    paddingHorizontal: 4,
    borderRadius: 8,
    backgroundColor: 'transparent',
  },
  settingLeft: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
  },
  settingText: {
    fontSize: 15,
    fontWeight: '600',
    color: COLORS.textPrimary,
  },
  // Modal styles
  modalHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingHorizontal: 18,
    paddingVertical: 12,
    borderBottomWidth: 1,
    borderBottomColor: COLORS.gray200,
  },
  closeButton: {
    padding: 4,
  },
  modalTitle: {
    fontSize: 18,
    fontWeight: '800',
    color: COLORS.textPrimary,
  },
  placeholder: {
    width: 32,
  },
  modalContent: {
    flex: 1,
    paddingHorizontal: 18,
    paddingTop: 12,
  },
  inputGroup: {
    marginBottom: 20,
  },
  inputLabel: {
    fontSize: 14,
    fontWeight: '600',
    color: COLORS.textPrimary,
    marginBottom: 8,
  },
  textInput: {
    borderWidth: 1,
    borderColor: COLORS.gray200,
    borderRadius: 10,
    paddingHorizontal: 14,
    paddingVertical: 12,
    fontSize: 16,
    backgroundColor: COLORS.white,
    color: COLORS.textPrimary,
  },
  modalButtonContainer: {
    flexDirection: 'row',
    gap: 12,
    marginTop: 24,
    marginBottom: 20,
  },
  modalButton: {
    flex: 1,
  },
});

export default ProfileScreen;
