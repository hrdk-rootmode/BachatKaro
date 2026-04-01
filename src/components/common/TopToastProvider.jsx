import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react';
import {
  Animated,
  Easing,
  Platform,
  StatusBar,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';

const TopToastContext = createContext({
  showToast: () => {},
  hideToast: () => {},
});

const TOP_OFFSET = Platform.OS === 'android'
  ? (StatusBar.currentHeight || 0)
  : 42;

const LEFT_DEPTH = 5;
const RIGHT_DEPTH = 6;
const FACE_THICKNESS = 4;
const HINGE_OFFSET = 24;

const TYPE_STYLES = {
  success: {
    bg: '#E6F9EF',
    border: '#16A34A',
    text: '#14532D',
    topFace: '#D2F0E1',
    bottomFace: '#B6E5CC',
    leftFace: '#CCEEDC',
    rightFace: '#B0DFC8',
    icon: 'checkmark-circle',
    iconColor: '#039855',
    title: 'Done',
  },
  warning: {
    bg: '#FFF4D6',
    border: '#D97706',
    text: '#7C2D12',
    topFace: '#FEE8B8',
    bottomFace: '#F7D587',
    leftFace: '#FBE3AC',
    rightFace: '#F2CD7D',
    icon: 'warning',
    iconColor: '#B54708',
    title: 'Heads up',
  },
  error: {
    bg: '#FEE8E8',
    border: '#DC2626',
    text: '#7F1D1D',
    topFace: '#FAD2D2',
    bottomFace: '#F4B5B5',
    leftFace: '#F7CDCD',
    rightFace: '#EEB0B0',
    icon: 'alert-circle',
    iconColor: '#D92D20',
    title: 'Error',
  },
  info: {
    bg: '#E7F0FF',
    border: '#2563EB',
    text: '#1E3A8A',
    topFace: '#D7E5FF',
    bottomFace: '#B8D2FF',
    leftFace: '#D2E2FF',
    rightFace: '#AFCBFF',
    icon: 'information-circle',
    iconColor: '#175CD3',
    title: 'Info',
  },
};

export const useTopToast = () => useContext(TopToastContext);

export const TopToastProvider = ({ children }) => {
  const motion = useRef(new Animated.Value(0)).current;
  const hideTimerRef = useRef(null);

  const [toast, setToast] = useState({
    visible: false,
    type: 'info',
    title: '',
    message: '',
  });

  const hideToast = useCallback(() => {
    if (hideTimerRef.current) {
      clearTimeout(hideTimerRef.current);
      hideTimerRef.current = null;
    }

    Animated.sequence([
      // Tiny forward lean, then reverse flip back to hidden top face.
      Animated.timing(motion, {
        toValue: 1.03,
        duration: 95,
        easing: Easing.out(Easing.quad),
        useNativeDriver: false,
      }),
      Animated.timing(motion, {
        toValue: 0,
        duration: 320,
        easing: Easing.in(Easing.cubic),
        useNativeDriver: false,
      }),
    ]).start(({ finished }) => {
      if (finished) {
        setToast((prev) => ({ ...prev, visible: false }));
      }
    });
  }, [motion]);

  const showToast = useCallback((payload = {}) => {
    const message = String(payload?.message || '').trim();
    if (!message) return;

    const type = TYPE_STYLES[payload?.type] ? payload.type : 'info';
    const style = TYPE_STYLES[type];
    const title = String(payload?.title || style.title || '').trim();
    const duration = Math.min(5000, Math.max(3000, Number(payload?.duration || 3800)));

    if (hideTimerRef.current) {
      clearTimeout(hideTimerRef.current);
      hideTimerRef.current = null;
    }

    motion.stopAnimation();

    motion.setValue(0);

    setToast({
      visible: true,
      type,
      title,
      message,
    });

    Animated.sequence([
      // Face-flip drop from hidden top face into front face.
      Animated.timing(motion, {
        toValue: 1.04,
        duration: 420,
        easing: Easing.bezier(0.18, 0.88, 0.22, 1),
        useNativeDriver: false,
      }),
      // Small settle so it feels like a rigid block.
      Animated.spring(motion, {
        toValue: 1,
        friction: 9,
        tension: 115,
        useNativeDriver: false,
      }),
    ]).start();

    hideTimerRef.current = setTimeout(() => {
      hideToast();
    }, duration);
  }, [hideToast, motion]);

  useEffect(() => {
    return () => {
      if (hideTimerRef.current) {
        clearTimeout(hideTimerRef.current);
      }
    };
  }, []);

  const contextValue = useMemo(() => ({ showToast, hideToast }), [hideToast, showToast]);
  const activeStyle = TYPE_STYLES[toast.type] || TYPE_STYLES.info;

  const translateY = motion.interpolate({
    inputRange: [0, 0.7, 1, 1.04],
    outputRange: [-110, -22, 0, 4],
    extrapolate: 'clamp',
  });

  const rotateX = motion.interpolate({
    inputRange: [0, 0.7, 1, 1.04],
    outputRange: ['-94deg', '-26deg', '0deg', '5deg'],
    extrapolate: 'clamp',
  });

  const opacity = motion.interpolate({
    inputRange: [0, 0.2, 1],
    outputRange: [0.05, 0.9, 1],
    extrapolate: 'clamp',
  });

  const shadowOpacity = motion.interpolate({
    inputRange: [0, 1],
    outputRange: [0.01, 0.2],
    extrapolate: 'clamp',
  });

  const shadowRadius = motion.interpolate({
    inputRange: [0, 1],
    outputRange: [1, 14],
    extrapolate: 'clamp',
  });

  const elevation = motion.interpolate({
    inputRange: [0, 1],
    outputRange: [1, 9],
    extrapolate: 'clamp',
  });

  const faceOpacity = motion.interpolate({
    inputRange: [0, 0.35, 1],
    outputRange: [0.9, 0.55, 0.3],
    extrapolate: 'clamp',
  });

  return (
    <TopToastContext.Provider value={contextValue}>
      {children}

      {toast.visible && (
        <Animated.View
          pointerEvents="none"
          style={[
            styles.container,
            {
              top: TOP_OFFSET,
              transform: [
                { perspective: 1200 },
                { translateY },
                { translateY: -HINGE_OFFSET },
                { rotateX },
                { translateY: HINGE_OFFSET },
              ],
              opacity,
              backgroundColor: activeStyle.bg,
              borderBottomColor: activeStyle.border,
              shadowOpacity,
              shadowRadius,
              elevation,
            },
          ]}
        >
          <Animated.View
            pointerEvents="none"
            style={[
              styles.topFace,
              {
                backgroundColor: activeStyle.topFace,
                opacity: faceOpacity,
              },
            ]}
          />
          <Animated.View
            pointerEvents="none"
            style={[
              styles.bottomFace,
              {
                backgroundColor: activeStyle.bottomFace,
                opacity: faceOpacity,
              },
            ]}
          />
          <Animated.View
            pointerEvents="none"
            style={[
              styles.leftFace,
              {
                backgroundColor: activeStyle.leftFace,
                opacity: faceOpacity,
              },
            ]}
          />
          <Animated.View
            pointerEvents="none"
            style={[
              styles.rightFace,
              {
                backgroundColor: activeStyle.rightFace,
                opacity: faceOpacity,
              },
            ]}
          />

          <View style={styles.iconWrap}>
            <Ionicons name={activeStyle.icon} size={20} color={activeStyle.iconColor} />
          </View>

          <View style={styles.textWrap}>
            {!!toast.title && (
              <Text style={[styles.title, { color: activeStyle.text }]} numberOfLines={1}>
                {toast.title}
              </Text>
            )}
            <Text style={[styles.message, { color: activeStyle.text }]} numberOfLines={3}>
              {toast.message}
            </Text>
          </View>
        </Animated.View>
      )}
    </TopToastContext.Provider>
  );
};

const styles = StyleSheet.create({
  container: {
    position: 'absolute',
    left: LEFT_DEPTH,
    right: RIGHT_DEPTH,
    zIndex: 9999,
    borderRadius: 0,
    borderWidth: 0,
    borderBottomWidth: 2,
    paddingHorizontal: 16,
    paddingVertical: 10,
    flexDirection: 'row',
    alignItems: 'flex-start',
    overflow: 'visible',
    shadowColor: '#111827',
    shadowOffset: { width: 0, height: 8 },
  },
  topFace: {
    position: 'absolute',
    left: -LEFT_DEPTH,
    right: -RIGHT_DEPTH,
    top: -FACE_THICKNESS,
    height: FACE_THICKNESS,
  },
  bottomFace: {
    position: 'absolute',
    left: -LEFT_DEPTH,
    right: -RIGHT_DEPTH,
    bottom: -FACE_THICKNESS,
    height: FACE_THICKNESS,
  },
  leftFace: {
    position: 'absolute',
    left: -LEFT_DEPTH,
    top: 0,
    bottom: 0,
    width: LEFT_DEPTH,
  },
  rightFace: {
    position: 'absolute',
    right: -RIGHT_DEPTH,
    top: 0,
    bottom: 0,
    width: RIGHT_DEPTH,
  },
  iconWrap: {
    marginTop: 1,
    marginRight: 10,
  },
  textWrap: {
    flex: 1,
  },
  title: {
    fontSize: 13,
    fontWeight: '800',
    marginBottom: 2,
  },
  message: {
    fontSize: 12.5,
    lineHeight: 17,
    fontWeight: '600',
  },
});

export default TopToastProvider;