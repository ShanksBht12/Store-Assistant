const API_BASE = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";

export async function sendMessage(message, conversationId, referenceProductId) {
  const response = await fetch(`${API_BASE}/api/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      message,
      conversation_id: conversationId || undefined,
      reference_product_id: referenceProductId || undefined,
    }),
  });

  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.detail || `Request failed (${response.status})`);
  }

  return response.json(); // { conversation_id, reply, grounded }
}
