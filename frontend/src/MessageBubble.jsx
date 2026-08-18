import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import './MessageBubble.css';

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
          <div className="typing-indicator">
            <span className="typing-dot" />
            <span className="typing-dot" />
            <span className="typing-dot" />
          </div>
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
