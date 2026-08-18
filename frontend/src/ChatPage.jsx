import { useState, useRef, useEffect, useCallback } from 'react';
import MessageBubble from './MessageBubble';
import DocumentUpload from './DocumentUpload';
import { useAuth } from './AuthContext';
import {
  createChat, fetchChats, fetchChatMessages, sendChatMessage,
  renameChat, deleteChat, fetchModels, switchModel, sendQuery,
} from './api';
import './ChatPage.css';

const MODEL_LABELS = {
  groq: 'Qwen 2.5 27B · Groq',
  gemini: 'Gemini 2.5 Flash · Google',
};

export default function ChatPage() {
  const { user, logout } = useAuth();

  // ── Conversation state ────────────────────────────────────────────────
  const [conversations, setConversations] = useState([]);
  const [activeChatId, setActiveChatId] = useState(null);
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [chatsLoading, setChatsLoading] = useState(true);

  // ── UI state ──────────────────────────────────────────────────────────
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [uploadedFiles, setUploadedFiles] = useState([]);
  const [activeModel, setActiveModel] = useState('groq');
  const [modelMenuOpen, setModelMenuOpen] = useState(false);
  const [modelSwitching, setModelSwitching] = useState(false);
  const [profileMenuOpen, setProfileMenuOpen] = useState(false);
  const [uploadModalOpen, setUploadModalOpen] = useState(false);
  const [editingChatId, setEditingChatId] = useState(null);
  const [editTitle, setEditTitle] = useState('');
  const [contextMenuChatId, setContextMenuChatId] = useState(null);
  const [contextMenuPos, setContextMenuPos] = useState({ x: 0, y: 0 });
  const [knowledgeExpanded, setKnowledgeExpanded] = useState(false);
  const [theme, setTheme] = useState(() => {
    return localStorage.getItem('app-theme') || 'dark';
  });

  const messagesEndRef = useRef(null);
  const inputRef = useRef(null);
  const modelMenuRef = useRef(null);
  const profileMenuRef = useRef(null);
  const editInputRef = useRef(null);

  // ── Theme sync ────────────────────────────────────────────────────────
  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme);
    document.documentElement.className = theme;
    localStorage.setItem('app-theme', theme);
  }, [theme]);

  // ── Scroll to bottom ─────────────────────────────────────────────────
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, loading]);

  useEffect(() => {
    inputRef.current?.focus();
  }, [activeChatId]);

  // ── Load conversations on mount ───────────────────────────────────────
  const loadConversations = useCallback(async () => {
    try {
      setChatsLoading(true);
      const data = await fetchChats();
      setConversations(data.chats || []);
    } catch (err) {
      console.error('Failed to load conversations:', err);
    } finally {
      setChatsLoading(false);
    }
  }, []);

  useEffect(() => {
    loadConversations();
  }, [loadConversations]);

  // ── Fetch models on mount ─────────────────────────────────────────────
  useEffect(() => {
    fetchModels()
      .then((data) => setActiveModel(data.active || 'groq'))
      .catch(() => {});
  }, []);

  // ── Close dropdowns on outside click ──────────────────────────────────
  useEffect(() => {
    function handleClick(e) {
      if (modelMenuRef.current && !modelMenuRef.current.contains(e.target)) {
        setModelMenuOpen(false);
      }
      if (profileMenuRef.current && !profileMenuRef.current.contains(e.target)) {
        setProfileMenuOpen(false);
      }
      // Close context menu on any click
      setContextMenuChatId(null);
    }
    document.addEventListener('mousedown', handleClick);
    return () => document.removeEventListener('mousedown', handleClick);
  }, []);

  // ── Focus rename input when editing ───────────────────────────────────
  useEffect(() => {
    if (editingChatId && editInputRef.current) {
      editInputRef.current.focus();
      editInputRef.current.select();
    }
  }, [editingChatId]);

  // ── Handlers ──────────────────────────────────────────────────────────

  function handleThemeChange(newTheme) {
    setTheme(newTheme);
  }

  async function handleSwitchModel(modelId) {
    if (modelId === activeModel || modelSwitching) return;
    setModelSwitching(true);
    try {
      await switchModel(modelId);
      setActiveModel(modelId);
    } catch (err) {
      console.error('Model switch failed:', err);
    } finally {
      setModelSwitching(false);
      setModelMenuOpen(false);
    }
  }

  /** Create a new conversation and switch to it. */
  async function handleNewChat() {
    try {
      const chat = await createChat();
      setConversations((prev) => [chat, ...prev]);
      setActiveChatId(chat.id);
      setMessages([]);
      inputRef.current?.focus();
    } catch (err) {
      console.error('Failed to create chat:', err);
    }
  }

  /** Load a conversation's messages and switch to it. */
  async function handleSelectChat(chatId) {
    if (chatId === activeChatId) return;
    setActiveChatId(chatId);
    setMessages([]);
    try {
      const data = await fetchChatMessages(chatId);
      setMessages(
        (data.messages || []).map((m) => ({
          role: m.role,
          content: m.content,
        }))
      );
    } catch (err) {
      console.error('Failed to load messages:', err);
    }
  }

  /** Send a message in the active conversation. */
  async function handleSend(e) {
    e?.preventDefault();
    const query = input.trim();
    if (!query || loading) return;

    // 1. Clear input & push user message to UI immediately for instant feedback
    setInput('');
    setMessages((prev) => [...prev, { role: 'user', content: query }]);
    setLoading(true);

    // 2. Ensure active conversation ID exists
    let chatId = activeChatId;
    if (!chatId) {
      try {
        const chat = await createChat();
        chatId = chat.id;
        setConversations((prev) => [chat, ...prev]);
        setActiveChatId(chatId);
      } catch (err) {
        console.warn('Backend createChat failed, using fallback session:', err);
        chatId = 'temp_' + Date.now();
        setActiveChatId(chatId);
      }
    }

    // 3. Send message & process AI response
    try {
      const result = await sendChatMessage(chatId, query);
      setMessages((prev) => [
        ...prev,
        { role: 'assistant', content: result.ai_message?.content || result.result?.content || 'No response.' },
      ]);

      // Update conversation title if auto-generated
      if (result.generated_title) {
        setConversations((prev) =>
          prev.map((c) =>
            c.id === chatId ? { ...c, title: result.generated_title } : c
          )
        );
      }

      // Move this conversation to top of list
      setConversations((prev) => {
        const updated = prev.find((c) => c.id === chatId);
        if (!updated) return prev;
        return [
          { ...updated, updated_at: new Date().toISOString() },
          ...prev.filter((c) => c.id !== chatId),
        ];
      });
    } catch (err) {
      console.error('sendChatMessage error, attempting legacy sendQuery fallback:', err);
      try {
        const legacyResponse = await sendQuery(query, user?.uid || 'anonymous');
        setMessages((prev) => [
          ...prev,
          { role: 'assistant', content: legacyResponse },
        ]);
      } catch (legacyErr) {
        setMessages((prev) => [
          ...prev,
          { role: 'assistant', content: '⚠️ Failed to get a response. Please check server connectivity.' },
        ]);
      }
    } finally {
      setLoading(false);
      inputRef.current?.focus();
    }
  }

  /** Handle right-click on conversation for context menu. */
  function handleContextMenu(e, chatId) {
    e.preventDefault();
    setContextMenuChatId(chatId);
    setContextMenuPos({ x: e.clientX, y: e.clientY });
  }

  /** Start renaming a conversation. */
  function handleStartRename(chatId) {
    const chat = conversations.find((c) => c.id === chatId);
    setEditingChatId(chatId);
    setEditTitle(chat?.title || '');
    setContextMenuChatId(null);
  }

  /** Submit rename. */
  async function handleSubmitRename(chatId) {
    const trimmed = editTitle.trim();
    if (!trimmed) {
      setEditingChatId(null);
      return;
    }
    try {
      await renameChat(chatId, trimmed);
      setConversations((prev) =>
        prev.map((c) => (c.id === chatId ? { ...c, title: trimmed } : c))
      );
    } catch (err) {
      console.error('Rename failed:', err);
    }
    setEditingChatId(null);
  }

  /** Delete a conversation. */
  async function handleDeleteChat(chatId) {
    setContextMenuChatId(null);
    try {
      await deleteChat(chatId);
      setConversations((prev) => prev.filter((c) => c.id !== chatId));
      if (activeChatId === chatId) {
        setActiveChatId(null);
        setMessages([]);
      }
    } catch (err) {
      console.error('Delete failed:', err);
    }
  }

  function handleUploadSuccess(fileName) {
    setUploadedFiles((prev) => [...prev, fileName]);
    setUploadModalOpen(false);
  }

  function handleKeyDown(e) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  }

  function setInputAndFocus(text) {
    setInput(text);
    inputRef.current?.focus();
  }

  const userInitials = user?.displayName
    ? user.displayName.split(' ').map((n) => n[0]).join('').substring(0, 2).toUpperCase()
    : (user?.email ? user.email.substring(0, 2).toUpperCase() : 'DF');

  const showHero = !activeChatId && messages.length === 0;

  return (
    <div className="docfetch-app-container">
      {/* Left Sidebar */}
      <aside className={`docfetch-sidebar ${sidebarOpen ? 'expanded' : 'collapsed'}`}>
        {/* Sidebar Header */}
        <div className="sidebar-header">
          <div className="docfetch-logo-badge">DF</div>
          <span className="sidebar-brand-name">DocFetch AI</span>
          <button 
            className="sidebar-toggle-btn" 
            onClick={() => setSidebarOpen(!sidebarOpen)}
            title="Toggle Sidebar"
          >
            <span className="material-symbols-outlined">dock_to_right</span>
          </button>
        </div>

        {/* Action Buttons */}
        <div className="sidebar-actions">
          <button className="docfetch-new-chat-btn" onClick={handleNewChat}>
            <span className="material-symbols-outlined">add</span>
            <span>New Chat</span>
            <span className="shortcut-badge">⌘ K</span>
          </button>

          <button className="upload-doc-btn" onClick={() => setUploadModalOpen(true)}>
            <span className="material-symbols-outlined">cloud_upload</span>
            <span>Upload Document</span>
          </button>
        </div>

        {/* Conversations List */}
        <div className="sidebar-section chats-section">
          <div className="section-heading">Conversations</div>
          {chatsLoading ? (
            <div className="sync-hint">Loading chats...</div>
          ) : conversations.length === 0 ? (
            <div className="sync-hint">No conversations yet</div>
          ) : (
            <div className="conversation-list">
              {conversations.map((chat) => (
                <div
                  key={chat.id}
                  className={`chat-history-item ${chat.id === activeChatId ? 'active' : ''}`}
                  onClick={() => handleSelectChat(chat.id)}
                  onContextMenu={(e) => handleContextMenu(e, chat.id)}
                >
                  <span className="material-symbols-outlined">chat_bubble_outline</span>
                  {editingChatId === chat.id ? (
                    <input
                      ref={editInputRef}
                      className="rename-input"
                      value={editTitle}
                      onChange={(e) => setEditTitle(e.target.value)}
                      onBlur={() => handleSubmitRename(chat.id)}
                      onKeyDown={(e) => {
                        if (e.key === 'Enter') handleSubmitRename(chat.id);
                        if (e.key === 'Escape') setEditingChatId(null);
                      }}
                      onClick={(e) => e.stopPropagation()}
                    />
                  ) : (
                    <span className="chat-title">{chat.title}</span>
                  )}

                  {/* Inline action buttons (hover) */}
                  {editingChatId !== chat.id && (
                    <div className="chat-item-actions">
                      <button
                        className="chat-action-btn"
                        onClick={(e) => { e.stopPropagation(); handleStartRename(chat.id); }}
                        title="Rename"
                      >
                        <span className="material-symbols-outlined">edit</span>
                      </button>
                      <button
                        className="chat-action-btn danger"
                        onClick={(e) => { e.stopPropagation(); handleDeleteChat(chat.id); }}
                        title="Delete"
                      >
                        <span className="material-symbols-outlined">delete</span>
                      </button>
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Knowledge Base Documents (collapsed) */}
        <div className="sidebar-section knowledge-section">
          <button
            className="section-heading-toggle"
            onClick={() => setKnowledgeExpanded(!knowledgeExpanded)}
          >
            <span className="material-symbols-outlined toggle-chevron">
              {knowledgeExpanded ? 'expand_more' : 'chevron_right'}
            </span>
            <span>Knowledge Base</span>
            {uploadedFiles.length > 0 && (
              <span className="knowledge-count">{uploadedFiles.length}</span>
            )}
          </button>
          {knowledgeExpanded && (
            <div className="knowledge-list">
              {uploadedFiles.length === 0 ? (
                <div className="sync-hint">No documents uploaded yet</div>
              ) : (
                uploadedFiles.map((name, i) => (
                  <div key={i} className="chat-history-item">
                    <span className="material-symbols-outlined">description</span>
                    <span className="chat-title">{name}</span>
                  </div>
                ))
              )}
            </div>
          )}
        </div>

        {/* Sidebar Footer User Profile */}
        <div className="sidebar-footer" ref={profileMenuRef}>
          <button className="user-profile-btn" onClick={() => setProfileMenuOpen(!profileMenuOpen)}>
            <div className="avatar-circle">{userInitials}</div>
            <span className="user-name">{user?.displayName || user?.email || 'User Account'}</span>
          </button>

          {/* Profile & Theme Popover Menu */}
          {profileMenuOpen && (
            <div className="profile-popover">
              <div className="popover-user-info">
                <div className="avatar-circle large">{userInitials}</div>
                <div className="popover-user-details">
                  <span className="popover-name">{user?.displayName || 'User Account'}</span>
                  <span className="popover-email">{user?.email || 'user@docfetch.ai'}</span>
                </div>
              </div>
              <div className="popover-divider" />
              <div className="theme-toggle-row">
                <span className="theme-label">Theme</span>
                <div className="theme-pills">
                  <button 
                    className={`theme-pill ${theme === 'light' ? 'active' : ''}`}
                    onClick={() => handleThemeChange('light')}
                  >
                    Light
                  </button>
                  <button 
                    className={`theme-pill ${theme === 'dark' ? 'active' : ''}`}
                    onClick={() => handleThemeChange('dark')}
                  >
                    Dark
                  </button>
                </div>
              </div>
              <div className="popover-divider" />
              <button className="popover-item danger" onClick={logout}>
                <span className="material-symbols-outlined">logout</span>
                Sign Out
              </button>
            </div>
          )}
        </div>
      </aside>

      {/* Toggle Sidebar Trigger (when collapsed) */}
      {!sidebarOpen && (
        <button 
          className="floating-sidebar-trigger" 
          onClick={() => setSidebarOpen(true)}
          title="Open Sidebar"
        >
          <span className="material-symbols-outlined">dock_to_right</span>
        </button>
      )}

      {/* Main Canvas Area */}
      <main className="docfetch-main-canvas">
        {showHero ? (
          <div className="docfetch-hero-container">
            {/* Centered Logo Header */}
            <h1 className="docfetch-giant-logo">DOCFETCH AI</h1>

            {/* Central Main Input Container */}
            <div className="docfetch-central-input-box">
              <form onSubmit={handleSend}>
                <textarea
                  ref={inputRef}
                  className="docfetch-textarea"
                  placeholder="Ask DocFetch AI anything or upload a document..."
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  onKeyDown={handleKeyDown}
                  rows={2}
                  disabled={loading}
                />

                {/* Model Selector Toggle */}
                <div className="model-badge-trigger-wrap" ref={modelMenuRef}>
                  <button 
                    type="button" 
                    className="model-badge-btn"
                    onClick={() => setModelMenuOpen(!modelMenuOpen)}
                  >
                    <span className="badge-text">{MODEL_LABELS[activeModel].split(' · ')[0]}</span>
                  </button>

                  {modelMenuOpen && (
                    <div className="model-select-popover">
                      {Object.keys(MODEL_LABELS).map((id) => (
                        <button
                          key={id}
                          type="button"
                          className={`model-option ${id === activeModel ? 'active' : ''}`}
                          onClick={() => handleSwitchModel(id)}
                        >
                          {MODEL_LABELS[id]}
                        </button>
                      ))}
                    </div>
                  )}
                </div>

                {/* Bottom Input Actions */}
                <div className="input-bottom-actions">
                  <button 
                    type="button" 
                    className="attach-btn" 
                    onClick={() => setUploadModalOpen(true)}
                    title="Upload File to Knowledge Base"
                  >
                    <span className="material-symbols-outlined">add</span>
                  </button>

                  <button 
                    type="submit" 
                    className="send-up-btn" 
                    disabled={!input.trim() || loading}
                    title="Send"
                  >
                    <span className="material-symbols-outlined">arrow_upward</span>
                  </button>
                </div>
              </form>
            </div>

            {/* Clean Quick Action Prompts */}
            <div className="docfetch-pill-filters">
              <button className="tool-pill" onClick={() => setInputAndFocus('Summarize key findings from uploaded documents')}>
                <span className="material-symbols-outlined">description</span>
                <span>Summarize Document</span>
              </button>
              <button className="tool-pill" onClick={() => setInputAndFocus('Perform in-depth analysis across indexed knowledge')}>
                <span className="material-symbols-outlined">biotech</span>
                <span>Deep Research</span>
              </button>
              <button className="tool-pill" onClick={() => setInputAndFocus('Retrieve latest relevant information')}>
                <span className="material-symbols-outlined">language</span>
                <span>Web Knowledge</span>
              </button>
            </div>
          </div>
        ) : (
          /* Active Chat Flow */
          <div className="chat-messages-container">
            <div className="messages-flow">
              {messages.map((msg, i) => (
                <MessageBubble key={i} role={msg.role} content={msg.content} />
              ))}
              {loading && <MessageBubble role="assistant" isTyping />}
              <div ref={messagesEndRef} />
            </div>

            {/* Sticky Chat Input Bar */}
            <div className="active-chat-input-bar">
              <form onSubmit={handleSend} className="active-input-form">
                <button 
                  type="button" 
                  className="attach-btn" 
                  onClick={() => setUploadModalOpen(true)}
                  title="Upload File"
                >
                  <span className="material-symbols-outlined">add</span>
                </button>
                <input
                  ref={inputRef}
                  className="active-text-input"
                  placeholder="Ask DocFetch AI anything..."
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  onKeyDown={handleKeyDown}
                  disabled={loading}
                />
                <button 
                  type="submit" 
                  className="send-up-btn" 
                  disabled={!input.trim() || loading}
                  title="Send"
                >
                  <span className="material-symbols-outlined">arrow_upward</span>
                </button>
              </form>
            </div>
          </div>
        )}
      </main>

      {/* Context Menu */}
      {contextMenuChatId && (
        <div
          className="context-menu-overlay"
          onClick={() => setContextMenuChatId(null)}
        >
          <div
            className="context-menu"
            style={{ top: contextMenuPos.y, left: contextMenuPos.x }}
            onClick={(e) => e.stopPropagation()}
          >
            <button className="context-menu-item" onClick={() => handleStartRename(contextMenuChatId)}>
              <span className="material-symbols-outlined">edit</span>
              Rename
            </button>
            <button className="context-menu-item danger" onClick={() => handleDeleteChat(contextMenuChatId)}>
              <span className="material-symbols-outlined">delete</span>
              Delete
            </button>
          </div>
        </div>
      )}

      {/* Document Upload Modal */}
      {uploadModalOpen && (
        <div className="modal-backdrop" onClick={() => setUploadModalOpen(false)}>
          <div className="modal-card" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h3>Upload Document to DocFetch AI Workspace</h3>
              <button onClick={() => setUploadModalOpen(false)}>
                <span className="material-symbols-outlined">close</span>
              </button>
            </div>
            <DocumentUpload onUploadSuccess={handleUploadSuccess} />
          </div>
        </div>
      )}
    </div>
  );
}
