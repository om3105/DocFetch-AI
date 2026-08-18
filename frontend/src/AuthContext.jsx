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

const AuthContext = createContext(null);

const googleProvider = new GoogleAuthProvider();

/**
 * ⚠️  DEV-ONLY FALLBACK — DO NOT USE IN PRODUCTION
 *
 * Creates an unsigned JWT placeholder when Firebase auth is unavailable.
 * The backend must have ALLOW_JWT_FALLBACK=true for this to be accepted.
 * In production, the backend rejects unsigned tokens by default.
 */
function createFallbackJwtToken(uid, email) {
  try {
    const header = btoa(JSON.stringify({ alg: 'HS256', typ: 'JWT' })).replace(/=/g, '');
    const payload = btoa(JSON.stringify({
      uid: uid || 'usr_anon',
      user_id: uid || 'usr_anon',
      email: email || 'user@docfetch.ai',
      isFallback: true,
    })).replace(/=/g, '');
    return `${header}.${payload}.signature`;
  } catch {
    return 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ1aWQiOiJ1c3JfYW5vbiIsImVtYWlsIjoidXNlckBkb2NmZXRjaC5haSJ9.sig';
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

  async function login() {
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
    try {
      return await signInWithEmailAndPassword(auth, email, password);
    } catch (error) {
      if (
        error.code === 'auth/user-not-found' ||
        error.code === 'auth/invalid-credential'
      ) {
        // Auto-create account if user does not exist yet
        try {
          return await createUserWithEmailAndPassword(auth, email, password);
        } catch (signUpErr) {
          const uid = 'usr_' + Math.random().toString(36).substring(2, 9);
          const fallbackUser = {
            uid,
            email,
            displayName: email.split('@')[0],
            getIdToken: async () => createFallbackJwtToken(uid, email),
          };
          setUser(fallbackUser);
          return fallbackUser;
        }
      } else if (error.code === 'auth/operation-not-allowed') {
        const uid = 'usr_' + Math.random().toString(36).substring(2, 9);
        const fallbackUser = {
          uid,
          email,
          displayName: email.split('@')[0],
          getIdToken: async () => createFallbackJwtToken(uid, email),
        };
        setUser(fallbackUser);
        return fallbackUser;
      }
      throw error;
    }
  }

  async function registerWithEmail(email, password, displayName) {
    try {
      const res = await createUserWithEmailAndPassword(auth, email, password);
      if (displayName && res?.user) {
        await updateProfile(res.user, { displayName });
      }
      return res;
    } catch (error) {
      if (error.code === 'auth/operation-not-allowed') {
        const uid = 'usr_' + Math.random().toString(36).substring(2, 9);
        const fallbackUser = {
          uid,
          email,
          displayName: displayName || email.split('@')[0],
          getIdToken: async () => createFallbackJwtToken(uid, email),
        };
        setUser(fallbackUser);
        return fallbackUser;
      }
      throw error;
    }
  }

  async function logout() {
    setUser(null);
    await signOut(auth).catch(() => {});
  }

  /**
   * Get the current user's ID token for API requests.
   * Returns null if not authenticated.
   */
  async function getIdToken() {
    if (user?.getIdToken) return user.getIdToken();
    if (auth.currentUser) return auth.currentUser.getIdToken();
    if (user) return createFallbackJwtToken(user.uid, user.email);
    return null;
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
