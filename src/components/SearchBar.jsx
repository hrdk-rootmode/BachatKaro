// ============================================
// DEALHUNT APP - SEARCH BAR COMPONENT
// ============================================

import React, { useRef, useEffect } from 'react';
import {
  View,
  TextInput,
  TouchableOpacity,
  StyleSheet,
  ActivityIndicator,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';

import { COLORS } from '../utils/constants';

/**
 * Search bar component with clear button and loading indicator
 * 
 * @param {string} value - Current search text
 * @param {function} onChangeText - Text change handler
 * @param {function} onSubmit - Submit handler (enter key)
 * @param {boolean} isLoading - Show loading indicator
 * @param {boolean} autoFocus - Auto focus on mount
 * @param {string} placeholder - Placeholder text
 * @param {function} onFocus - Focus handler
 * @param {function} onBlur - Blur handler
 */
const SearchBar = ({
  value = '',
  onChangeText,
  onSubmit,
  isLoading = false,
  autoFocus = false,
  placeholder = 'Search products...',
  onFocus,
  onBlur,
  style,
}) => {
  const inputRef = useRef(null);

  useEffect(() => {
    if (autoFocus && inputRef.current) {
      setTimeout(() => {
        inputRef.current?.focus();
      }, 100);
    }
  }, [autoFocus]);

  const handleClear = () => {
    onChangeText?.('');
    inputRef.current?.focus();
  };

  return (
    <View style={[styles.container, style]}>
      {/* Search Icon */}
      <View style={styles.iconContainer}>
        {isLoading ? (
          <ActivityIndicator size="small" color={COLORS.primary} />
        ) : (
          <Ionicons name="search-outline" size={20} color={COLORS.gray500} />
        )}
      </View>

      {/* Text Input */}
      <TextInput
        ref={inputRef}
        style={styles.input}
        value={value}
        onChangeText={onChangeText}
        onSubmitEditing={onSubmit}
        placeholder={placeholder}
        placeholderTextColor={COLORS.gray400}
        returnKeyType="search"
        autoCapitalize="none"
        autoCorrect={false}
        onFocus={onFocus}
        onBlur={onBlur}
      />

      {/* Clear Button */}
      {value.length > 0 && (
        <TouchableOpacity
          style={styles.clearButton}
          onPress={handleClear}
          hitSlop={{ top: 10, bottom: 10, left: 10, right: 10 }}
        >
          <Ionicons name="close-circle" size={20} color={COLORS.gray400} />
        </TouchableOpacity>
      )}
    </View>
  );
};

// --------------------------------------------
// STYLES
// --------------------------------------------

const styles = StyleSheet.create({
  container: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: COLORS.gray100,
    borderRadius: 12,
    paddingHorizontal: 12,
    height: 48,
  },

  iconContainer: {
    marginRight: 10,
    width: 24,
    alignItems: 'center',
  },

  input: {
    flex: 1,
    fontSize: 16,
    color: COLORS.textPrimary,
    paddingVertical: 0,
  },

  clearButton: {
    marginLeft: 8,
    padding: 4,
  },
});

export default SearchBar;