// ============================================
// DEALHUNT APP - URL SEARCH SCREEN
// ============================================

import React, { useState, useCallback } from 'react';
import {
  View,
  Text,
  StyleSheet,
  TextInput,
  TouchableOpacity,
  Alert,
  Clipboard,
  ActivityIndicator,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useNavigation } from '@react-navigation/native';
import { useDispatch, useSelector } from 'react-redux';
import { Ionicons } from '@expo/vector-icons';

// Redux
import {
  searchByUrl,
  selectIsUrlSearching,
  selectUrlSearchError,
} from '../../store/searchSlice';

// Utils
import { COLORS } from '../../utils/constants';
import { getPlatformName, getPlatformColor } from '../../utils/formatters';

// Supported platforms
const SUPPORTED_PLATFORMS = [
  { key: 'amazon', name: 'Amazon', domain: 'amazon.in' },
  { key: 'flipkart', name: 'Flipkart', domain: 'flipkart.com' },
  { key: 'meesho', name: 'Meesho', domain: 'meesho.com' },
  { key: 'myntra', name: 'Myntra', domain: 'myntra.com' },
  { key: 'nykaa', name: 'Nykaa', domain: 'nykaa.com' },
  { key: 'croma', name: 'Croma', domain: 'croma.com' },
];

// --------------------------------------------
// URL SEARCH SCREEN COMPONENT
// --------------------------------------------

