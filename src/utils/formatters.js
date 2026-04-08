// ============================================
// DEALHUNT APP - DATA FORMATTERS
// ============================================

const ISO_NO_TZ_RE = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?$/;
const SQL_NO_TZ_RE = /^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}(?:\.\d+)?$/;

const normalizeApiDateInput = (value) => {
  if (!value) return null;
  if (value instanceof Date) return value;
  if (typeof value !== 'string') return value;

  const trimmed = value.trim();
  if (!trimmed) return null;

  // Backend often sends naive UTC timestamps. Add Z so JS parses as UTC,
  // then renders correctly in local time (IST on device).
  if (ISO_NO_TZ_RE.test(trimmed)) {
    return `${trimmed}Z`;
  }

  if (SQL_NO_TZ_RE.test(trimmed)) {
    return `${trimmed.replace(' ', 'T')}Z`;
  }

  return trimmed;
};

export const parseApiDate = (value) => {
  try {
    const normalized = normalizeApiDateInput(value);
    if (!normalized) return null;
    const date = normalized instanceof Date ? normalized : new Date(normalized);
    return Number.isFinite(date.getTime()) ? date : null;
  } catch {
    return null;
  }
};

export const toEpochMs = (value) => {
  const date = parseApiDate(value);
  return date ? date.getTime() : 0;
};

/**
 * Format price to Indian currency (₹)
 * Handles both number and Decimal string types from backend
 * 
 * @param {number|string} price - Price value
 * @returns {string} Formatted price (₹12,999)
 */
export const formatPrice = (price) => {
  if (price === null || price === undefined || price === '') {
    return '₹0';
  }

  try {
    const numPrice = typeof price === 'string' ? parseFloat(price) : price;

    if (isNaN(numPrice)) {
      return '₹0';
    }

    // Format with Indian locale (₹ with comma separators)
    return new Intl.NumberFormat('en-IN', {
      style: 'currency',
      currency: 'INR',
      minimumFractionDigits: 0,
      maximumFractionDigits: 0,
    }).format(numPrice);
  } catch (error) {
    console.warn('Format price error:', error, 'value:', price);
    return '₹0';
  }
};

/**
 * Format date string to readable format
 * 
 * @param {string|Date} dateString - ISO date string or Date object
 * @returns {string} Formatted date (Jan 15, 2024)
 */
export const formatDate = (dateString) => {
  if (!dateString) {
    return '';
  }

  try {
    const date = parseApiDate(dateString);
    if (!date) {
      return '';
    }

    return new Intl.DateTimeFormat('en-IN', {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
    }).format(date);
  } catch (error) {
    console.warn('Format date error:', error, 'value:', dateString);
    return '';
  }
};

/**
 * Calculate discount percentage between original and current price
 * 
 * @param {number|string} originalPrice - Original/list price
 * @param {number|string} currentPrice - Current/selling price
 * @returns {number} Discount percentage (0-100)
 */
export const calculateDiscount = (originalPrice, currentPrice) => {
  try {
    const original = typeof originalPrice === 'string'
      ? parseFloat(originalPrice)
      : originalPrice;
    const current = typeof currentPrice === 'string'
      ? parseFloat(currentPrice)
      : currentPrice;

    if (!original || !current || original <= 0) {
      return 0;
    }

    const discount = ((original - current) / original) * 100;
    return Math.max(0, Math.min(100, Math.round(discount)));
  } catch (error) {
    console.warn('Calculate discount error:', error);
    return 0;
  }
};

/**
 * Pick a single coherent listing for UI price display.
 * Prevents mixing best_price from one listing with original_price from another.
 */
export const getDisplayListingForPrice = (product) => {
  const listings = Array.isArray(product?.listings) ? product.listings : [];
  if (listings.length === 0) return null;

  const bestPrice = parsePrice(product?.best_price);
  const bestPlatform = String(product?.best_platform || '').toLowerCase();

  const candidates = listings.filter((l) => parsePrice(l?.current_price) > 0);
  if (candidates.length === 0) return listings[0];

  const platformCandidates = bestPlatform
    ? candidates.filter((l) => String(l?.platform || '').toLowerCase() === bestPlatform)
    : [];

  const pool = platformCandidates.length > 0 ? platformCandidates : candidates;

  return pool
    .slice()
    .sort((a, b) => {
      const aPrice = parsePrice(a?.current_price);
      const bPrice = parsePrice(b?.current_price);
      const aDelta = Math.abs(aPrice - bestPrice);
      const bDelta = Math.abs(bPrice - bestPrice);
      if (aDelta !== bDelta) return aDelta - bDelta;
      return bPrice - aPrice;
    })[0];
};

