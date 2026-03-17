// ============================================
// DEALHUNT APP - FIREBASE SERVICE (FIXED)
// ============================================

import { initializeApp, getApps, getApp } from 'firebase/app';
// IMPORT THESE NEW MODULES
import { 
  initializeAuth, 
  getAuth, 
  getReactNativePersistence,
  signInWithEmailAndPassword,
  createUserWithEmailAndPassword,
  signOut,
  sendPasswordResetEmail,
  onAuthStateChanged,
  getIdToken
} from 'firebase/auth';
import ReactNativeAsyncStorage from '@react-native-async-storage/async-storage';

import { FIREBASE_CONFIG } from '../utils/constants';

// --------------------------------------------
// INITIALIZE FIREBASE
// --------------------------------------------

let app;
let auth;

const initializeFirebase = () => {
  try {
    // Check if config is loaded
    if (!FIREBASE_CONFIG.apiKey) {
      console.error('Firebase: Missing API Key! Check .env file');
      return false;
    }

    // Check if Firebase is already initialized
    if (getApps().length === 0) {
      app = initializeApp(FIREBASE_CONFIG);
      
      // Initialize Auth with Persistence (FIXED)
      auth = initializeAuth(app, {
        persistence: getReactNativePersistence(ReactNativeAsyncStorage)
      });
      
      console.log('Firebase: Initialized successfully with Persistence');
    } else {
      app = getApp();
      auth = getAuth(app); // Get existing auth instance
      console.log('Firebase: Using existing app');
    }

    return true;
  } catch (error) {
    console.error('Firebase: Initialization error:', error.message);
    return false;
  }
};

// Initialize on import
initializeFirebase();

// --------------------------------------------
// GET AUTH INSTANCE
// --------------------------------------------

export const getAuthInstance = () => {
  if (!auth) {
    initializeFirebase();
  }
  return auth;
};

// --------------------------------------------
// SIGN IN WITH EMAIL & PASSWORD
// --------------------------------------------

export const signInWithEmail = async (email, password) => {
  try {
    const authInstance = getAuthInstance();
    const userCredential = await signInWithEmailAndPassword(authInstance, email, password);
    const user = userCredential.user;

    // Get Firebase ID token
    const idToken = await getIdToken(user);

    console.log('Firebase: Sign in successful');

    return {
      success: true,
      user: {
        uid: user.uid,
        email: user.email,
        emailVerified: user.emailVerified,
        displayName: user.displayName,
        photoURL: user.photoURL,
      },
      idToken,
    };
  } catch (error) {
    console.error('Firebase: Sign in error:', error.code, error.message);

    let errorMessage = 'Sign in failed. Please try again.';

    switch (error.code) {
      case 'auth/user-not-found':
        errorMessage = 'No account found with this email. Please sign up.';
        break;
      case 'auth/wrong-password':
        errorMessage = 'Incorrect password. Please try again.';
        break;
      case 'auth/invalid-email':
        errorMessage = 'Invalid email address.';
        break;
      case 'auth/user-disabled':
        errorMessage = 'This account has been disabled.';
        break;
      case 'auth/too-many-requests':
        errorMessage = 'Too many failed attempts. Please try again later.';
        break;
      case 'auth/invalid-credential':
        errorMessage = 'Invalid email or password.';
        break;
      default:
        errorMessage = error.message;
    }

    return {
      success: false,
      error: errorMessage,
      code: error.code,
    };
  }
};

// --------------------------------------------
// SIGN UP WITH EMAIL & PASSWORD
// --------------------------------------------

