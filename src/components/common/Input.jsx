// ============================================
// DEALHUNT APP - CUSTOM INPUT COMPONENT
// ============================================

import React, { useState } from 'react';
import {
  View,
  TextInput,
  Text,
  StyleSheet,
  TouchableOpacity,
} from 'react-native';

import { COLORS } from '../../utils/constants';

// --------------------------------------------
// INPUT COMPONENT
// --------------------------------------------

const Input = ({
  label,
  value,
  onChangeText,
  placeholder,
  error,
  secureTextEntry = false,
  keyboardType = 'default',
  autoCapitalize = 'none',
  autoCorrect = false,
  maxLength,
  editable = true,
  multiline = false,
  numberOfLines = 1,
  leftIcon = null,
  rightIcon = null,
  onRightIconPress,
  style = {},
  inputStyle = {},
  showPasswordToggle = false,
  helperText = null,
  required = false,
}) => {
  const [isFocused, setIsFocused] = useState(false);
  const [showPassword, setShowPassword] = useState(false);

  // --------------------------------------------
  // HANDLERS
  // --------------------------------------------
  
  const handleFocus = () => setIsFocused(true);
  const handleBlur = () => setIsFocused(false);
  
  const togglePasswordVisibility = () => {
    setShowPassword(!showPassword);
  };

  // --------------------------------------------
  // COMPUTED STYLES
  // --------------------------------------------
  
  const getContainerStyle = () => {
    const baseStyle = [styles.inputContainer];
    
    if (isFocused) {
      baseStyle.push(styles.inputContainerFocused);
    }
    
    if (error) {
      baseStyle.push(styles.inputContainerError);
    }
    
    if (!editable) {
      baseStyle.push(styles.inputContainerDisabled);
    }
    
    return baseStyle;
  };

  // --------------------------------------------
  // RENDER
  // --------------------------------------------
  
  return (
    <View style={[styles.container, style]}>
      {/* Label */}
      {label && (
        <Text style={styles.label}>
          {label}
          {required && <Text style={styles.required}> *</Text>}
        </Text>
      )}
      
      {/* Input Container */}
      <View style={getContainerStyle()}>
        {/* Left Icon */}
        {leftIcon && <View style={styles.leftIcon}>{leftIcon}</View>}
        
        {/* Text Input */}
        <TextInput
          style={[
            styles.input,
            leftIcon && styles.inputWithLeftIcon,
            (rightIcon || showPasswordToggle) && styles.inputWithRightIcon,
            multiline && styles.multilineInput,
            inputStyle,
          ]}
          value={value}
          onChangeText={onChangeText}
          placeholder={placeholder}
          placeholderTextColor={COLORS.gray400}
          secureTextEntry={secureTextEntry && !showPassword}
          keyboardType={keyboardType}
          autoCapitalize={autoCapitalize}
          autoCorrect={autoCorrect}
          maxLength={maxLength}
          editable={editable}
          multiline={multiline}
          numberOfLines={numberOfLines}
          onFocus={handleFocus}
          onBlur={handleBlur}
        />
        
        {/* Password Toggle */}
        {showPasswordToggle && secureTextEntry && (
          <TouchableOpacity
            style={styles.rightIcon}
            onPress={togglePasswordVisibility}
          >
            <Text style={styles.toggleText}>
              {showPassword ? '🙈' : '👁️'}
            </Text>
          </TouchableOpacity>
        )}
        
        {/* Right Icon */}
        {rightIcon && !showPasswordToggle && (
          <TouchableOpacity
            style={styles.rightIcon}
            onPress={onRightIconPress}
            disabled={!onRightIconPress}
          >
            {rightIcon}
          </TouchableOpacity>
        )}
      </View>
      
      {/* Error Message */}
      {error && <Text style={styles.errorText}>{error}</Text>}
      
      {/* Helper Text */}
      {helperText && !error && (
        <Text style={styles.helperText}>{helperText}</Text>
      )}
    </View>
  );
};

// --------------------------------------------
// STYLES
// --------------------------------------------

const styles = StyleSheet.create({
  container: {
    marginBottom: 16,
  },
  
  label: {
    fontSize: 14,
    fontWeight: '600',
    color: COLORS.gray700,
    marginBottom: 8,
  },
  
  required: {
    color: COLORS.error,
  },
  
  inputContainer: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: COLORS.gray50,
    borderWidth: 1.5,
    borderColor: COLORS.gray200,
    borderRadius: 12,
    minHeight: 52,
  },
  
  inputContainerFocused: {
    borderColor: COLORS.primary,
    backgroundColor: COLORS.white,
  },
  
  inputContainerError: {
    borderColor: COLORS.error,
    backgroundColor: COLORS.errorLight,
  },
  
  inputContainerDisabled: {
    backgroundColor: COLORS.gray100,
    opacity: 0.7,
  },
  
  input: {
    flex: 1,
    fontSize: 16,
    color: COLORS.textPrimary,
    paddingHorizontal: 16,
    paddingVertical: 14,
  },
  
  inputWithLeftIcon: {
    paddingLeft: 8,
  },
  
  inputWithRightIcon: {
    paddingRight: 8,
  },
  
  multilineInput: {
    minHeight: 100,
    textAlignVertical: 'top',
  },
  
  leftIcon: {
    paddingLeft: 14,
  },
  
  rightIcon: {
    paddingRight: 14,
    paddingLeft: 8,
  },
  
  toggleText: {
    fontSize: 20,
  },
  
  errorText: {
    fontSize: 12,
    color: COLORS.error,
    marginTop: 6,
    marginLeft: 4,
  },
  
  helperText: {
    fontSize: 12,
    color: COLORS.gray500,
    marginTop: 6,
    marginLeft: 4,
  },
});

export default Input;