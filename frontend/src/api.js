const API_BASE = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";

export async function sendMessage(message, conversationId) {
  const response = await fetch(`${API_BASE}/api/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      message,
      conversation_id: conversationId || undefined,
    }),
  });

  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.detail || `Request failed (${response.status})`);
  }

  return response.json(); // { conversation_id, reply, product }
}
