const API_BASE = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";

// Generous timeout for ordering turns which can take 60-90s (multiple LLM calls)
const TIMEOUT_MS = 120_000;

export async function sendMessage(message, conversationId) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), TIMEOUT_MS);

  try {
    const response = await fetch(`${API_BASE}/api/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        message,
        conversation_id: conversationId || undefined,
      }),
      signal: controller.signal,
    });

    if (!response.ok) {
      const body = await response.json().catch(() => ({}));
      throw new Error(body.detail || `Request failed (${response.status})`);
    }

    return response.json();
  } catch (err) {
    if (err.name === "AbortError") {
      throw new Error("The request took too long. Please try again.");
    }
    throw err;
  } finally {
    clearTimeout(timer);
  }
}

export async function askAnything(question, length, maxWords) {
  const body = { question, length };
  if (maxWords) body.max_words = maxWords;

  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), TIMEOUT_MS);

  try {
    const response = await fetch(`${API_BASE}/api/ask`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
      signal: controller.signal,
    });

    if (!response.ok) {
      const err = await response.json().catch(() => ({}));
      throw new Error(err.detail || `Request failed (${response.status})`);
    }
    return response.json(); // { answer_markdown, length_used }
  } catch (err) {
    if (err.name === "AbortError") {
      throw new Error("The request took too long. Please try again.");
    }
    throw err;
  } finally {
    clearTimeout(timer);
  }
}
