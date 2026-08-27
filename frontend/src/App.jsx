import { useEffect, useRef, useState } from "react";
import { sendMessage } from "./api";

const WELCOME = {
  role: "agent",
  text: "Hi, I'm the store assistant. Ask me about a product's price, stock, or price history — try \"How much are black shoes?\"",
  grounded: null,
  product: null,
};

export default function App() {
  const [messages, setMessages] = useState([WELCOME]);
  const [input, setInput] = useState("");
  const [isSending, setIsSending] = useState(false);
  const [conversationId, setConversationId] = useState(null);
  const [error, setError] = useState(null);
  const [previewProduct, setPreviewProduct] = useState(null);
  const [purchaseMessage, setPurchaseMessage] = useState(null);
  const scrollRef = useRef(null);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages, isSending]);

  async function handleSend(e) {
    e.preventDefault();
    const text = input.trim();
    if (!text || isSending) return;

    setMessages((prev) => [...prev, { role: "user", text }]);
    setInput("");
    setIsSending(true);
    setError(null);

    try {
      const previousProduct = [...messages]
        .reverse()
        .find((message) => message.product)?.product;
      const data = await sendMessage(text, conversationId, previousProduct?.id);
      setConversationId(data.conversation_id);
      setMessages((prev) => [
        ...prev,
        { role: "agent", text: data.reply, grounded: data.grounded, product: data.product },
      ]);
    } catch (err) {
      setError(err.message);
    } finally {
      setIsSending(false);
    }
  }

  function handleBuy(product) {
    const variant = product.color ? `${product.name} - ${product.color}` : product.name;
    setPurchaseMessage(`${variant} added to your purchase request.`);
    setPreviewProduct(null);
  }

  return (
    <div className="page">
      <div className="receipt">
        <header className="receipt-header">
          <span className="store-name">STORE ASSISTANT</span>
          <span className="store-sub">AI Business Agent · Phase 1</span>
        </header>

        <div className="thread" ref={scrollRef}>
          {messages.map((m, i) => (
            <Message key={i} message={m} onPreview={setPreviewProduct} onBuy={handleBuy} />
          ))}
          {isSending && (
            <div className="msg agent">
              <div className="bubble typing">
                <span className="dot" />
                <span className="dot" />
                <span className="dot" />
              </div>
            </div>
          )}
        </div>

        {error && <div className="error-bar">⚠ {error}</div>}

        <form className="composer" onSubmit={handleSend}>
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Ask about a price, product, or order…"
            disabled={isSending}
            autoFocus
          />
          <button type="submit" disabled={isSending || !input.trim()}>
            Send
          </button>
        </form>
      </div>
      {purchaseMessage && (
        <div className="purchase-message" role="status">
          {purchaseMessage}
          <button type="button" onClick={() => setPurchaseMessage(null)}>
            Dismiss
          </button>
        </div>
      )}
      {previewProduct && (
        <div className="image-preview-backdrop" onClick={() => setPreviewProduct(null)}>
          <div
            className="image-preview"
            role="dialog"
            aria-modal="true"
            aria-label={`${previewProduct.name} ${previewProduct.color || ""} preview`}
            onClick={(event) => event.stopPropagation()}
          >
            <button
              className="image-preview-close"
              type="button"
              onClick={() => setPreviewProduct(null)}
              aria-label="Close image preview"
            >
              Close
            </button>
            <div className="image-preview-content">
              <div className="image-preview-image-frame">
                <img
                  src={previewProduct.image_url}
                  alt={`${previewProduct.name} - ${previewProduct.color || ""}`}
                />
              </div>
              <div className="image-preview-info">
                <h2>
                  {previewProduct.name}{previewProduct.color && ` - ${previewProduct.color}`}
                </h2>
                <p className="image-preview-description">
                  {previewProduct.description || "No description available."}
                </p>
                <div className="image-preview-details">
                  <span>Price</span>
                  <strong>{previewProduct.current_price} {previewProduct.currency}</strong>
                  <span>Stock</span>
                  <strong>
                    {previewProduct.stock_quantity > 0
                      ? `${previewProduct.stock_quantity} in stock`
                      : "Out of stock"}
                  </strong>
                  <span>SKU</span>
                  <strong>{previewProduct.sku}</strong>
                </div>
                <BuyButton product={previewProduct} onBuy={handleBuy} />
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function Message({ message, onPreview, onBuy }) {
  const isAgent = message.role === "agent";
  return (
    <div className={`msg ${message.role}`}>
      <div className="bubble">
        <p>{message.text}</p>
        {isAgent && message.product && (
          <ProductCard product={message.product} onPreview={onPreview} onBuy={onBuy} />
        )}
      </div>
    </div>
  );
}

function ProductCard({ product, onPreview, onBuy }) {
  return (
    <div className="product-card">
      <button
        className="product-image-button"
        type="button"
        onClick={() => onPreview(product)}
        aria-label={`View larger image of ${product.color || ""} ${product.name}`}
      >
        <img src={product.image_url} alt={`${product.name} - ${product.color}`} />
      </button>
      <div className="product-card-body">
        <div className="product-card-name">
          {product.name}
          {product.color && <span className="product-card-color">{product.color}</span>}
        </div>
        {product.brand && <div className="product-card-brand">{product.brand}</div>}
        <div className="product-card-price">
          {product.current_price} {product.currency}
        </div>
        <div className="product-card-stock">
          {product.stock_quantity > 0
            ? `${product.stock_quantity} in stock`
            : "Out of stock"}
        </div>
        <BuyButton product={product} onBuy={onBuy} compact />
      </div>
    </div>
  );
}

function BuyButton({ product, onBuy, compact = false }) {
  const unavailable = product.stock_quantity <= 0;
  return (
    <button
      className={`buy-button${compact ? " buy-button-compact" : ""}`}
      type="button"
      onClick={() => onBuy(product)}
      disabled={unavailable}
    >
      {unavailable ? "Out of stock" : "Buy now"}
    </button>
  );
}
