// ============================================
// DEALHUNT APP - EMPTY STATE COMPONENT
// ============================================

import React from 'react';
import {
  View,
  Text,
  StyleSheet,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';

import Button from './Button';
import { COLORS } from '../../utils/constants';

/**
 * Reusable empty state component
 * 
 * @param {string} icon - Ionicons name
 * @param {string} title - Main title
 * @param {string} subtitle - Description text
 * @param {string} buttonTitle - Optional button text
 * @param {function} onButtonPress - Optional button handler
 * @param {string} emoji - Optional emoji instead of icon
 */
const EmptyState = ({
  icon = 'search-outline',
  title = 'No results found',
  subtitle = 'Try searching with different keywords',
  buttonTitle = null,
  onButtonPress = null,
  emoji = null,
}) => {
  return (
    <View style={styles.container}>
      {/* Icon or Emoji */}
      {emoji ? (
        <Text style={styles.emoji}>{emoji}</Text>
      ) : (
        <View style={styles.iconContainer}>
          <Ionicons name={icon} size={64} color={COLORS.gray300} />
        </View>
      )}

      {/* Title */}
      <Text style={styles.title}>{title}</Text>

      {/* Subtitle */}
      <Text style={styles.subtitle}>{subtitle}</Text>

      {/* Optional Action Button */}
      {buttonTitle && onButtonPress && (
        <View style={styles.buttonContainer}>
          <Button
            title={buttonTitle}
            onPress={onButtonPress}
            variant="outline"
            size="medium"
            fullWidth={false}
          />
        </View>
      )}
    </View>
  );
};

// --------------------------------------------
// STYLES
// --------------------------------------------

const styles = StyleSheet.create({
  container: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    padding: 40,
    minHeight: 300,
  },

  iconContainer: {
    marginBottom: 20,
  },

  emoji: {
    fontSize: 64,
    marginBottom: 20,
  },

  title: {
    fontSize: 18,
    fontWeight: '600',
    color: COLORS.textPrimary,
    textAlign: 'center',
    marginBottom: 8,
  },

  subtitle: {
    fontSize: 14,
    color: COLORS.textSecondary,
    textAlign: 'center',
    lineHeight: 20,
    paddingHorizontal: 20,
  },

  buttonContainer: {
    marginTop: 24,
  },
});

export default EmptyState;