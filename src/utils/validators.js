// ============================================
// DEALHUNT APP - VALIDATION UTILITIES
// ============================================

import { VALIDATION, ERROR_MESSAGES } from './constants';

// --------------------------------------------
// EMAIL VALIDATION
// --------------------------------------------
export const validateEmail = (email) => {
  // Check if empty
  if (!email || email.trim() === '') {
    return {
      valid: false,
      error: 'Email is required',
    };
  }

  // Trim whitespace
  const trimmedEmail = email.trim().toLowerCase();

  // Check format
  if (!VALIDATION.EMAIL_REGEX.test(trimmedEmail)) {
    return {
      valid: false,
      error: ERROR_MESSAGES.INVALID_EMAIL,
    };
  }

  // Check for disposable email domains (basic list)
  const disposableDomains = [
    'tempmail.com',
    'guerrillamail.com',
    '10minutemail.com',
    'throwaway.email',
    'mailinator.com',
    'yopmail.com',
    'temp-mail.org',
    'fakeinbox.com',
    'trashmail.com',
    'getnada.com',
  ];

  const domain = trimmedEmail.split('@')[1];
  if (disposableDomains.includes(domain)) {
    return {
      valid: false,
      error: 'Disposable email addresses are not allowed',
    };
  }

  return {
    valid: true,
    value: trimmedEmail,
  };
};

// --------------------------------------------
// PASSWORD VALIDATION
// --------------------------------------------
export const validatePassword = (password) => {
  // Check if empty
  if (!password) {
    return {
      valid: false,
      error: 'Password is required',
    };
  }

  // Check minimum length
  if (password.length < VALIDATION.PASSWORD_MIN_LENGTH) {
    return {
      valid: false,
      error: `Password must be at least ${VALIDATION.PASSWORD_MIN_LENGTH} characters`,
    };
  }

  // Check for uppercase letter
  if (!/[A-Z]/.test(password)) {
    return {
      valid: false,
      error: 'Password must contain at least 1 uppercase letter',
    };
  }

  // Check for number
  if (!/\d/.test(password)) {
    return {
      valid: false,
      error: 'Password must contain at least 1 number',
    };
  }

  return {
    valid: true,
  };
};

// --------------------------------------------
// CONFIRM PASSWORD VALIDATION
// --------------------------------------------
export const validateConfirmPassword = (password, confirmPassword) => {
  if (!confirmPassword) {
    return {
      valid: false,
      error: 'Please confirm your password',
    };
  }

  if (password !== confirmPassword) {
    return {
      valid: false,
      error: 'Passwords do not match',
    };
  }

  return {
    valid: true,
  };
};

// --------------------------------------------
// REFERRAL CODE VALIDATION
// --------------------------------------------
export const validateReferralCode = (code) => {
  // Referral code is optional
  if (!code || code.trim() === '') {
    return {
      valid: true,
      value: null,
    };
  }

  const trimmedCode = code.trim().toUpperCase();

  // Check length (typically 6-8 characters)
  if (trimmedCode.length < 4 || trimmedCode.length > 10) {
    return {
      valid: false,
      error: 'Invalid referral code format',
    };
  }

  // Check for valid characters (alphanumeric only)
  if (!/^[A-Z0-9]+$/.test(trimmedCode)) {
    return {
      valid: false,
      error: 'Referral code can only contain letters and numbers',
    };
  }

  return {
    valid: true,
    value: trimmedCode,
  };
};

// --------------------------------------------
// VALIDATE FULL LOGIN FORM
// --------------------------------------------
export const validateLoginForm = (email, password) => {
  const errors = {};

  const emailResult = validateEmail(email);
  if (!emailResult.valid) {
    errors.email = emailResult.error;
  }

  const passwordResult = validatePassword(password);
  if (!passwordResult.valid) {
    errors.password = passwordResult.error;
  }

  return {
    valid: Object.keys(errors).length === 0,
    errors,
    values: {
      email: emailResult.value || email,
    },
  };
};

// --------------------------------------------
// VALIDATE FULL SIGNUP FORM
// --------------------------------------------
export const validateSignupForm = (email, password, confirmPassword, referralCode) => {
  const errors = {};

  const emailResult = validateEmail(email);
  if (!emailResult.valid) {
    errors.email = emailResult.error;
  }

  const passwordResult = validatePassword(password);
  if (!passwordResult.valid) {
    errors.password = passwordResult.error;
  }

  const confirmResult = validateConfirmPassword(password, confirmPassword);
  if (!confirmResult.valid) {
    errors.confirmPassword = confirmResult.error;
  }

  const referralResult = validateReferralCode(referralCode);
  if (!referralResult.valid) {
    errors.referralCode = referralResult.error;
  }

  return {
    valid: Object.keys(errors).length === 0,
    errors,
    values: {
      email: emailResult.value || email,
      referralCode: referralResult.value,
    },
  };
};

// --------------------------------------------
// SANITIZE INPUT (Prevent XSS)
// --------------------------------------------
export const sanitizeInput = (input) => {
  if (!input || typeof input !== 'string') {
    return '';
  }

  return input
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#x27;')
    .trim();
};

export default {
  validateEmail,
  validatePassword,
  validateConfirmPassword,
  validateReferralCode,
  validateLoginForm,
  validateSignupForm,
  sanitizeInput,
};