/**
 * Abbreviate large numbers for display
 * 1200 → "1.2k", 1500000 → "1.5M"
 * 
 * @param {number} num - Number to abbreviate
 * @returns {string} Abbreviated number
 */
export const abbreviateNumber = (num) => {
  if (!num || num <= 0) return '0';

  const abs = Math.abs(num);

  if (abs >= 1000000) {
    return (num / 1000000).toFixed(1).replace(/\.0$/, '') + 'M';
  }

  if (abs >= 1000) {
    return (num / 1000).toFixed(1).replace(/\.0$/, '') + 'k';
  }

  return num.toString();
};

/**
 * Get platform badge color and display name
 * 
 * @param {string} platform - Platform name (amazon, flipkart, etc)
 * @returns {Object} { color: string, name: string, icon: string }
 */
export const getPlatformBadge = (platform) => {
  const badges = {
    amazon: {
      color: '#FF9900',
      name: 'Amazon',
      icon: '🔵',
    },
    flipkart: {
      color: '#4169E1',
      name: 'Flipkart',
      icon: '🟦',
    },
    meesho: {
      color: '#FF6652',
      name: 'Meesho',
      icon: '🔴',
    },
    myntra: {
      color: '#FF5722',
      name: 'Myntra',
      icon: '🧡',
    },
    nykaa: {
      color: '#D81B60',
      name: 'Nykaa',
      icon: '💄',
    },
    croma: {
      color: '#FF0000',
      name: 'Croma',
      icon: '🔴',
    },
  };

  return badges[platform?.toLowerCase()] || {
    color: '#666666',
    name: platform || 'Unknown',
    icon: '📦',
  };
};

/**
 * Extract display data from product object
 * Handles variations in API response structure
 * 
 * @param {Object} product - Product object from API
 * @returns {Object} Standardized display object
 */
export const getProductDisplayData = (product) => {
  if (!product) {
    return {
      id: '',
      title: 'Unknown Product',
      price: '₹0',
      originalPrice: null,
      discount: 0,
      imageUrl: null,
      platforms: [],
      bestPlatform: 'Unknown',
      rating: null,
      inStock: false,
      // ✅ New variant fields
      variant_fingerprint: null,
      base_fingerprint: null,
      variant_type: null,
      storage_gb: null,
      color: null,
      condition: null,
    };
  }

  // Try to get title from different locations
  const displayListing = getDisplayListingForPrice(product) || product.listings?.[0] || null;

  const title =
    displayListing?.title ||
    product.ai_generated_essence ||
    product.title ||
    'Unknown Product';

  // Try to get image from different locations
  const imageUrl =
    displayListing?.image_url ||
    product.image_url ||
    null;

  // Extract available platforms from listings
  const platforms =
    product.listings?.map((l) => l.platform) || [];

  // Get best price
  const bestPrice = product.best_price || 0;
  const originalPriceRaw = displayListing?.original_price;
  const originalPrice = parsePrice(originalPriceRaw) > parsePrice(bestPrice) ? originalPriceRaw : null;

  return {
    id: product.id || product.product_id || '',
    title,
    price: formatPrice(bestPrice),
    priceRaw: bestPrice,
    originalPrice: originalPrice ? formatPrice(originalPrice) : null,
    discount: calculateDiscount(originalPrice, bestPrice),
    imageUrl,
    platforms,
    bestPlatform:
      getPlatformBadge(product.best_platform).name ||
      'Unknown',
    rating: displayListing?.rating ? parseFloat(displayListing.rating) : null,
    reviewCount: displayListing?.review_count || 0,
    inStock:
      displayListing?.in_stock ||
      product.in_stock ||
      false,
    tags: product.ai_tags || [],
    specs: product.ai_extracted_specs || {},
    // ✅ NEW: Variant fingerprinting and specification fields
    variant_fingerprint: product.variant_fingerprint || null,
    base_fingerprint: product.base_fingerprint || null,
    variant_type: product.variant_type || null,
    storage_gb: product.storage_gb || null,
    color: product.color || null,
    condition: product.condition || null,
  };
};

/**
 * Format trending product for display
 * 
 * @param {Object} trendingProduct - Trending product from API
 * @returns {Object} Display object
 */
export const formatTrendingProduct = (trendingProduct) => {
  if (!trendingProduct) return null;

  return {
    id: trendingProduct.product_id,
    title: trendingProduct.title,
    price: formatPrice(trendingProduct.best_price),
    priceRaw: trendingProduct.best_price,
    discount: trendingProduct.discount_percentage || 0,
    imageUrl: trendingProduct.image_url,
    platform: trendingProduct.best_platform,
    searchCount: abbreviateNumber(trendingProduct.search_count),
    rank: trendingProduct.rank,
    // ✅ NEW: Variant fingerprinting for cross-platform deduplication
    variant_fingerprint: trendingProduct.variant_fingerprint || null,
    base_fingerprint: trendingProduct.base_fingerprint || null,
    variant_type: trendingProduct.variant_type || null,
  };
};

