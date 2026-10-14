import { useState, useRef, useEffect } from "react";
import type { ChatMessage, ToolCallEntry } from "../types";

interface ChatProps {
  messages: ChatMessage[];
  isStreaming: boolean;
  onSend: (message: string) => void;
}

function ToolCallExpander({ tc }: { tc: ToolCallEntry }) {
  const [open, setOpen] = useState(false);

  let parsedResult: unknown = null;
  try {
    parsedResult = JSON.parse(tc.result);
  } catch {
    parsedResult = tc.result;
  }

  return (
    <div className="tool-call">
      <button className="tool-call-header" onClick={() => setOpen(!open)}>
        <span className="tool-icon">🔧</span>
        <span className="tool-name">{tc.name}</span>
        <span className="tool-args">
          ({Object.entries(tc.arguments).map(([k, v]) =>
            `${k}: ${typeof v === "string" ? v.slice(0, 40) : JSON.stringify(v).slice(0, 40)}`
          ).join(", ")})
        </span>
        <span className="tool-toggle">{open ? "▾" : "▸"}</span>
      </button>
      {open && (
        <div className="tool-call-body">
          <div className="tool-section">
            <strong>Arguments:</strong>
            <pre>{JSON.stringify(tc.arguments, null, 2)}</pre>
          </div>
          {tc.result && (
            <div className="tool-section">
              <strong>Result:</strong>
              <pre>{typeof parsedResult === "string" ? parsedResult : JSON.stringify(parsedResult, null, 2)}</pre>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export default function Chat({ messages, isStreaming, onSend }: ChatProps) {
  const [input, setInput] = useState("");
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const trimmed = input.trim();
    if (!trimmed || isStreaming) return;
    setInput("");
    onSend(trimmed);
  };

  return (
    <div className="chat-container">
      <div className="chat-messages">
        {messages.length === 0 && (
          <div className="chat-empty">
            <p>Ask me about data quality issues in the AGT dataset.</p>
            <p className="hint">Try: "What are the top data quality issues?" or "Show me invalid phone numbers"</p>
          </div>
        )}
        {messages.map((msg, i) => (
          <div key={i} className={`chat-message ${msg.role}`}>
            <div className="message-role">{msg.role === "user" ? "You" : "AI Assistant"}</div>
            {msg.tool_calls && msg.tool_calls.length > 0 && (
              <div className="tool-calls">
                {msg.tool_calls.map((tc, j) => (
                  <ToolCallExpander key={j} tc={tc} />
                ))}
              </div>
            )}
            {msg.content && <div className="message-content">{msg.content}</div>}
          </div>
        ))}
        {isStreaming && (
          <div className="chat-message assistant streaming">
            <div className="typing-indicator">
              <span></span><span></span><span></span>
            </div>
          </div>
        )}
        <div ref={bottomRef} />
      </div>
      <form className="chat-input" onSubmit={handleSubmit}>
        <input
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Ask about data quality..."
          disabled={isStreaming}
        />
        <button type="submit" disabled={isStreaming || !input.trim()}>
          Send
        </button>
      </form>
    </div>
  );
}
