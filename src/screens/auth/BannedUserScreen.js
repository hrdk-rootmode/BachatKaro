import React from 'react';
import {
  View,
  Text,
  ScrollView,
  StyleSheet,
  TouchableOpacity,
  Alert,
} from 'react-native';
import { COLORS } from '../../utils/constants';

const BannedUserScreen = ({ route, navigation }) => {
  const { banReason, blockedAt } = route.params || {};

  const handleContactSupport = () => {
    Alert.alert(
      'Contact Support',
      'For support regarding your account status, please email:\n\nsupport@dealhunt.com\n\nPlease include your email address and account details.',
      [{ text: 'OK', style: 'default' }]
    );
  };

  const handleLogout = () => {
    Alert.alert(
      'Logout',
      'This will log you out of the app.',
      [
        { text: 'Cancel', style: 'cancel' },
        {
          text: 'Logout',
          style: 'destructive',
          onPress: () => {
            // Clear user data and navigate to login
            navigation.reset({
              index: 0,
              routes: [{ name: 'Login' }],
            });
          },
        },
      ]
    );
  };

  return (
    <View style={styles.container}>
      <ScrollView contentContainerStyle={styles.scrollContent}>
        {/* Account Status Icon */}
        <View style={styles.iconContainer}>
          <Text style={styles.icon}>🚫</Text>
        </View>

        {/* Title */}
        <Text style={styles.title}>Account Suspended</Text>

        {/* Message */}
        <Text style={styles.message}>
          Your DealHunt account has been suspended due to a violation of our terms of service.
        </Text>

        {/* Ban Reason */}
        {banReason && (
          <View style={styles.reasonContainer}>
            <Text style={styles.reasonLabel}>Reason:</Text>
            <Text style={styles.reasonText}>{banReason}</Text>
          </View>
        )}

        {/* Blocked Date */}
        {blockedAt && (
          <View style={styles.dateContainer}>
            <Text style={styles.dateLabel}>Suspended on:</Text>
            <Text style={styles.dateText}>
              {new Date(blockedAt).toLocaleDateString('en-US', {
                year: 'numeric',
                month: 'long',
                day: 'numeric',
              })}
            </Text>
          </View>
        )}

        {/* Information Section */}
        <View style={styles.infoSection}>
          <Text style={styles.infoTitle}>What this means:</Text>
          <Text style={styles.infoText}>
            • You cannot search for deals{'\n'}
            • Your watchlist is inaccessible{'\n'}
            • Notifications are disabled{'\n'}
            • Your subscription is paused
          </Text>
        </View>

        {/* Appeal Section */}
        <View style={styles.appealSection}>
          <Text style={styles.appealTitle}>Need help?</Text>
          <Text style={styles.appealText}>
            If you believe this suspension is in error, please contact our support team.
          </Text>
        </View>

        {/* Action Buttons */}
        <View style={styles.buttonContainer}>
          <TouchableOpacity
            style={[styles.button, styles.primaryButton]}
            onPress={handleContactSupport}
          >
            <Text style={styles.primaryButtonText}>Contact Support</Text>
          </TouchableOpacity>

          <TouchableOpacity
            style={[styles.button, styles.secondaryButton]}
            onPress={handleLogout}
          >
            <Text style={styles.secondaryButtonText}>Logout</Text>
          </TouchableOpacity>
        </View>

        {/* Footer */}
        <Text style={styles.footer}>
          DealHunt Terms of Service • Privacy Policy
        </Text>
      </ScrollView>
    </View>
  );
};

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: COLORS.background,
  },
  scrollContent: {
    padding: 20,
    alignItems: 'center',
  },
  iconContainer: {
    marginBottom: 20,
  },
  icon: {
    fontSize: 80,
  },
  title: {
    fontSize: 28,
    fontWeight: 'bold',
    color: COLORS.text,
    textAlign: 'center',
    marginBottom: 16,
  },
  message: {
    fontSize: 16,
    color: COLORS.textSecondary,
    textAlign: 'center',
    lineHeight: 24,
    marginBottom: 24,
  },
  reasonContainer: {
    backgroundColor: COLORS.error + '10',
    padding: 16,
    borderRadius: 8,
    marginBottom: 20,
    width: '100%',
  },
  reasonLabel: {
    fontSize: 14,
    fontWeight: '600',
    color: COLORS.error,
    marginBottom: 8,
  },
  reasonText: {
    fontSize: 16,
    color: COLORS.text,
    lineHeight: 22,
  },
  dateContainer: {
    backgroundColor: COLORS.backgroundSecondary,
    padding: 16,
    borderRadius: 8,
    marginBottom: 20,
    width: '100%',
  },
  dateLabel: {
    fontSize: 14,
    fontWeight: '600',
    color: COLORS.textSecondary,
    marginBottom: 4,
  },
  dateText: {
    fontSize: 16,
    color: COLORS.text,
  },
  infoSection: {
    backgroundColor: COLORS.backgroundSecondary,
    padding: 16,
    borderRadius: 8,
    marginBottom: 24,
    width: '100%',
  },
  infoTitle: {
    fontSize: 16,
    fontWeight: '600',
    color: COLORS.text,
    marginBottom: 12,
  },
  infoText: {
    fontSize: 14,
    color: COLORS.textSecondary,
    lineHeight: 20,
  },
  appealSection: {
    marginBottom: 32,
    alignItems: 'center',
  },
  appealTitle: {
    fontSize: 18,
    fontWeight: '600',
    color: COLORS.text,
    marginBottom: 8,
    textAlign: 'center',
  },
  appealText: {
    fontSize: 14,
    color: COLORS.textSecondary,
    textAlign: 'center',
    lineHeight: 20,
  },
  buttonContainer: {
    width: '100%',
    gap: 12,
  },
  button: {
    padding: 16,
    borderRadius: 8,
    alignItems: 'center',
  },
  primaryButton: {
    backgroundColor: COLORS.primary,
  },
  secondaryButton: {
    backgroundColor: 'transparent',
    borderWidth: 1,
    borderColor: COLORS.border,
  },
  primaryButtonText: {
    color: 'white',
    fontSize: 16,
    fontWeight: '600',
  },
  secondaryButtonText: {
    color: COLORS.textSecondary,
    fontSize: 16,
    fontWeight: '600',
  },
  footer: {
    fontSize: 12,
    color: COLORS.textTertiary,
    textAlign: 'center',
    marginTop: 24,
  },
});

export default BannedUserScreen;
