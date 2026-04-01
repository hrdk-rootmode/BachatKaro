// ============================================
// DEALHUNT APP - PROFILE SCREEN (PLACEHOLDER)
// ============================================

import React from 'react';
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  Alert,
  TouchableOpacity,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useDispatch, useSelector } from 'react-redux';
import { Ionicons } from '@expo/vector-icons';
import { LinearGradient } from 'expo-linear-gradient';

import Button from '../components/common/Button';
import { useAuth } from '../hooks/useAuth';
import {
  selectIsPro,
  selectProTrialInfo,
  debugAdjustProTrialMinutesForDev,
} from '../store/authSlice';
import {
  selectCurrentStreak,
  debugIncreaseStreakForDev,
  debugResetStreakForDev,
} from '../store/streakSlice';
import { COLORS, APP } from '../utils/constants';

const formatTrialTimeRemaining = (expiresAt) => {
  if (!expiresAt) return null;

  const remainingMs = new Date(expiresAt).getTime() - Date.now();
  if (remainingMs <= 0) return null;

  const hours = Math.floor(remainingMs / (1000 * 60 * 60));
  const minutes = Math.floor((remainingMs % (1000 * 60 * 60)) / (1000 * 60));
  const seconds = Math.floor((remainingMs % (1000 * 60)) / 1000);
  return `${hours}:${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`;
};

// --------------------------------------------
// PROFILE SCREEN COMPONENT
// --------------------------------------------

