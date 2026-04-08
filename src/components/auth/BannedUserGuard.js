import React, { useEffect } from 'react';
import { useSelector, useDispatch } from 'react-redux';
import { Alert } from 'react-native';
import { selectBanInfo, selectIsAuthenticated } from '../../store/authSlice';
import { resetAuth } from '../../store/authSlice';

const BannedUserGuard = ({ children }) => {
  const banInfo = useSelector(selectBanInfo);
  const isAuthenticated = useSelector(selectIsAuthenticated);
  const dispatch = useDispatch();

  useEffect(() => {
    // Check if user is banned and authenticated
    if (isAuthenticated && banInfo?.isBanned) {
      console.log('[BannedUserGuard] User is banned, showing alert and redirecting');
      
      // Show alert to user
      Alert.alert(
        'Account Suspended',
        banInfo.message || 'Your account has been suspended due to a violation of our terms of service.',
        [
          {
            text: 'OK',
            onPress: () => {
              // Clear auth state and redirect to login
              dispatch(resetAuth());
            },
          },
        ]
      );
    }
  }, [banInfo, isAuthenticated, dispatch]);

  // If user is banned, don't render children
  if (banInfo?.isBanned) {
    return null;
  }

  return children;
};

export default BannedUserGuard;
