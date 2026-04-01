// ============================================
// DEALHUNT APP - LOGIN/SIGNUP SCREEN
// ============================================

import React, { useState, useEffect } from 'react';
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  KeyboardAvoidingView,
  Platform,
  TouchableOpacity,
  Alert,
  Keyboard,
} from 'react-native';

import Button from '../../components/common/Button';
import Input from '../../components/common/Input';
import { useAuth } from '../../hooks/useAuth';
import { COLORS, APP } from '../../utils/constants';
import { SafeAreaView } from 'react-native-safe-area-context';
// --------------------------------------------
// LOGIN SCREEN COMPONENT
// --------------------------------------------

const LoginScreen = () => {
  // --------------------------------------------
  // STATE
  // --------------------------------------------
  
  const [isSignup, setIsSignup] = useState(false);
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [referralCodeInput, setReferralCodeInput] = useState('');
  const [errors, setErrors] = useState({});
  const [referralChecking, setReferralChecking] = useState(false);

  // --------------------------------------------
  // HOOKS
  // --------------------------------------------
  
  const {
    login,
    signup,
    isLoading,
    error,
    clearAuthError,
    checkReferralCode,
    referralValid,
    clearReferral,
  } = useAuth();

  // --------------------------------------------
  // EFFECTS
  // --------------------------------------------
  
  // Clear errors when switching modes
  useEffect(() => {
    setErrors({});
    clearAuthError();
    clearReferral();
  }, [isSignup]);

  // Show auth error
  useEffect(() => {
    if (error) {
      setErrors({ general: error });
    }
  }, [error]);

  // --------------------------------------------
  // HANDLERS
  // --------------------------------------------
  
  const handleSubmit = async () => {
    Keyboard.dismiss();
    setErrors({});
    clearAuthError();

    let result;

    if (isSignup) {
      // Signup flow
      result = await signup(email, password, confirmPassword, referralCodeInput);
    } else {
      // Login flow
      result = await login(email, password);
    }

    if (!result.success) {
      if (result.errors) {
        setErrors(result.errors);
      } else if (result.error) {
        setErrors({ general: result.error });
      }
    }
    // If success, navigation happens automatically via App.js
  };

  const handleReferralBlur = async () => {
    if (!referralCodeInput || referralCodeInput.trim() === '') {
      clearReferral();
      return;
    }

    setReferralChecking(true);
    await checkReferralCode(referralCodeInput);
    setReferralChecking(false);
  };

  const toggleMode = () => {
    setIsSignup(!isSignup);
    setEmail('');
    setPassword('');
    setConfirmPassword('');
    setReferralCodeInput('');
  };

  const handleForgotPassword = () => {
    Alert.alert(
      'Reset Password',
      'Password reset will be available in the next update. For now, please create a new account.',
      [{ text: 'OK' }]
    );
  };

  // --------------------------------------------
  // RENDER
  // --------------------------------------------
  
  return (
    <SafeAreaView style={styles.container}>
      <KeyboardAvoidingView
        style={styles.keyboardView}
        behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
      >
        <ScrollView
          contentContainerStyle={styles.scrollContent}
          showsVerticalScrollIndicator={false}
          keyboardShouldPersistTaps="handled"
        >
          {/* Header */}
          <View style={styles.header}>
            <Text style={styles.logo}>🔍</Text>
            <Text style={styles.appName}>{APP.NAME}</Text>
            <Text style={styles.tagline}>Find the Best Deals</Text>
          </View>

          {/* Form Card */}
          <View style={styles.formCard}>
            <Text style={styles.formTitle}>
              {isSignup ? 'Create Account' : 'Welcome Back'}
            </Text>
            <Text style={styles.formSubtitle}>
              {isSignup
                ? 'Sign up to start saving money'
                : 'Sign in to continue'}
            </Text>

            {/* General Error */}
            {errors.general && (
              <View style={styles.errorContainer}>
                <Text style={styles.errorText}>⚠️ {errors.general}</Text>
              </View>
            )}

            {/* Email Input */}
            <Input
              label="Email"
              value={email}
              onChangeText={setEmail}
              placeholder="Enter your email"
              keyboardType="email-address"
              autoCapitalize="none"
              error={errors.email}
              required
            />

            {/* Password Input */}
            <Input
              label="Password"
              value={password}
              onChangeText={setPassword}
              placeholder={isSignup ? 'Create a password' : 'Enter your password'}
              secureTextEntry
              showPasswordToggle
              error={errors.password}
              required
              helperText={
                isSignup
                  ? 'Min 8 characters, 1 uppercase, 1 number'
                  : null
              }
            />

            {/* Confirm Password (Signup only) */}
            {isSignup && (
              <Input
                label="Confirm Password"
                value={confirmPassword}
                onChangeText={setConfirmPassword}
                placeholder="Confirm your password"
                secureTextEntry
                showPasswordToggle
                error={errors.confirmPassword}
                required
              />
            )}

            {/* Referral Code (Signup only) */}
            {isSignup && (
              <View>
                <Input
                  label="Referral Code"
                  value={referralCodeInput}
                  onChangeText={(text) =>
                    setReferralCodeInput(text.toUpperCase())
                  }
                  placeholder="Enter referral code (optional)"
                  autoCapitalize="characters"
                  maxLength={10}
                  error={errors.referralCode}
                  helperText={
                    referralChecking
                      ? 'Checking code...'
                      : referralValid?.valid
                      ? '✅ Valid code! You\'ll get bonus searches'
                      : referralValid?.valid === false
                      ? '❌ Invalid referral code'
                      : 'Get bonus searches with a valid code'
                  }
                />
              </View>
            )}

            {/* Forgot Password (Login only) */}
            {!isSignup && (
              <TouchableOpacity
                style={styles.forgotButton}
                onPress={handleForgotPassword}
              >
                <Text style={styles.forgotText}>Forgot Password?</Text>
              </TouchableOpacity>
            )}

            {/* Submit Button */}
            <View style={styles.submitContainer}>
              <Button
                title={isSignup ? 'Create Account' : 'Sign In'}
                onPress={handleSubmit}
                loading={isLoading}
                disabled={isLoading}
              />
            </View>

            {/* Toggle Mode */}
            <View style={styles.toggleContainer}>
              <Text style={styles.toggleText}>
                {isSignup
                  ? 'Already have an account?'
                  : "Don't have an account?"}
              </Text>
              <TouchableOpacity onPress={toggleMode}>
                <Text style={styles.toggleLink}>
                  {isSignup ? 'Sign In' : 'Sign Up'}
                </Text>
              </TouchableOpacity>
            </View>
          </View>

          {/* Benefits Card (Signup) */}
          {isSignup && (
            <View style={styles.benefitsCard}>
              <Text style={styles.benefitsTitle}>🎁 What You Get:</Text>
              <Text style={styles.benefitItem}>✓ Compare prices across 6 platforms</Text>
              <Text style={styles.benefitItem}>✓ Price drop alerts</Text>
              <Text style={styles.benefitItem}>✓ 10 free searches daily</Text>
              <Text style={styles.benefitItem}>✓ 30-day Pro trial</Text>
            </View>
          )}

          {/* Footer */}
          <Text style={styles.footer}>
            By continuing, you agree to our Terms of Service
            
          </Text>
        </ScrollView>
      </KeyboardAvoidingView>
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
  
  keyboardView: {
    flex: 1,
  },
  
  scrollContent: {
    flexGrow: 1,
    padding: 20,
    justifyContent: 'center',
  },
  
  header: {
    alignItems: 'center',
    marginBottom: 30,
  },
  
  logo: {
    fontSize: 60,
    marginBottom: 10,
  },
  
  appName: {
    fontSize: 36,
    fontWeight: 'bold',
    color: COLORS.primary,
  },
  
  tagline: {
    fontSize: 16,
    color: COLORS.gray500,
    marginTop: 4,
  },
  
  formCard: {
    backgroundColor: COLORS.white,
    borderRadius: 20,
    padding: 24,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.1,
    shadowRadius: 12,
    elevation: 6,
  },
  
  formTitle: {
    fontSize: 24,
    fontWeight: 'bold',
    color: COLORS.textPrimary,
    textAlign: 'center',
    marginBottom: 8,
  },
  
  formSubtitle: {
    fontSize: 14,
    color: COLORS.gray500,
    textAlign: 'center',
    marginBottom: 24,
  },
  
  errorContainer: {
    backgroundColor: COLORS.errorLight,
    borderRadius: 8,
    padding: 12,
    marginBottom: 16,
    borderLeftWidth: 4,
    borderLeftColor: COLORS.error,
  },
  
  errorText: {
    color: COLORS.error,
    fontSize: 14,
  },
  
  forgotButton: {
    alignSelf: 'flex-end',
    marginBottom: 16,
    marginTop: -8,
  },
  
  forgotText: {
    color: COLORS.primary,
    fontSize: 14,
    fontWeight: '500',
  },
  
  submitContainer: {
    marginTop: 8,
  },
  
  toggleContainer: {
    flexDirection: 'row',
    justifyContent: 'center',
    marginTop: 20,
  },
  
  toggleText: {
    color: COLORS.gray500,
    fontSize: 14,
  },
  
  toggleLink: {
    color: COLORS.primary,
    fontSize: 14,
    fontWeight: '600',
  },
  
  benefitsCard: {
    backgroundColor: COLORS.primaryLight + '20',
    borderRadius: 16,
    padding: 20,
    marginTop: 24,
    borderWidth: 1,
    borderColor: COLORS.primary + '30',
  },
  
  benefitsTitle: {
    fontSize: 16,
    fontWeight: '600',
    color: COLORS.textPrimary,
    marginBottom: 12,
  },
  
  benefitItem: {
    fontSize: 14,
    color: COLORS.gray700,
    marginBottom: 6,
  },
  
  footer: {
    fontSize: 12,
    color: COLORS.gray400,
    textAlign: 'center',
    marginTop: 24,
  },
});

export default LoginScreen;