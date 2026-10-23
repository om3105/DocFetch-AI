import { auth } from './firebase';

const API_BASE = import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000';

/**
 * Get the current user's Firebase ID token.
 * Throws if no user is signed in — the backend rejects unauthenticated requests.
 */
async function getAuthToken() {
  if (!auth?.currentUser) {
    throw new Error('Not signed in');
  }
  return auth.currentUser.getIdToken();
}

/**
 * Readable message for a failed request. Browsers report an unreachable
 * server as a bare "Failed to fetch" (Chrome) or "Load failed" (Safari).
 */
export function describeError(err) {
  if (err instanceof TypeError && /fetch|load failed|network/i.test(err.message)) {
    return "Can't reach the DocFetch server. Check your connection, or try again in a moment.";
  }
  return err?.message || 'Something went wrong. Please try again.';
}

/** Fired when the backend rejects the login; AuthContext signs the user out. */
export const AUTH_EXPIRED_EVENT = 'docfetch:auth-expired';

/** Throw an Error carrying the backend's `detail` message when available. */
async function throwForStatus(response, fallback) {
  if (response.status === 401) {
    window.dispatchEvent(new Event(AUTH_EXPIRED_EVENT));
  }
  let detail;
  try {
    detail = (await response.json()).detail;
  } catch {}
  throw new Error(typeof detail === 'string' ? detail : `${fallback}: ${response.status}`);
}

/** Helper to build headers with auth token. */
async function authHeaders(extra = {}) {
  const token = await getAuthToken();
  return {
    Authorization: `Bearer ${token}`,
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
  if (!response.ok) await throwForStatus(response, 'Create chat failed');
  return response.json();
}

/** Fetch all conversations for the current user (cursor-paginated). */
export async function fetchChats(cursor) {
  const headers = await authHeaders();
  const params = new URLSearchParams({ limit: '50' });
  if (cursor) params.set('cursor', cursor);

  const response = await fetch(`${API_BASE}/api/chats?${params}`, { headers });
  if (!response.ok) await throwForStatus(response, 'Fetch chats failed');
  return response.json();
}

/** Fetch a conversation with its message history. */
export async function fetchChatMessages(chatId, msgCursor) {
  const headers = await authHeaders();
  const params = new URLSearchParams({ msg_limit: '100' });
  if (msgCursor) params.set('msg_cursor', msgCursor);

  const response = await fetch(`${API_BASE}/api/chats/${chatId}?${params}`, { headers });
  if (!response.ok) await throwForStatus(response, 'Fetch messages failed');
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
  if (!response.ok) await throwForStatus(response, 'Send message failed');
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
  if (!response.ok) await throwForStatus(response, 'Rename failed');
  return response.json();
}

/** Delete a conversation and all its messages. */
export async function deleteChat(chatId) {
  const headers = await authHeaders();
  const response = await fetch(`${API_BASE}/api/chats/${chatId}`, {
    method: 'DELETE',
    headers,
  });
  if (!response.ok) await throwForStatus(response, 'Delete failed');
  return response.json();
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

  if (!response.ok) await throwForStatus(response, 'Upload failed');

  return response.json();
}

/** Fetch the current user's uploaded documents. */
export async function fetchDocuments() {
  const headers = await authHeaders();
  const response = await fetch(`${API_BASE}/rag/documents`, { headers });
  if (!response.ok) await throwForStatus(response, 'Fetch documents failed');
  return response.json();
}

// ── Model management ───────────────────────────────────────────────────────

export async function fetchModels() {
  const headers = await authHeaders();

  const response = await fetch(`${API_BASE}/models`, { headers });
  if (!response.ok) await throwForStatus(response, 'Failed to fetch models');
  return response.json();
}

export async function switchModel(modelId) {
  const headers = await authHeaders({ 'Content-Type': 'application/json' });

  const response = await fetch(`${API_BASE}/models/switch`, {
    method: 'POST',
    headers,
    body: JSON.stringify({ model_id: modelId }),
  });

  if (!response.ok) await throwForStatus(response, 'Failed to switch model');
  return response.json();
}