const ProfileScreen = () => {
  const dispatch = useDispatch();
  const { user, userPlan, signOut, isLoading } = useAuth();
  const isPro = useSelector(selectIsPro);
  const proTrialInfo = useSelector(selectProTrialInfo);
  const currentStreak = useSelector(selectCurrentStreak);
  const [trialTimeRemaining, setTrialTimeRemaining] = React.useState(null);

  const handleIncreaseDays = (days) => {
    dispatch(debugIncreaseStreakForDev({ days }));
  };

  const handleResetStreak = () => {
    dispatch(debugResetStreakForDev());
  };

  const handleAdjustTrialMinutes = (minutesDelta) => {
    dispatch(debugAdjustProTrialMinutesForDev({ minutesDelta }));
  };

  React.useEffect(() => {
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

  const handleLogout = () => {
    Alert.alert(
      'Logout',
      'Are you sure you want to logout?',
      [
        { text: 'Cancel', style: 'cancel' },
        {
          text: 'Logout',
          style: 'destructive',
          onPress: async () => {
            await signOut();
          },
        },
      ]
    );
  };

  return (
    <SafeAreaView style={styles.container}>
      <ScrollView contentContainerStyle={styles.content} showsVerticalScrollIndicator={false}>
        {/* Header */}
        <View style={styles.header}>
          <Text style={styles.title}>Profile</Text>
        </View>

        {/* User Info Card */}
        <View style={styles.card}>
          <View style={styles.userHeader}>
            <View style={styles.avatar}>
              <Ionicons name="person" size={40} color={COLORS.white} />
            </View>
            <View style={styles.userInfo}>
              <Text style={styles.userName}>{user?.email?.split('@')[0] || 'User'}</Text>
              <Text style={styles.userEmail}>{user?.email || 'N/A'}</Text>
            </View>
          </View>
          
          <View style={styles.planBadge}>
            <Text style={styles.planText}>{userPlan?.toUpperCase()} PLAN</Text>
          </View>
        </View>

        {(isPro || proTrialInfo?.isActive) && (
          <View style={styles.proCardWrap}>
            <LinearGradient
              colors={['#F59E0B', '#EA580C']}
              start={{ x: 0, y: 0 }}
              end={{ x: 1, y: 1 }}
              style={styles.proCard}
            >
              <View style={styles.proCardHeader}>
                <Ionicons name="sparkles" size={18} color={COLORS.white} />
                <Text style={styles.proCardTitle}>PRO Access</Text>
              </View>

              {proTrialInfo?.isActive ? (
                <>
                  <Text style={styles.proCardStatus}>Trial active</Text>
                  <Text style={styles.proCardTime}>
                    {trialTimeRemaining || formatTrialTimeRemaining(proTrialInfo?.expiresAt) || '0:00:00'} remaining
                  </Text>
                </>
              ) : (
                <Text style={styles.proCardStatus}>Permanent Pro plan active</Text>
              )}
            </LinearGradient>
          </View>
        )}

        {currentStreak < 5 && (
          <View style={styles.unlockHintCard}>
            <Text style={styles.unlockHintTitle}>Surprise Unlock Strategy</Text>
            <Text style={styles.unlockHintText}>
              Keep your streak to 5 days to unlock future surprise streak experiences.
            </Text>
            <Text style={styles.unlockHintProgress}>{currentStreak}/5 days completed</Text>
          </View>
        )}

        {__DEV__ && (
          <View style={styles.devCard}>
            <Text style={styles.devTitle}>Developer Streak Debug</Text>
            <Text style={styles.devSubtitle}>Temporary controls for day progression testing.</Text>

            <View style={styles.devActionRow}>
              <TouchableOpacity
                style={[styles.devButton, styles.devButtonPrimary]}
                onPress={() => handleIncreaseDays(1)}
                activeOpacity={0.85}
              >
                <Text style={styles.devButtonText}>+1 Day</Text>
              </TouchableOpacity>

              <TouchableOpacity
                style={[styles.devButton, styles.devButtonSecondary]}
                onPress={() => handleIncreaseDays(3)}
                activeOpacity={0.85}
              >
                <Text style={styles.devButtonText}>+3 Days</Text>
              </TouchableOpacity>
            </View>

            <TouchableOpacity
              style={[styles.devButton, styles.devButtonReset]}
              onPress={handleResetStreak}
              activeOpacity={0.85}
            >
              <Text style={styles.devButtonText}>Reset Streak</Text>
            </TouchableOpacity>

            <View style={styles.devSectionDivider} />
            <Text style={styles.devSectionTitle}>Trial Time Debug</Text>

            <View style={styles.devActionRow}>
              <TouchableOpacity
                style={[styles.devButton, styles.devButtonPrimary]}
                onPress={() => handleAdjustTrialMinutes(15)}
                activeOpacity={0.85}
              >
                <Text style={styles.devButtonText}>+15m Trial</Text>
              </TouchableOpacity>

              <TouchableOpacity
                style={[styles.devButton, styles.devButtonSecondary]}
                onPress={() => handleAdjustTrialMinutes(-15)}
                activeOpacity={0.85}
              >
                <Text style={styles.devButtonText}>-15m Trial</Text>
              </TouchableOpacity>
            </View>

            <View style={styles.devActionRow}>
              <TouchableOpacity
                style={[styles.devButton, styles.devButtonPrimary]}
                onPress={() => handleAdjustTrialMinutes(60)}
                activeOpacity={0.85}
              >
                <Text style={styles.devButtonText}>+1h Trial</Text>
              </TouchableOpacity>

              <TouchableOpacity
                style={[styles.devButton, styles.devButtonSecondary]}
                onPress={() => handleAdjustTrialMinutes(-60)}
                activeOpacity={0.85}
              >
                <Text style={styles.devButtonText}>-1h Trial</Text>
              </TouchableOpacity>
            </View>

            {proTrialInfo?.isActive ? (
              <Text style={styles.devTrialInfo}>
                Live trial: {trialTimeRemaining || formatTrialTimeRemaining(proTrialInfo?.expiresAt) || 'expired'}
              </Text>
            ) : (
              <Text style={styles.devTrialInfo}>No active trial. Activate trial from Streak debug first.</Text>
            )}
          </View>
        )}

        {/* Menu Items */}
        <View style={styles.menuSection}>
          <View style={styles.menuItem}>
            <Ionicons name="settings-outline" size={24} color={COLORS.gray600} />
            <Text style={styles.menuText}>Settings</Text>
            <Ionicons name="chevron-forward" size={20} color={COLORS.gray400} />
          </View>
          
          <View style={styles.menuItem}>
            <Ionicons name="help-circle-outline" size={24} color={COLORS.gray600} />
            <Text style={styles.menuText}>Help & Support</Text>
            <Ionicons name="chevron-forward" size={20} color={COLORS.gray400} />
          </View>
          
          <View style={styles.menuItem}>
            <Ionicons name="information-circle-outline" size={24} color={COLORS.gray600} />
            <Text style={styles.menuText}>About</Text>
            <Ionicons name="chevron-forward" size={20} color={COLORS.gray400} />
          </View>
        </View>

        {/* Coming Soon Badge */}
        <View style={styles.comingSoon}>
          <Text style={styles.comingSoonText}>🚧 Full Profile in Part 5</Text>
        </View>

        {/* Logout Button */}
        <View style={styles.logoutContainer}>
          <Button
            title="Logout"
            onPress={handleLogout}
            variant="outline"
            loading={isLoading}
          />
        </View>

        {/* Version */}
        <Text style={styles.version}>v{APP.VERSION}</Text>
      </ScrollView>
    </SafeAreaView>
  );
};

// --------------------------------------------
// STYLES
// --------------------------------------------

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: COLORS.background,
  },
  
  content: {
    flexGrow: 1,
    padding: 20,
    paddingBottom: 28,
  },
  
  header: {
    marginBottom: 30,
  },
  
  title: {
    fontSize: 28,
    fontWeight: 'bold',
    color: COLORS.textPrimary,
  },
  
  card: {
    backgroundColor: COLORS.white,
    borderRadius: 16,
    padding: 20,
    marginBottom: 24,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.1,
    shadowRadius: 8,
    elevation: 4,
  },
  
  userHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    marginBottom: 16,
  },
  
  avatar: {
    width: 60,
    height: 60,
    borderRadius: 30,
    backgroundColor: COLORS.primary,
    alignItems: 'center',
    justifyContent: 'center',
  },
  
  userInfo: {
    marginLeft: 16,
    flex: 1,
  },
  
  userName: {
    fontSize: 18,
    fontWeight: '600',
    color: COLORS.textPrimary,
  },
  
  userEmail: {
    fontSize: 14,
    color: COLORS.textSecondary,
    marginTop: 2,
  },
  
  planBadge: {
    backgroundColor: COLORS.primaryLight,
    borderRadius: 12,
    paddingVertical: 8,
    paddingHorizontal: 16,
    alignSelf: 'flex-start',
  },
  
  planText: {
    fontSize: 12,
    fontWeight: '700',
    color: COLORS.primary,
  },

  proCardWrap: {
    marginBottom: 20,
    borderRadius: 14,
    overflow: 'hidden',
    shadowColor: '#F59E0B',
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.25,
    shadowRadius: 8,
    elevation: 5,
  },

  proCard: {
    paddingVertical: 14,
    paddingHorizontal: 16,
  },

  proCardHeader: {
    flexDirection: 'row',
    alignItems: 'center',
  },

  proCardTitle: {
    marginLeft: 8,
    fontSize: 15,
    fontWeight: '800',
    color: COLORS.white,
    letterSpacing: 0.4,
  },

  proCardStatus: {
    marginTop: 8,
    fontSize: 13,
    fontWeight: '600',
    color: COLORS.white,
  },

  proCardTime: {
    marginTop: 8,
    alignSelf: 'flex-start',
    fontSize: 13,
    color: COLORS.white,
    fontWeight: '700',
    backgroundColor: 'rgba(0,0,0,0.2)',
    paddingHorizontal: 9,
    paddingVertical: 4,
    borderRadius: 8,
  },

  unlockHintCard: {
    backgroundColor: '#FFF7ED',
    borderRadius: 12,
    paddingVertical: 12,
    paddingHorizontal: 14,
    marginBottom: 18,
    borderWidth: 1,
    borderColor: '#FED7AA',
  },

  unlockHintTitle: {
    fontSize: 14,
    fontWeight: '700',
    color: '#9A3412',
  },

  unlockHintText: {
    marginTop: 4,
    fontSize: 12,
    color: '#B45309',
    lineHeight: 18,
  },

  unlockHintProgress: {
    marginTop: 8,
    fontSize: 12,
    fontWeight: '700',
    color: '#C2410C',
  },

  devCard: {
    backgroundColor: '#EFF6FF',
    borderRadius: 12,
    paddingVertical: 12,
    paddingHorizontal: 14,
    marginBottom: 18,
    borderWidth: 1,
    borderColor: '#BFDBFE',
  },

  devTitle: {
    fontSize: 14,
    fontWeight: '700',
    color: '#1D4ED8',
  },

  devSubtitle: {
    marginTop: 4,
    marginBottom: 10,
    fontSize: 12,
    color: '#1E40AF',
  },

  devActionRow: {
    flexDirection: 'row',
    marginBottom: 10,
  },

  devButton: {
    borderRadius: 9,
    paddingVertical: 10,
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: 12,
  },

  devButtonPrimary: {
    flex: 1,
    marginRight: 8,
    backgroundColor: '#2563EB',
  },

  devButtonSecondary: {
    flex: 1,
    marginLeft: 8,
    backgroundColor: '#3B82F6',
  },

  devButtonReset: {
    backgroundColor: '#DC2626',
  },

  devButtonText: {
    fontSize: 13,
    fontWeight: '700',
    color: COLORS.white,
  },

  devSectionDivider: {
    height: 1,
    backgroundColor: '#BFDBFE',
    marginVertical: 10,
  },

  devSectionTitle: {
    fontSize: 12,
    fontWeight: '700',
    color: '#1D4ED8',
    marginBottom: 8,
    textTransform: 'uppercase',
    letterSpacing: 0.4,
  },

  devTrialInfo: {
    marginTop: 8,
    fontSize: 12,
    color: '#1E40AF',
    fontWeight: '600',
    textAlign: 'center',
  },
  
  menuSection: {
    backgroundColor: COLORS.white,
    borderRadius: 16,
    overflow: 'hidden',
    marginBottom: 24,
  },
  
  menuItem: {
    flexDirection: 'row',
    alignItems: 'center',
    padding: 16,
    borderBottomWidth: 1,
    borderBottomColor: COLORS.gray100,
  },
  
  menuText: {
    flex: 1,
    fontSize: 16,
    color: COLORS.textPrimary,
    marginLeft: 16,
  },
  
  comingSoon: {
    backgroundColor: COLORS.warningLight,
    borderRadius: 12,
    padding: 16,
    alignItems: 'center',
    marginBottom: 24,
  },
  
  comingSoonText: {
    fontSize: 14,
    fontWeight: '600',
    color: COLORS.gray700,
  },
  
  logoutContainer: {
    marginBottom: 20,
  },
  
  version: {
    fontSize: 12,
    color: COLORS.gray400,
    textAlign: 'center',
  },
});

export default ProfileScreen;