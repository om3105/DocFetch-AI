import { useState } from 'react';
import { useAuth } from './AuthContext';
import './LoginPage.css';

export default function LoginPage() {
  const { login, loginWithEmail, registerWithEmail } = useAuth();
  const [mode, setMode] = useState('login'); // 'login' | 'register'
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(false);

  async function handleGoogleLogin() {
    try {
      setError(null);
      await login();
    } catch (err) {
      console.error('Login failed:', err.message);
      setError('Google sign-in failed. Please try again.');
    }
  }

  async function handleSubmit(e) {
    e.preventDefault();
    if (!email || !password) {
      setError('Please enter both email and password.');
      return;
    }
    if (mode === 'register' && password.length < 6) {
      setError('Password must be at least 6 characters.');
      return;
    }

    setLoading(true);
    setError(null);
    try {
      if (mode === 'register') {
        await registerWithEmail(email.trim(), password, name.trim());
      } else {
        await loginWithEmail(email.trim(), password);
      }
    } catch (err) {
      console.error('Auth action failed:', err.message);
      setError(err.message || 'Authentication failed. Please verify credentials.');
    } finally {
      setLoading(false);
    }
  }

  function toggleMode() {
    setMode((prev) => (prev === 'login' ? 'register' : 'login'));
    setError(null);
  }

  return (
    <div className="docfetch-login-overlay">
      <div className="docfetch-login-card">
        {/* Cosmic Blue Top Header */}
        <div className="cosmic-header font-sans">
          <div className="cosmic-orbit-glow" />
          <span className="cosmic-sub">
            {mode === 'login' ? 'Log in to' : 'Sign up for'}
          </span>
          <h2 className="cosmic-title">Chat with DocFetch AI for Free</h2>
        </div>

        {/* Main Card Body */}
        <div className="login-body">
          {/* Mode Switcher Tabs */}
          <div className="auth-tab-bar">
            <button 
              type="button" 
              className={`auth-tab ${mode === 'login' ? 'active' : ''}`}
              onClick={() => { setMode('login'); setError(null); }}
            >
              Log In
            </button>
            <button 
              type="button" 
              className={`auth-tab ${mode === 'register' ? 'active' : ''}`}
              onClick={() => { setMode('register'); setError(null); }}
            >
              Register
            </button>
          </div>

          {/* Google Sign-in Button */}
          <button type="button" className="docfetch-google-btn" onClick={handleGoogleLogin}>
            <svg className="google-svg" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
              <path d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z" fill="#4285F4" />
              <path d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" fill="#34A853" />
              <path d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z" fill="#FBBC05" />
              <path d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" fill="#EA4335" />
            </svg>
            <span>Continue with Google</span>
          </button>

          {/* Divider Line */}
          <div className="login-divider">
            <span className="divider-line" />
            <span className="divider-text">OR</span>
            <span className="divider-line" />
          </div>

          {/* Email & Password Form Section */}
          <form className="email-login-form" onSubmit={handleSubmit}>
            <div className="form-heading">
              {mode === 'login' ? 'Log in with email and password' : 'Create your new account'}
            </div>

            {error && <div className="login-error-msg">{error}</div>}

            {mode === 'register' && (
              <div className="input-group">
                <input
                  type="text"
                  className="form-input"
                  placeholder="Full Name"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  required
                />
              </div>
            )}

            <div className="input-group">
              <input
                type="email"
                className="form-input"
                placeholder="Email address"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
              />
            </div>

            <div className="input-group password-group">
              <input
                type={showPassword ? 'text' : 'password'}
                className="form-input"
                placeholder={mode === 'register' ? 'Password (min. 6 characters)' : 'Password'}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
              />
              <button
                type="button"
                className="toggle-password-btn"
                onClick={() => setShowPassword(!showPassword)}
                tabIndex={-1}
              >
                <span className="material-symbols-outlined">
                  {showPassword ? 'visibility_off' : 'visibility'}
                </span>
              </button>
            </div>

            {/* Submit Button */}
            <button type="submit" className="docfetch-submit-btn" disabled={loading}>
              {loading
                ? (mode === 'login' ? 'Logging in...' : 'Registering...')
                : (mode === 'login' ? 'Log In' : 'Register Account')}
            </button>
          </form>

          {/* Account Mode Switcher Link */}
          <div className="mode-switch-row">
            <span>
              {mode === 'login' ? "Don't have an account?" : 'Already have an account?'}
            </span>
            <button type="button" className="switch-mode-link" onClick={toggleMode}>
              {mode === 'login' ? 'Register' : 'Log In'}
            </button>
          </div>

          {/* Footer Terms Agreement */}
          <div className="login-terms-footer">
            Agree to <a href="#terms">Terms of Service</a> and <a href="#privacy">Privacy Policy</a>
          </div>
        </div>
      </div>
    </div>
  );
}


