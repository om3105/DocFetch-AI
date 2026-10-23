import { useEffect, useState } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import './MessageBubble.css';

// After this long, explain the wait (models may be busy and the backend is switching)
const SLOW_REPLY_MS = 8000;

function TypingIndicator() {
  const [slow, setSlow] = useState(false);

  useEffect(() => {
    const timer = setTimeout(() => setSlow(true), SLOW_REPLY_MS);
    return () => clearTimeout(timer);
  }, []);

  return (
    <div>
      <div className="typing-indicator">
        <span className="typing-dot" />
        <span className="typing-dot" />
        <span className="typing-dot" />
      </div>
      {slow && (
        <div className="typing-slow-note">
          Still working — the AI models are busy, so this is taking a little longer.
        </div>
      )}
    </div>
  );
}

export default function MessageBubble({ role, content, isTyping }) {
  const isUser = role === 'user';

  return (
    <div className={`message-row ${isUser ? 'user' : 'assistant'}`}>
      <div className="message-avatar">
        {isUser ? (
          <span className="material-symbols-outlined" style={{ fontSize: '18px', color: '#fff' }}>person</span>
        ) : (
          <span className="material-symbols-outlined" style={{ fontSize: '18px', color: 'var(--accent)' }}>smart_toy</span>
        )}
      </div>
      <div className={`message-bubble ${isUser ? 'user-bubble' : 'assistant-bubble'}`}>
        {isTyping ? (
          <TypingIndicator />
        ) : (
          <div className="message-content markdown-body">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>
              {content || ''}
            </ReactMarkdown>
          </div>
        )}
      </div>
    </div>
  );
}