const URLSearchScreen = () => {
  const navigation = useNavigation();
  const dispatch = useDispatch();

  // Redux state
  const isSearching = useSelector(selectIsUrlSearching);
  const searchError = useSelector(selectUrlSearchError);

  // Local state
  const [url, setUrl] = useState('');
  const [detectedPlatform, setDetectedPlatform] = useState(null);

  // Detect platform from URL
  const detectPlatform = useCallback((inputUrl) => {
    const lowercaseUrl = inputUrl.toLowerCase();
    
    for (const platform of SUPPORTED_PLATFORMS) {
      if (lowercaseUrl.includes(platform.domain)) {
        setDetectedPlatform(platform.key);
        return;
      }
    }
    
    setDetectedPlatform(null);
  }, []);

  // Handle URL change
  const handleUrlChange = (text) => {
    setUrl(text);
    detectPlatform(text);
  };

  // Handle paste from clipboard
  const handlePaste = async () => {
    try {
      const clipboardContent = await Clipboard.getString();
      if (clipboardContent) {
        setUrl(clipboardContent);
        detectPlatform(clipboardContent);
      }
    } catch (error) {
      console.log('Clipboard read error:', error);
    }
  };

  // Handle search
  const handleSearch = async () => {
    if (!url.trim()) {
      Alert.alert('Error', 'Please enter a product URL');
      return;
    }

    if (!detectedPlatform) {
      Alert.alert(
        'Unsupported URL',
        'Please paste a URL from Amazon, Flipkart, Meesho, Myntra, Nykaa, or Croma.'
      );
      return;
    }

    try {
      const result = await dispatch(searchByUrl(url.trim())).unwrap();
      const productId =
        result?.product_id ||
        result?.source?.product_id ||
        result?.product?.product_id ||
        result?.product?.id;

      if (productId) {
        navigation.navigate('ProductDetail', {
          productId,
        });
      } else {
        Alert.alert(
          'Product Found',
          'We extracted the URL, but product details are still syncing. Please try again in a moment.'
        );
      }
    } catch (error) {
      const message =
        typeof error === 'string'
          ? error
          : error?.message || 'Failed to extract product from URL';
      Alert.alert('Error', message);
    }
  };

  // Handle clear
  const handleClear = () => {
    setUrl('');
    setDetectedPlatform(null);
  };

  return (
    <SafeAreaView style={styles.container} edges={['top']}>
      {/* Header */}
      <View style={styles.header}>
        <TouchableOpacity
          style={styles.backButton}
          onPress={() => navigation.goBack()}
        >
          <Ionicons name="arrow-back" size={24} color={COLORS.textPrimary} />
        </TouchableOpacity>
        <Text style={styles.headerTitle}>Paste Product URL</Text>
        <View style={styles.headerRight} />
      </View>

      {/* Content */}
      <View style={styles.content}>
        {/* URL Input */}
        <View style={styles.inputContainer}>
          <View style={styles.inputWrapper}>
            <Ionicons name="link-outline" size={20} color={COLORS.gray400} />
            <TextInput
              style={styles.input}
              value={url}
              onChangeText={handleUrlChange}
              placeholder="Paste product link here..."
              placeholderTextColor={COLORS.gray400}
              autoCapitalize="none"
              autoCorrect={false}
              multiline
              numberOfLines={3}
            />
            {url.length > 0 && (
              <TouchableOpacity onPress={handleClear}>
                <Ionicons name="close-circle" size={20} color={COLORS.gray400} />
              </TouchableOpacity>
            )}
          </View>

          {/* Paste Button */}
          <TouchableOpacity style={styles.pasteButton} onPress={handlePaste}>
            <Ionicons name="clipboard-outline" size={18} color={COLORS.primary} />
            <Text style={styles.pasteButtonText}>Paste</Text>
          </TouchableOpacity>
        </View>

        {/* Platform Detection */}
        {detectedPlatform && (
          <View style={styles.detectedPlatform}>
            <Ionicons name="checkmark-circle" size={18} color={COLORS.success} />
            <Text style={styles.detectedText}>
              Detected: <Text style={{ color: getPlatformColor(detectedPlatform), fontWeight: '600' }}>
                {getPlatformName(detectedPlatform)}
              </Text>
            </Text>
          </View>
        )}

        {/* Search Button */}
        <TouchableOpacity
          style={[
            styles.searchButton,
            (!url.trim() || !detectedPlatform) && styles.searchButtonDisabled,
          ]}
          onPress={handleSearch}
          disabled={!url.trim() || !detectedPlatform || isSearching}
        >
          {isSearching ? (
            <ActivityIndicator size="small" color={COLORS.white} />
          ) : (
            <>
              <Ionicons name="search" size={20} color={COLORS.white} />
              <Text style={styles.searchButtonText}>Find Product</Text>
            </>
          )}
        </TouchableOpacity>

        {/* Supported Platforms */}
        <View style={styles.platformsSection}>
          <Text style={styles.platformsTitle}>Supported Platforms</Text>
          <View style={styles.platformsGrid}>
            {SUPPORTED_PLATFORMS.map((platform) => (
              <View key={platform.key} style={styles.platformItem}>
                <View
                  style={[
                    styles.platformDot,
                    { backgroundColor: getPlatformColor(platform.key) },
                  ]}
                />
                <Text style={styles.platformName}>{platform.name}</Text>
              </View>
            ))}
          </View>
        </View>

        {/* Instructions */}
        <View style={styles.instructions}>
          <Text style={styles.instructionsTitle}>How to use:</Text>
          <Text style={styles.instructionStep}>
            1. Go to Amazon, Flipkart, or any supported platform
          </Text>
          <Text style={styles.instructionStep}>
            2. Find the product you want to compare
          </Text>
          <Text style={styles.instructionStep}>
            3. Copy the product page URL
          </Text>
          <Text style={styles.instructionStep}>
            4. Paste it here and tap "Find Product"
          </Text>
        </View>
      </View>
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

  header: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: 16,
    paddingVertical: 12,
    borderBottomWidth: 1,
    borderBottomColor: COLORS.gray100,
    backgroundColor: COLORS.white,
  },

  backButton: {
    padding: 4,
  },

  headerTitle: {
    fontSize: 17,
    fontWeight: '600',
    color: COLORS.textPrimary,
  },

  headerRight: {
    width: 32,
  },

  content: {
    flex: 1,
    padding: 20,
  },

  inputContainer: {
    marginBottom: 16,
  },

  inputWrapper: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    backgroundColor: COLORS.white,
    borderRadius: 12,
    borderWidth: 1,
    borderColor: COLORS.gray200,
    padding: 14,
    minHeight: 80,
  },

  input: {
    flex: 1,
    fontSize: 15,
    color: COLORS.textPrimary,
    marginLeft: 10,
    marginRight: 10,
    paddingTop: 0,
    textAlignVertical: 'top',
  },

  pasteButton: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: COLORS.primaryLight + '30',
    paddingVertical: 12,
    borderRadius: 10,
    marginTop: 12,
  },

  pasteButtonText: {
    fontSize: 14,
    fontWeight: '600',
    color: COLORS.primary,
    marginLeft: 6,
  },

  detectedPlatform: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: COLORS.successLight,
    padding: 12,
    borderRadius: 10,
    marginBottom: 16,
  },

  detectedText: {
    fontSize: 14,
    color: COLORS.textPrimary,
    marginLeft: 8,
  },

  searchButton: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: COLORS.primary,
    paddingVertical: 16,
    borderRadius: 12,
    marginBottom: 24,
  },

  searchButtonDisabled: {
    backgroundColor: COLORS.gray300,
  },

  searchButtonText: {
    fontSize: 16,
    fontWeight: '600',
    color: COLORS.white,
    marginLeft: 8,
  },

  platformsSection: {
    marginBottom: 24,
  },

  platformsTitle: {
    fontSize: 14,
    fontWeight: '600',
    color: COLORS.textPrimary,
    marginBottom: 12,
  },

  platformsGrid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
  },

  platformItem: {
    flexDirection: 'row',
    alignItems: 'center',
    width: '50%',
    paddingVertical: 8,
  },

  platformDot: {
    width: 8,
    height: 8,
    borderRadius: 4,
    marginRight: 8,
  },

  platformName: {
    fontSize: 13,
    color: COLORS.textSecondary,
  },

  instructions: {
    backgroundColor: COLORS.gray50,
    padding: 16,
    borderRadius: 12,
  },

  instructionsTitle: {
    fontSize: 14,
    fontWeight: '600',
    color: COLORS.textPrimary,
    marginBottom: 10,
  },

  instructionStep: {
    fontSize: 13,
    color: COLORS.textSecondary,
    lineHeight: 22,
  },
});

export default URLSearchScreen;