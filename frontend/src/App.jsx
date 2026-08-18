import { AuthProvider, useAuth } from './AuthContext';
import LoginPage from './LoginPage';
import ChatPage from './ChatPage';

function AppContent() {
  const { user, loading } = useAuth();

  if (loading) {
    return (
      <div style={{
        minHeight: '100vh',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        background: '#0a0a0f',
        color: 'rgba(255,255,255,0.4)',
        fontSize: '16px',
      }}>
        Loading...
      </div>
    );
  }

  return user ? <ChatPage /> : <LoginPage />;
}

export default function App() {
  return (
    <AuthProvider>
      <AppContent />
    </AuthProvider>
  );
}
