import { useCallback, useEffect, useRef, useState } from "react";
import { sendMessage } from "./api";
import esewaQr  from "./assets/esewa-qr.png";
import khaltiQr from "./assets/khalti-qr.png";

/* ── Constants ────────────────────────────────────────────────────────── */

const MAX_CHARS = 4000;

const QR_CONFIG = {
  esewa: {
    src: esewaQr,
    label: "eSewa",
    color: "#60BB46",
    instructions: "Open your eSewa app → Scan QR → scan the code to complete payment.",
    merchantId: "9800000001",
    storeName: "SOLE STORE",
  },
  khalti: {
    src: khaltiQr,
    label: "Khalti",
    color: "#5C2D91",
    instructions: "Open your Khalti app → Scan QR → scan the code to complete payment.",
    merchantId: "9800000002",
    storeName: "SOLE STORE",
  },
};

const SUGGESTIONS = [
  { icon: "👟", text: "What shoes do you have?" },
  { icon: "💰", text: "Which is the cheapest?" },
  { icon: "🔍", text: "Show me Nike shoes" },
  { icon: "📦", text: "Check my order status" },
];

const CAPABILITIES = [
  { icon: "🔎", text: "Browse & search products" },
  { icon: "💬", text: "Answer price & stock questions" },
  { icon: "🛒", text: "Guide you through checkout" },
  { icon: "📋", text: "Look up your order status" },
  { icon: "💳", text: "eSewa & Khalti payments" },
];

function makeWelcome() {
  return {
    id: 0,
    role: "agent",
    text: "Hi! I'm your Store Assistant. I can help you find shoes, check prices and stock, place orders, and track deliveries. What are you looking for today?",
    product: null,
    paymentMethod: null,
    ts: new Date(),
    showSuggestions: true,
  };
}

/* ── Utility ──────────────────────────────────────────────────────────── */

function formatTime(date) {
  return date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

let _id = 1;
function nextId() { return _id++; }

/* ── Toast hook ───────────────────────────────────────────────────────── */

function useToasts() {
  const [toasts, setToasts] = useState([]);

  const push = useCallback((message, type = "info") => {
    const id = nextId();
    setToasts((t) => [...t, { id, message, type }]);
    setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), 4000);
  }, []);

  const dismiss = useCallback((id) => {
    setToasts((t) => t.filter((x) => x.id !== id));
  }, []);

  return { toasts, push, dismiss };
}

/* ── App ──────────────────────────────────────────────────────────────── */