export const signUpWithEmail = async (email, password) => {
  try {
    const authInstance = getAuthInstance();
    const userCredential = await createUserWithEmailAndPassword(authInstance, email, password);
    const user = userCredential.user;

    // Get Firebase ID token
    const idToken = await getIdToken(user);

    console.log('Firebase: Sign up successful');

    return {
      success: true,
      user: {
        uid: user.uid,
        email: user.email,
        emailVerified: user.emailVerified,
        displayName: user.displayName,
        photoURL: user.photoURL,
      },
      idToken,
      isNewUser: true,
    };
  } catch (error) {
    console.error('Firebase: Sign up error:', error.code, error.message);

    let errorMessage = 'Sign up failed. Please try again.';

    switch (error.code) {
      case 'auth/email-already-in-use':
        errorMessage = 'An account with this email already exists.';
        break;
      case 'auth/invalid-email':
        errorMessage = 'Invalid email address.';
        break;
      case 'auth/weak-password':
        errorMessage = 'Password is too weak. Please use a stronger password.';
        break;
      case 'auth/operation-not-allowed':
        errorMessage = 'Email/password accounts are not enabled.';
        break;
      default:
        errorMessage = error.message;
    }

    return {
      success: false,
      error: errorMessage,
      code: error.code,
    };
  }
};

// --------------------------------------------
// SIGN OUT
// --------------------------------------------

export const firebaseSignOut = async () => {
  try {
    const authInstance = getAuthInstance();
    await signOut(authInstance);
    console.log('Firebase: Sign out successful');
    return { success: true };
  } catch (error) {
    console.error('Firebase: Sign out error:', error.message);
    return {
      success: false,
      error: error.message,
    };
  }
};

// --------------------------------------------
// SEND PASSWORD RESET EMAIL
// --------------------------------------------

export const sendResetEmail = async (email) => {
  try {
    const authInstance = getAuthInstance();
    await sendPasswordResetEmail(authInstance, email);
    console.log('Firebase: Password reset email sent');
    return {
      success: true,
      message: 'Password reset email sent. Check your inbox.',
    };
  } catch (error) {
    console.error('Firebase: Password reset error:', error.code, error.message);

    let errorMessage = 'Failed to send reset email.';

    switch (error.code) {
      case 'auth/user-not-found':
        errorMessage = 'No account found with this email.';
        break;
      case 'auth/invalid-email':
        errorMessage = 'Invalid email address.';
        break;
      case 'auth/too-many-requests':
        errorMessage = 'Too many requests. Please try again later.';
        break;
      default:
        errorMessage = error.message;
    }

    return {
      success: false,
      error: errorMessage,
    };
  }
};

// --------------------------------------------
// GET CURRENT USER
// --------------------------------------------

export const getCurrentUser = () => {
  const authInstance = getAuthInstance();
  return authInstance?.currentUser || null;
};

// --------------------------------------------
// GET FRESH ID TOKEN
// --------------------------------------------

export const getFreshIdToken = async (forceRefresh = false) => {
  try {
    const user = getCurrentUser();
    if (!user) {
      return { success: false, error: 'No user logged in' };
    }

    const idToken = await getIdToken(user, forceRefresh);
    return {
      success: true,
      idToken,
    };
  } catch (error) {
    console.error('Firebase: Get token error:', error.message);
    return {
      success: false,
      error: error.message,
    };
  }
};

// --------------------------------------------
// AUTH STATE LISTENER
// --------------------------------------------

export const subscribeToAuthChanges = (callback) => {
  const authInstance = getAuthInstance();
  return onAuthStateChanged(authInstance, callback);
};

// --------------------------------------------
// CHECK IF USER EXISTS (for auto-login)
// --------------------------------------------

export const checkAuthState = () => {
  return new Promise((resolve) => {
    const authInstance = getAuthInstance();
    const unsubscribe = onAuthStateChanged(authInstance, async (user) => {
      unsubscribe(); // Stop listening after first check

      if (user) {
        const idToken = await getIdToken(user);
        resolve({
          isLoggedIn: true,
          user: {
            uid: user.uid,
            email: user.email,
            emailVerified: user.emailVerified,
            displayName: user.displayName,
          },
          idToken,
        });
      } else {
        resolve({
          isLoggedIn: false,
          user: null,
          idToken: null,
        });
      }
    });
  });
};

export default {
  getAuthInstance,
  signInWithEmail,
  signUpWithEmail,
  firebaseSignOut,
  sendResetEmail,
  getCurrentUser,
  getFreshIdToken,
  subscribeToAuthChanges,
  checkAuthState,
};