/**
 * Format variant info for product display
 * ✅ NEW: Create variant description from available fields
 * 
 * @param {Object} product - Product object
 * @returns {string} Formatted variant string (e.g., "256GB Black, New")
 */
export const formatVariantInfo = (product) => {
  if (!product) return '';
  
  const parts = [];
  
  // Add storage
  if (product.storage_gb) {
    parts.push(`${product.storage_gb}GB`);
  }
  
  // Add color
  if (product.color) {
    parts.push(product.color);
  }
  
  // Add condition
  if (product.condition && product.condition !== 'new') {
    parts.push(capitalize(product.condition));
  }
  
  return parts.length > 0 ? parts.join(', ') : '';
};

/**
 * Get variant type badge (Pro, Plus, Max, etc)
 * ✅ NEW: Display variant type prominently
 * 
 * @param {string} variantType - Variant type from API
 * @returns {Object} { label: string, color: string }
 */
export const getVariantBadge = (variantType) => {
  if (!variantType) return { label: '', color: '' };
  
  const badges = {
    pro: { label: '⭐ Pro', color: '#FF6B6B' },
    plus: { label: '➕ Plus', color: '#4ECDC4' },
    max: { label: '🔝 Max', color: '#45B7D1' },
    ultra: { label: '✨ Ultra', color: '#F7B731' },
    lite: { label: '💡 Lite', color: '#95E1D3' },
  };
  
  return badges[variantType?.toLowerCase()] || { label: '', color: '' };
};

/**
 * Capitalize first letter of string
 * 
 * @param {string} str - String to capitalize
 * @returns {string} Capitalized string
 */
const capitalize = (str) => {
  if (!str) return '';
  return str.charAt(0).toUpperCase() + str.slice(1).toLowerCase();
};

/**
 * Format price history for Victory chart
 * 
 * @param {Object} priceHistory - Price history response
 * @returns {Array} Array of { x, y } for charting
 */
export const formatPriceHistoryForChart = (priceHistory) => {
  if (!priceHistory || !priceHistory.history) {
    return [];
  }

  return priceHistory.history.map((point) => ({
    x: formatDate(point.date),
    y: parseFloat(point.price),
    date: new Date(point.date),
  }));
};
export const parsePrice = (value) => {
  if (value === null || value === undefined) return 0;
  if (typeof value === 'number') return value;
  const cleaned = String(value).replace(/[₹,\s]/g, '');
  const num = parseFloat(cleaned);
  return isNaN(num) ? 0 : num;
};

/**
 * Get platform display name
 */
export const getPlatformName = (platform) => {
  return getPlatformBadge(platform).name;
};

/**
 * Get platform brand color
 */
export const getPlatformColor = (platform) => {
  return getPlatformBadge(platform).color;
};

/**
 * Truncate text with ellipsis
 */
export const truncateText = (text, maxLength = 50) => {
  if (!text || text.length <= maxLength) return text || '';
  return text.substring(0, maxLength).trim() + '...';
};

/**
 * Format date to short format (Jan 15)
 */
export const formatShortDate = (dateString) => {
  if (!dateString) return '';
  try {
    const date = parseApiDate(dateString);
    if (!date) return '';
    return new Intl.DateTimeFormat('en-IN', {
      month: 'short',
      day: 'numeric',
    }).format(date);
  } catch {
    return '';
  }
};

/**
 * Format relative time (2h ago, 3d ago)
 */
export const formatTimeAgo = (dateString) => {
  if (!dateString) return 'Recently';
  try {
    const date = parseApiDate(dateString);
    if (!date) return 'Recently';
    const now = new Date();
    const diffMs = now - date;
    const diffMin = Math.floor(diffMs / 60000);
    const diffHr = Math.floor(diffMin / 60);
    const diffDay = Math.floor(diffHr / 24);

    if (diffMin < 1) return 'Just now';
    if (diffMin < 60) return `${diffMin}m ago`;
    if (diffHr < 24) return `${diffHr}h ago`;
    if (diffDay < 30) return `${diffDay}d ago`;
    return formatShortDate(dateString);
  } catch {
    return 'Recently';
  }
};

export default {
  formatPrice,
  parsePrice,
  formatDate,
  formatShortDate,
  formatTimeAgo,
  calculateDiscount,
  abbreviateNumber,
  getPlatformBadge,
  getDisplayListingForPrice,
  getPlatformName,
  getPlatformColor,
  truncateText,
  getProductDisplayData,
  formatTrendingProduct,
  formatPriceHistoryForChart,
  formatVariantInfo,
  getVariantBadge,
};