export default function App() {
  const [messages,       setMessages]       = useState([makeWelcome()]);
  const [input,          setInput]          = useState("");
  const [isSending,      setIsSending]      = useState(false);
  const [conversationId, setConversationId] = useState(null);
  const [error,          setError]          = useState(null);
  const [previewProduct, setPreviewProduct] = useState(null);
  const { toasts, push: pushToast, dismiss: dismissToast } = useToasts();

  const threadRef  = useRef(null);
  const textareaRef = useRef(null);

  /* Scroll to bottom on new messages */
  useEffect(() => {
    threadRef.current?.scrollTo({ top: threadRef.current.scrollHeight, behavior: "smooth" });
  }, [messages, isSending]);

  /* Auto-resize textarea */
  useEffect(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 120)}px`;
  }, [input]);

  function handleNewConversation() {
    setMessages([makeWelcome()]);
    setConversationId(null);
    setInput("");
    setError(null);
    setPreviewProduct(null);
    textareaRef.current?.focus();
  }

  async function submit(text) {
    const trimmed = text.trim();
    if (!trimmed || isSending) return;

    setMessages((prev) => [
      ...prev,
      { id: nextId(), role: "user", text: trimmed, ts: new Date() },
    ]);
    setInput("");
    setIsSending(true);
    setError(null);

    try {
      const data = await sendMessage(trimmed, conversationId);
      setConversationId(data.conversation_id);
      setMessages((prev) => [
        ...prev,
        {
          id: nextId(),
          role: "agent",
          text: data.reply,
          product: data.product ?? null,
          paymentMethod: data.payment_method ?? null,
          ts: new Date(),
          showSuggestions: false,
        },
      ]);
    } catch (err) {
      setError(err.message);
    } finally {
      setIsSending(false);
    }
  }

  function handleFormSubmit(e) {
    e.preventDefault();
    submit(input);
  }

  function handleKeyDown(e) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      submit(input);
    }
  }

  function handleBuy(product) {
    setPreviewProduct(null);
    pushToast(
      `${product.name}${product.color ? ` – ${product.color}` : ""} added to your purchase request.`,
      "success"
    );
  }

  const charCount  = input.length;
  const charWarn   = charCount > MAX_CHARS * 0.85;
  const charLimit  = charCount >= MAX_CHARS;

  return (
    <div className="app">
      {/* ── Sidebar ── */}
      <aside className="sidebar">
        <div className="sidebar-brand">
          <div className="brand-icon">👟</div>
          <div>
            <div className="brand-name">Store Assistant</div>
            <div className="brand-sub">AI Sales Agent</div>
          </div>
        </div>

        <div className="sidebar-section">
          <div className="sidebar-section-label">Conversation</div>
          <button type="button" className="sidebar-new-btn" onClick={handleNewConversation}>
            <svg width="13" height="13" viewBox="0 0 13 13" fill="none">
              <path d="M6.5 1v11M1 6.5h11" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round"/>
            </svg>
            New conversation
          </button>
        </div>

        <div className="sidebar-capabilities">
          <div className="sidebar-section-label" style={{ padding: "0 0 4px" }}>I can help with</div>
          {CAPABILITIES.map((c) => (
            <div key={c.text} className="capability-item">
              <span className="capability-icon">{c.icon}</span>
              <span>{c.text}</span>
            </div>
          ))}
        </div>

        <div className="sidebar-footer">
          <div className="sidebar-status">
            <span className="status-dot" />
            AI agent online
          </div>
        </div>
      </aside>

      {/* ── Chat panel ── */}
      <div className="chat-panel">
        {/* Header */}
        <div className="chat-header">
          <div className="chat-header-left">
            <div className="agent-avatar-sm">🤖</div>
            <div>
              <div className="chat-header-name">Store Assistant</div>
              <div className="chat-header-status">Online</div>
            </div>
          </div>
          <div className="header-actions">
            <button
              type="button"
              className="icon-btn"
              onClick={handleNewConversation}
              title="New conversation"
              aria-label="New conversation"
            >
              {/* pencil-square icon */}
              <svg width="15" height="15" viewBox="0 0 20 20" fill="none">
                <path d="M13.586 3.586a2 2 0 112.828 2.828l-9 9A2 2 0 016 16H4a1 1 0 01-1-1v-2a2 2 0 01.586-1.414l9-9z" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
              </svg>
            </button>
          </div>
        </div>

        {/* Thread */}
        <div className="thread" ref={threadRef} role="log" aria-live="polite" aria-label="Conversation">
          <div className="date-divider">Today</div>

          {messages.map((msg) => (
            <MessageGroup
              key={msg.id}
              message={msg}
              onPreview={setPreviewProduct}
              onBuy={handleBuy}
              onSuggestion={submit}
            />
          ))}

          {isSending && (
            <div className="typing-row">
              <div className="agent-avatar">🤖</div>
              <div className="typing-bubble">
                <span className="dot" />
                <span className="dot" />
                <span className="dot" />
              </div>
            </div>
          )}
        </div>

        {/* Error bar */}
        {error && (
          <div className="error-bar" role="alert">
            <span>⚠</span>
            <span>{error}</span>
            <button
              type="button"
              className="error-dismiss"
              onClick={() => setError(null)}
              aria-label="Dismiss error"
            >
              ×
            </button>
          </div>
        )}

        {/* Composer */}
        <div className="composer-wrap">
          <form className="composer" onSubmit={handleFormSubmit}>
            <textarea
              ref={textareaRef}
              className="composer-textarea"
              value={input}
              onChange={(e) => setInput(e.target.value.slice(0, MAX_CHARS))}
              onKeyDown={handleKeyDown}
              placeholder="Ask about shoes, prices, or your order…"
              disabled={isSending}
              rows={1}
              aria-label="Message input"
              autoFocus
            />
            <button
              type="submit"
              className="send-btn"
              disabled={isSending || !input.trim()}
              aria-label="Send message"
            >
              {/* arrow-up icon */}
              <svg width="16" height="16" viewBox="0 0 20 20" fill="none">
                <path d="M10 16V4m0 0L5 9m5-5l5 5" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
              </svg>
            </button>
          </form>
          <div className="composer-footer">
            <span className="composer-hint">Enter to send · Shift+Enter for new line</span>
            {charCount > 0 && (
              <span className={`char-count ${charLimit ? "limit" : charWarn ? "warn" : ""}`}>
                {charCount}/{MAX_CHARS}
              </span>
            )}
          </div>
        </div>
      </div>

      {/* ── Product preview modal ── */}
      {previewProduct && (
        <ProductModal
          product={previewProduct}
          onClose={() => setPreviewProduct(null)}
          onBuy={handleBuy}
        />
      )}

      {/* ── Toast stack ── */}
      <div className="toast-stack" aria-live="polite">
        {toasts.map((t) => (
          <div key={t.id} className={`toast ${t.type}`} role="status">
            <span className="toast-icon">
              {t.type === "success" ? "✓" : t.type === "error" ? "✕" : "ℹ"}
            </span>
            <span>{t.message}</span>
            <button type="button" className="toast-dismiss" onClick={() => dismissToast(t.id)} aria-label="Dismiss">×</button>
          </div>
        ))}
      </div>
    </div>
  );
}

/* ── MessageGroup ─────────────────────────────────────────────────────── */

function MessageGroup({ message, onPreview, onBuy, onSuggestion }) {
  const isAgent = message.role === "agent";

  return (
    <div className={`msg-group ${message.role}`}>
      <div className="msg-row">
        {isAgent && <div className="agent-avatar">🤖</div>}
        {!isAgent && <div className="avatar-placeholder" />}

        <div className="bubble">
          <p>{message.text}</p>

          {/* Suggestion chips — only on the welcome message */}
          {isAgent && message.showSuggestions && (
            <div className="suggestions">
              {SUGGESTIONS.map((s) => (
                <button
                  key={s.text}
                  type="button"
                  className="chip"
                  onClick={() => onSuggestion(s.text)}
                >
                  {s.icon} {s.text}
                </button>
              ))}
            </div>
          )}

          {/* Product card */}
          {isAgent && message.product && (
            <ProductCard product={message.product} onPreview={onPreview} onBuy={onBuy} />
          )}

          {/* Payment QR */}
          {isAgent && message.paymentMethod && QR_CONFIG[message.paymentMethod] && (
            <PaymentQR method={message.paymentMethod} />
          )}
        </div>
      </div>

      <div className="msg-meta">
        <span className="msg-time">{formatTime(new Date(message.ts))}</span>
      </div>
    </div>
  );
}

/* ── ProductCard ──────────────────────────────────────────────────────── */

function ProductCard({ product, onPreview, onBuy }) {
  const inStock = product.stock_quantity > 0;
  return (
    <div className="product-card">
      <button
        type="button"
        className="product-image-button"
        onClick={() => onPreview(product)}
        aria-label={`View ${product.name} image`}
      >
        <img src={product.image_url} alt={`${product.name} ${product.color ?? ""}`} />
      </button>
      <div className="product-card-body">
        <div className="product-card-name">
          {product.name}
          {product.color && <span className="product-card-color">{product.color}</span>}
        </div>
        {product.brand && <div className="product-card-brand">{product.brand}</div>}
        <div className="product-card-price">{product.current_price.toLocaleString()} {product.currency}</div>
        <div className={`product-card-stock ${inStock ? "in-stock" : "out-stock"}`}>
          {inStock ? `${product.stock_quantity} in stock` : "Out of stock"}
        </div>
      </div>
      <button
        type="button"
        className="buy-btn"
        onClick={() => onBuy(product)}
        disabled={!inStock}
      >
        {inStock ? "Buy now" : "Out of stock"}
      </button>
    </div>
  );
}

/* ── ProductModal ─────────────────────────────────────────────────────── */

function ProductModal({ product, onClose, onBuy }) {
  const inStock = product.stock_quantity > 0;

  /* Close on Escape */
  useEffect(() => {
    function onKey(e) { if (e.key === "Escape") onClose(); }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <div
      className="modal-backdrop"
      onClick={onClose}
      role="dialog"
      aria-modal="true"
      aria-label={`${product.name} details`}
    >
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <button type="button" className="modal-close" onClick={onClose} aria-label="Close">×</button>
        <div className="modal-body">
          <div className="modal-image-frame">
            <img src={product.image_url} alt={`${product.name} ${product.color ?? ""}`} />
          </div>
          <div className="modal-info">
            {product.brand && <div className="modal-brand">{product.brand}</div>}
            <div className="modal-title">{product.name}</div>
            {product.color && (
              <div className="modal-color-badge">
                <span>●</span> {product.color}
              </div>
            )}
            {product.description && (
              <p className="modal-description">{product.description}</p>
            )}
            <div className="modal-divider" />
            <div className="modal-details">
              <div className="modal-detail-item">
                <span className="modal-detail-label">Price</span>
                <span className="modal-detail-value price">
                  {product.current_price.toLocaleString()} {product.currency}
                </span>
              </div>
              <div className="modal-detail-item">
                <span className="modal-detail-label">Stock</span>
                <span className={`modal-detail-value ${inStock ? "in-stock" : "out-stock"}`}>
                  {inStock ? `${product.stock_quantity} available` : "Out of stock"}
                </span>
              </div>
              {product.category && (
                <div className="modal-detail-item">
                  <span className="modal-detail-label">Category</span>
                  <span className="modal-detail-value">{product.category}</span>
                </div>
              )}
              <div className="modal-detail-item">
                <span className="modal-detail-label">SKU</span>
                <span className="modal-detail-value" style={{ fontFamily: "var(--mono)", fontSize: "12px" }}>
                  {product.sku}
                </span>
              </div>
            </div>
            <button
              type="button"
              className="buy-btn buy-btn-lg"
              onClick={() => onBuy(product)}
              disabled={!inStock}
            >
              {inStock ? "Buy now" : "Out of stock"}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

/* ── PaymentQR ────────────────────────────────────────────────────────── */

function PaymentQR({ method }) {
  const cfg = QR_CONFIG[method];
  const [copied, setCopied] = useState(false);
  const [zoomed, setZoomed]  = useState(false);

  function handleCopy() {
    navigator.clipboard.writeText(cfg.merchantId).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  }

  return (
    <>
      <div className="payment-qr">
        <div className="payment-qr-header">
          <span className="payment-qr-dot" style={{ background: cfg.color }} />
          <span className="payment-qr-title">{cfg.label} — Scan to Pay</span>
          <span className="payment-qr-subtitle">Pending payment</span>
        </div>
        <div className="payment-qr-body">
          <button
            type="button"
            className="payment-qr-img-btn"
            onClick={() => setZoomed(true)}
            aria-label={`Zoom ${cfg.label} QR code`}
            title="Click to enlarge"
          >
            <img
              src={cfg.src}
              alt={`${cfg.label} QR code`}
              className="payment-qr-img"
            />
            <span className="payment-qr-zoom-hint">
              <svg width="12" height="12" viewBox="0 0 20 20" fill="none">
                <path d="M13 13l5 5M8.5 15a6.5 6.5 0 100-13 6.5 6.5 0 000 13zM8.5 6v5M6 8.5h5" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round"/>
              </svg>
              Tap to zoom
            </span>
          </button>
          <div className="payment-qr-meta">
            <p className="payment-qr-instructions">{cfg.instructions}</p>
            <div className="payment-qr-id-row">
              <span className="payment-qr-id-label">Merchant ID</span>
              <span className="payment-qr-id-value">{cfg.merchantId}</span>
              <button type="button" className="payment-qr-copy" onClick={handleCopy} aria-label="Copy merchant ID">
                {copied ? "Copied!" : "Copy"}
              </button>
            </div>
          </div>
        </div>
      </div>

      {zoomed && (
        <QRModal cfg={cfg} onClose={() => setZoomed(false)} onCopy={handleCopy} copied={copied} />
      )}
    </>
  );
}

function QRModal({ cfg, onClose, onCopy, copied }) {
  useEffect(() => {
    function onKey(e) { if (e.key === "Escape") onClose(); }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <div
      className="modal-backdrop qr-backdrop"
      onClick={onClose}
      role="dialog"
      aria-modal="true"
      aria-label={`${cfg.label} payment QR code`}
    >
      <div className="qr-modal" onClick={(e) => e.stopPropagation()}>

        {/* Close button — floats top-right over the image */}
        <button
          type="button"
          className="qr-modal-close-btn"
          onClick={onClose}
          aria-label="Close"
        >×</button>

        {/* The PNG already contains the full card: QR + branding */}
        <img
          src={cfg.src}
          alt={`${cfg.label} QR code for ${cfg.storeName}`}
          className="qr-modal-full-img"
          draggable={false}
        />

        {/* Copy button below the card */}
        <div className="qr-modal-copy-row">
          <button
            type="button"
            className="qr-modal-copy-btn"
            onClick={onCopy}
            aria-label="Copy merchant ID"
          >
            {copied ? "✓  Copied!" : "⎘  Copy Merchant ID"}
          </button>
        </div>

      </div>
    </div>
  );
}
