import { useEffect, useState } from 'react';
import { wakeServer } from './api';

const MESSAGES = {
  slow: 'Starting the DocFetch server… this can take up to a minute after a quiet period.',
  down: "Can't reach the DocFetch server right now. Please try again in a few minutes.",
};

/** Wakes the backend on page load and shows a notice only if it is slow to answer. */
export default function ServerWakeBanner() {
  const [status, setStatus] = useState('checking'); // 'checking' | 'slow' | 'ready' | 'down'

  useEffect(() => {
    let cancelled = false;
    // An awake server answers well within 3 s, so most visitors never see the notice
    const slowTimer = setTimeout(() => {
      if (!cancelled) setStatus((s) => (s === 'checking' ? 'slow' : s));
    }, 3000);
    wakeServer().then((ok) => {
      if (!cancelled) setStatus(ok ? 'ready' : 'down');
    });
    return () => {
      cancelled = true;
      clearTimeout(slowTimer);
    };
  }, []);

  if (!MESSAGES[status]) return null;

  return (
    <div
      role="status"
      style={{
        position: 'fixed',
        bottom: '16px',
        left: '50%',
        transform: 'translateX(-50%)',
        zIndex: 1000,
        maxWidth: 'calc(100% - 32px)',
        padding: '10px 16px',
        borderRadius: '999px',
        background: 'rgba(20, 20, 30, 0.92)',
        border: '1px solid rgba(255,255,255,0.12)',
        color: 'rgba(255,255,255,0.85)',
        fontSize: '14px',
        textAlign: 'center',
      }}
    >
      {MESSAGES[status]}
    </div>
  );
}
