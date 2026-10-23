/**
 * Auth context — provides user state and auth actions to all components.
 *
 * Uses signInWithPopup with automatic fallback to signInWithRedirect
 * when popups are blocked (common in embedded browsers / strict settings).
 */
import { createContext, useContext, useEffect, useState } from 'react';
import {
  onAuthStateChanged,
  signInWithPopup,
  signInWithRedirect,
  getRedirectResult,
  GoogleAuthProvider,
  signInWithEmailAndPassword,
  createUserWithEmailAndPassword,
  updateProfile,
  signOut,
} from 'firebase/auth';
import { auth } from './firebase';
import { AUTH_EXPIRED_EVENT } from './api';

const AuthContext = createContext(null);

const googleProvider = new GoogleAuthProvider();

/** Firebase isn't configured (missing VITE_FIREBASE_* env vars). */
function requireAuth() {
  if (!auth) {
    throw new Error('Sign-in is unavailable: Firebase is not configured.');
  }
}

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!auth) {
      setLoading(false);
      return;
    }

    // Safety timeout to prevent black screen if network or Firebase takes too long
    const timeout = setTimeout(() => {
      setLoading(false);
    }, 2000);

    // Check for redirect result on mount
    getRedirectResult(auth).catch(() => {});

    const unsubscribe = onAuthStateChanged(auth, (firebaseUser) => {
      clearTimeout(timeout);
      setUser(firebaseUser);
      setLoading(false);
    });

    return () => {
      clearTimeout(timeout);
      unsubscribe();
    };
  }, []);

  // Sign out when the backend rejects the login (e.g. an expired session)
  useEffect(() => {
    const handleExpired = () => logout();
    window.addEventListener(AUTH_EXPIRED_EVENT, handleExpired);
    return () => window.removeEventListener(AUTH_EXPIRED_EVENT, handleExpired);
  }, []);

  async function login() {
    requireAuth();
    try {
      await signInWithPopup(auth, googleProvider);
    } catch (error) {
      // Fallback to redirect if popup is blocked
      if (
        error.code === 'auth/popup-blocked' ||
        error.code === 'auth/cancelled-popup-request' ||
        error.code === 'auth/popup-closed-by-user'
      ) {
        await signInWithRedirect(auth, googleProvider);
      } else {
        throw error;
      }
    }
  }

  async function loginWithEmail(email, password) {
    requireAuth();
    return signInWithEmailAndPassword(auth, email, password);
  }

  async function registerWithEmail(email, password, displayName) {
    requireAuth();
    const res = await createUserWithEmailAndPassword(auth, email, password);
    if (displayName && res?.user) {
      await updateProfile(res.user, { displayName });
    }
    return res;
  }

  async function logout() {
    setUser(null);
    if (auth) await signOut(auth).catch(() => {});
  }

  /**
   * Get the current user's ID token for API requests.
   * Returns null if not authenticated.
   */
  async function getIdToken() {
    return auth?.currentUser ? auth.currentUser.getIdToken() : null;
  }

  return (
    <AuthContext.Provider value={{ user, loading, login, loginWithEmail, registerWithEmail, logout, getIdToken }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
}
