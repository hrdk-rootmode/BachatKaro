// ============================================
// DEALHUNT APP - FILTER MODAL
// ============================================

import React, { useState, useEffect } from 'react';
import {
  View,
  Text,
  StyleSheet,
  Modal,
  TouchableOpacity,
  ScrollView,
  Switch,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import Slider from '@react-native-community/slider';

import Button from '../../components/common/Button';
import { COLORS } from '../../utils/constants';
import { formatPrice, getPlatformName, getPlatformColor } from '../../utils/formatters';

// All supported platforms
const ALL_PLATFORMS = [
  'amazon',
  'flipkart',
  'meesho',
  'myntra',
  'nykaa',
  'croma',
];

/**
 * Filter modal for search results
 * 
 * @param {boolean} visible - Modal visibility
 * @param {function} onClose - Close handler
 * @param {Object} filters - Current filter values
 * @param {function} onApply - Apply filters handler
 */
const FilterModal = ({ visible, onClose, filters, onApply }) => {
  // Local state for filter values
  const [minPrice, setMinPrice] = useState(filters?.minPrice || 0);
  const [maxPrice, setMaxPrice] = useState(filters?.maxPrice || 100000);
  const [selectedPlatforms, setSelectedPlatforms] = useState(
    filters?.platforms || ALL_PLATFORMS
  );
  const [inStockOnly, setInStockOnly] = useState(filters?.inStockOnly || false);

  // Reset local state when modal opens
  useEffect(() => {
    if (visible) {
      setMinPrice(filters?.minPrice || 0);
      setMaxPrice(filters?.maxPrice || 100000);
      setSelectedPlatforms(filters?.platforms || ALL_PLATFORMS);
      setInStockOnly(filters?.inStockOnly || false);
    }
  }, [visible, filters]);

  // Toggle platform selection
  const togglePlatform = (platform) => {
    setSelectedPlatforms((prev) => {
      if (prev.includes(platform)) {
        // Don't allow deselecting all platforms
        if (prev.length === 1) return prev;
        return prev.filter((p) => p !== platform);
      } else {
        return [...prev, platform];
      }
    });
  };

  // Select all platforms
  const selectAllPlatforms = () => {
    setSelectedPlatforms(ALL_PLATFORMS);
  };

  // Clear all filters
  const clearFilters = () => {
    setMinPrice(0);
    setMaxPrice(100000);
    setSelectedPlatforms(ALL_PLATFORMS);
    setInStockOnly(false);
  };

  // Apply filters and close
  const handleApply = () => {
    onApply?.({
      minPrice,
      maxPrice,
      platforms: selectedPlatforms,
      inStockOnly,
    });
    onClose?.();
  };

  return (
    <Modal
      visible={visible}
      animationType="slide"
      transparent={true}
      onRequestClose={onClose}
    >
      <View style={styles.overlay}>
        <View style={styles.modalContainer}>
          <SafeAreaView style={styles.safeArea} edges={['bottom']}>
            {/* Header */}
            <View style={styles.header}>
              <Text style={styles.headerTitle}>Filters</Text>
              <TouchableOpacity onPress={onClose} style={styles.closeButton}>
                <Ionicons name="close" size={24} color={COLORS.textPrimary} />
              </TouchableOpacity>
            </View>

            {/* Content */}
            <ScrollView style={styles.content} showsVerticalScrollIndicator={false}>
              {/* Price Range Section */}
              <View style={styles.section}>
                <Text style={styles.sectionTitle}>Price Range</Text>
                
                <View style={styles.priceDisplay}>
                  <Text style={styles.priceText}>{formatPrice(minPrice)}</Text>
                  <Text style={styles.priceDivider}>-</Text>
                  <Text style={styles.priceText}>{formatPrice(maxPrice)}</Text>
                </View>

                {/* Min Price Slider */}
                <View style={styles.sliderContainer}>
                  <Text style={styles.sliderLabel}>Min Price</Text>
                  <Slider
                    style={styles.slider}
                    minimumValue={0}
                    maximumValue={100000}
                    step={1000}
                    value={minPrice}
                    onValueChange={(value) => {
                      if (value < maxPrice) setMinPrice(value);
                    }}
                    minimumTrackTintColor={COLORS.primary}
                    maximumTrackTintColor={COLORS.gray300}
                    thumbTintColor={COLORS.primary}
                  />
                </View>

                {/* Max Price Slider */}
                <View style={styles.sliderContainer}>
                  <Text style={styles.sliderLabel}>Max Price</Text>
                  <Slider
                    style={styles.slider}
                    minimumValue={0}
                    maximumValue={100000}
                    step={1000}
                    value={maxPrice}
                    onValueChange={(value) => {
                      if (value > minPrice) setMaxPrice(value);
                    }}
                    minimumTrackTintColor={COLORS.primary}
                    maximumTrackTintColor={COLORS.gray300}
                    thumbTintColor={COLORS.primary}
                  />
                </View>
              </View>

              {/* Platforms Section */}
              <View style={styles.section}>
                <View style={styles.sectionHeader}>
                  <Text style={styles.sectionTitle}>Platforms</Text>
                  <TouchableOpacity onPress={selectAllPlatforms}>
                    <Text style={styles.selectAllText}>Select All</Text>
                  </TouchableOpacity>
                </View>

                <View style={styles.platformsGrid}>
                  {ALL_PLATFORMS.map((platform) => {
                    const isSelected = selectedPlatforms.includes(platform);
                    return (
                      <TouchableOpacity
                        key={platform}
                        style={[
                          styles.platformChip,
                          isSelected && {
                            backgroundColor: getPlatformColor(platform) + '20',
                            borderColor: getPlatformColor(platform),
                          },
                        ]}
                        onPress={() => togglePlatform(platform)}
                      >
                        <Ionicons
                          name={isSelected ? 'checkmark-circle' : 'ellipse-outline'}
                          size={18}
                          color={isSelected ? getPlatformColor(platform) : COLORS.gray400}
                        />
                        <Text
                          style={[
                            styles.platformChipText,
                            isSelected && { color: getPlatformColor(platform) },
                          ]}
                        >
                          {getPlatformName(platform)}
                        </Text>
                      </TouchableOpacity>
                    );
                  })}
                </View>
              </View>

              {/* In Stock Toggle */}
              <View style={styles.section}>
                <View style={styles.toggleRow}>
                  <View>
                    <Text style={styles.sectionTitle}>In Stock Only</Text>
                    <Text style={styles.toggleDescription}>
                      Show only products currently in stock
                    </Text>
                  </View>
                  <Switch
                    value={inStockOnly}
                    onValueChange={setInStockOnly}
                    trackColor={{ false: COLORS.gray300, true: COLORS.primaryLight }}
                    thumbColor={inStockOnly ? COLORS.primary : COLORS.white}
                  />
                </View>
              </View>
            </ScrollView>

            {/* Footer Actions */}
            <View style={styles.footer}>
              <Button
                title="Clear All"
                onPress={clearFilters}
                variant="outline"
                style={styles.clearButton}
              />
              <Button
                title="Apply Filters"
                onPress={handleApply}
                variant="primary"
                style={styles.applyButton}
              />
            </View>
          </SafeAreaView>
        </View>
      </View>
    </Modal>
  );
};

// --------------------------------------------
// STYLES
// --------------------------------------------

const styles = StyleSheet.create({
  overlay: {
    flex: 1,
    backgroundColor: 'rgba(0,0,0,0.5)',
    justifyContent: 'flex-end',
  },

  modalContainer: {
    backgroundColor: COLORS.white,
    borderTopLeftRadius: 20,
    borderTopRightRadius: 20,
    maxHeight: '80%',
  },

  safeArea: {
    flex: 1,
  },

  header: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingHorizontal: 20,
    paddingVertical: 16,
    borderBottomWidth: 1,
    borderBottomColor: COLORS.gray100,
  },

  headerTitle: {
    fontSize: 18,
    fontWeight: '600',
    color: COLORS.textPrimary,
  },

  closeButton: {
    padding: 4,
  },

  content: {
    flex: 1,
    paddingHorizontal: 20,
  },

  section: {
    paddingVertical: 20,
    borderBottomWidth: 1,
    borderBottomColor: COLORS.gray100,
  },

  sectionHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 16,
  },

  sectionTitle: {
    fontSize: 16,
    fontWeight: '600',
    color: COLORS.textPrimary,
    marginBottom: 16,
  },

  selectAllText: {
    fontSize: 14,
    color: COLORS.primary,
    fontWeight: '500',
  },

  priceDisplay: {
    flexDirection: 'row',
    justifyContent: 'center',
    alignItems: 'center',
    backgroundColor: COLORS.gray50,
    borderRadius: 12,
    padding: 16,
    marginBottom: 20,
  },

  priceText: {
    fontSize: 18,
    fontWeight: '700',
    color: COLORS.primary,
  },

  priceDivider: {
    fontSize: 18,
    color: COLORS.gray400,
    marginHorizontal: 16,
  },

  sliderContainer: {
    marginBottom: 16,
  },

  sliderLabel: {
    fontSize: 12,
    color: COLORS.textSecondary,
    marginBottom: 8,
  },

  slider: {
    width: '100%',
    height: 40,
  },

  platformsGrid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    marginTop: -8,
  },

  platformChip: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 12,
    paddingVertical: 10,
    borderRadius: 20,
    borderWidth: 1,
    borderColor: COLORS.gray300,
    marginRight: 10,
    marginTop: 10,
  },

  platformChipText: {
    fontSize: 14,
    color: COLORS.gray600,
    marginLeft: 6,
    fontWeight: '500',
  },

  toggleRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },

  toggleDescription: {
    fontSize: 12,
    color: COLORS.textSecondary,
    marginTop: 4,
  },

  footer: {
    flexDirection: 'row',
    paddingHorizontal: 20,
    paddingVertical: 16,
    borderTopWidth: 1,
    borderTopColor: COLORS.gray100,
    gap: 12,
  },

  clearButton: {
    flex: 1,
  },

  applyButton: {
    flex: 1,
  },
});

export default FilterModal;