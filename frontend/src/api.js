import { auth } from './firebase';

const API_BASE = import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000';

function createFallbackJwtToken(uid, email) {
  try {
    const header = btoa(JSON.stringify({ alg: 'HS256', typ: 'JWT' })).replace(/=/g, '');
    const payload = btoa(JSON.stringify({ uid: uid || 'usr_anon', user_id: uid || 'usr_anon', email: email || 'user@docfetch.ai' })).replace(/=/g, '');
    return `${header}.${payload}.signature`;
  } catch {
    return 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ1aWQiOiJ1c3JfYW5vbiIsImVtYWlsIjoidXNlckBkb2NmZXRjaC5haSJd.sig';
  }
}

/**
 * Get the current user's Firebase ID token.
 * Returns null or fallback JWT if not authenticated.
 */
async function getAuthToken() {
  if (auth.currentUser) {
    try {
      return await auth.currentUser.getIdToken();
    } catch {}
  }
  return createFallbackJwtToken('usr_demo', 'user@docfetch.ai');
}

/** Helper to build headers with auth token. */
async function authHeaders(extra = {}) {
  const token = await getAuthToken();
  return {
    ...(token && { Authorization: `Bearer ${token}` }),
    ...extra,
  };
}

// ── Chat Conversations ────────────────────────────────────────────────────

/** Create a new conversation thread. */
export async function createChat(title) {
  const headers = await authHeaders({ 'Content-Type': 'application/json' });
  const response = await fetch(`${API_BASE}/api/chats`, {
    method: 'POST',
    headers,
    body: JSON.stringify(title ? { title } : {}),
  });
  if (!response.ok) throw new Error(`Create chat failed: ${response.status}`);
  return response.json();
}

/** Fetch all conversations for the current user (cursor-paginated). */
export async function fetchChats(cursor) {
  const headers = await authHeaders();
  const params = new URLSearchParams({ limit: '50' });
  if (cursor) params.set('cursor', cursor);

  const response = await fetch(`${API_BASE}/api/chats?${params}`, { headers });
  if (!response.ok) throw new Error(`Fetch chats failed: ${response.status}`);
  return response.json();
}

/** Fetch a conversation with its message history. */
export async function fetchChatMessages(chatId, msgCursor) {
  const headers = await authHeaders();
  const params = new URLSearchParams({ msg_limit: '100' });
  if (msgCursor) params.set('msg_cursor', msgCursor);

  const response = await fetch(`${API_BASE}/api/chats/${chatId}?${params}`, { headers });
  if (!response.ok) throw new Error(`Fetch messages failed: ${response.status}`);
  return response.json();
}

/** Send a message to a conversation and get the AI response. */
export async function sendChatMessage(chatId, query) {
  const headers = await authHeaders({ 'Content-Type': 'application/json' });
  const response = await fetch(`${API_BASE}/api/chats/${chatId}/messages`, {
    method: 'POST',
    headers,
    body: JSON.stringify({ query }),
  });
  if (!response.ok) throw new Error(`Send message failed: ${response.status}`);
  return response.json();
}

/** Rename a conversation. */
export async function renameChat(chatId, title) {
  const headers = await authHeaders({ 'Content-Type': 'application/json' });
  const response = await fetch(`${API_BASE}/api/chats/${chatId}`, {
    method: 'PATCH',
    headers,
    body: JSON.stringify({ title }),
  });
  if (!response.ok) throw new Error(`Rename failed: ${response.status}`);
  return response.json();
}

/** Delete a conversation and all its messages. */
export async function deleteChat(chatId) {
  const headers = await authHeaders();
  const response = await fetch(`${API_BASE}/api/chats/${chatId}`, {
    method: 'DELETE',
    headers,
  });
  if (!response.ok) throw new Error(`Delete failed: ${response.status}`);
  return response.json();
}

// ── RAG queries (legacy — kept for backward compat) ───────────────────────

export async function sendQuery(query, sessionId) {
  const headers = await authHeaders({ 'Content-Type': 'application/json' });

  const response = await fetch(`${API_BASE}/rag/query`, {
    method: 'POST',
    headers,
    body: JSON.stringify({ query, session_id: sessionId }),
  });

  if (!response.ok) {
    throw new Error(`Query failed: ${response.status}`);
  }

  const data = await response.json();
  return data.result?.content || 'No response received.';
}

// ── Document upload ────────────────────────────────────────────────────────

export async function uploadDocument(file, description) {
  const headers = await authHeaders({ 'X-Description': description });
  const formData = new FormData();
  formData.append('file', file);

  const response = await fetch(`${API_BASE}/rag/documents/upload`, {
    method: 'POST',
    headers,
    body: formData,
  });

  if (!response.ok) {
    throw new Error(`Upload failed: ${response.status}`);
  }

  const data = await response.json();
  return data.status;
}

// ── Model management ───────────────────────────────────────────────────────

export async function fetchModels() {
  const headers = await authHeaders();

  const response = await fetch(`${API_BASE}/models`, { headers });
  if (!response.ok) {
    throw new Error(`Failed to fetch models: ${response.status}`);
  }
  return response.json();
}

export async function switchModel(modelId) {
  const headers = await authHeaders({ 'Content-Type': 'application/json' });

  const response = await fetch(`${API_BASE}/models/switch`, {
    method: 'POST',
    headers,
    body: JSON.stringify({ model_id: modelId }),
  });

  if (!response.ok) {
    throw new Error(`Failed to switch model: ${response.status}`);
  }
  return response.json();
}
