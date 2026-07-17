"use client";
import { useState, useRef, useEffect } from "react";
import { api } from "@/lib/api";
import { useAuth } from "@/components/AuthProvider";
import styles from "./chat.module.css";

export default function ChatMonitorPage() {
  const { user } = useAuth();
  const [conversations, setConversations] = useState([]);
  const [activeConv, setActiveConv] = useState(null);
  const [messages, setMessages] = useState([]);
  const [testMessage, setTestMessage] = useState("");
  const [testSession, setTestSession] = useState("");
  const [sending, setSending] = useState(false);
  const [convFilter, setConvFilter] = useState("");
  const chatEndRef = useRef(null);

  useEffect(() => {
    loadConversations();
    // Generate test session ID
    setTestSession(`test-${Date.now()}`);
  }, []);

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  async function loadConversations() {
    try {
      const data = await api.getConversations();
      setConversations(data);
    } catch (e) {
      console.error("Failed to load conversations:", e);
      setConversations([]);
    }
  }

  async function loadMessages(sessionId) {
    try {
      const data = await api.getChatHistory(sessionId);
      setMessages(data.messages || []);
    } catch (e) {
      setMessages([]);
    }
  }

  const handleSelectConv = (conv) => {
    setActiveConv(conv);
    loadMessages(conv.session_id);
  };

  const handleSendTest = async (e) => {
    e.preventDefault();
    if (!testMessage.trim() || sending) return;

    const userMsg = { role: "customer", content: testMessage, created_at: new Date().toISOString() };
    setMessages((prev) => [...prev, userMsg]);
    setTestMessage("");
    setSending(true);

    try {
      if (!user?.slug) throw new Error("Seller identity unavailable");
      const data = await api.sendChat({
        message: userMsg.content,
        session_id: testSession,
        seller_slug: user.slug,
      });

      setMessages((prev) => [
        ...prev,
        { role: "ai", content: data.response, created_at: new Date().toISOString() },
      ]);
    } catch (e) {
      setMessages((prev) => [
        ...prev,
        { role: "ai", content: "Hai kak! Maaf, AI sedang offline. Coba lagi ya 😊", created_at: new Date().toISOString() },
      ]);
    }

    setSending(false);
  };

  return (
    <div className={styles.chatPage}>
      {/* Conversation List */}
      <div className={styles.convList}>
        <div className={styles.convHeader}>
          <h3>Percakapan</h3>
          <span className="badge badge-primary">{conversations.length}</span>
        </div>

      <div className={styles.convTabs}>
          <button className={`${styles.convTab} ${!convFilter ? styles.convTabActive : ""}`} onClick={() => setConvFilter("")}>Semua</button>
          <button className={`${styles.convTab} ${convFilter === "active" ? styles.convTabActive : ""}`} onClick={() => setConvFilter("active")}>Aktif</button>
          <button className={`${styles.convTab} ${convFilter === "urgent" ? styles.convTabActive : ""}`} onClick={() => setConvFilter("urgent")}>Urgent</button>
        </div>

        {/* Test Chat Button */}
        <button
          className={styles.testChatBtn}
          onClick={() => {
            setActiveConv({ id: 0, session_id: testSession, customer_name: "Test Chat" });
            setMessages([]);
          }}
        >
          🧪 Test Chat AI
        </button>

        <div className={styles.convItems}>
          {conversations
            .filter(conv => {
              if (convFilter === "urgent") return conv.is_urgent === 1;
              if (convFilter === "active") return conv.message_count > 0;
              return true;
            })
            .map((conv) => (
            <div
              key={conv.id}
              className={`${styles.convItem} ${activeConv?.id === conv.id ? styles.convItemActive : ""}`}
              onClick={() => handleSelectConv(conv)}
            >
              <div className={styles.convAvatar}>C</div>
              <div className={styles.convInfo}>
                <span className={styles.convName}>
                  {conv.customer_name || "Customer"}
                  {conv.is_urgent === 1 && <span className="badge badge-danger" style={{ marginLeft: 6 }}>Urgent</span>}
                </span>
                <span className={styles.convPreview}>{conv.last_message}</span>
              </div>
              <div className={styles.convMeta}>
                <span className={styles.convTime}>
                  {new Date(conv.created_at).toLocaleTimeString("id-ID", { hour: "2-digit", minute: "2-digit" })}
                </span>
                {conv.message_count > 0 && (
                  <span className={styles.convUnread}>{conv.message_count}</span>
                )}
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Chat Window */}
      <div className={styles.chatWindow}>
        {activeConv ? (
          <>
            <div className={styles.chatHeader}>
              <div className={styles.chatHeaderInfo}>
                <div className={styles.chatAvatar}>C</div>
                <div>
                  <h4>{activeConv.customer_name || "Customer"}</h4>
                  <span className={styles.chatStatus}>
                    <span className={styles.onlineDot}></span> AI Auto-Reply Aktif
                  </span>
                </div>
              </div>
            </div>

            <div className={styles.chatMessages}>
              {messages.length === 0 && (
                <div className={styles.chatEmpty}>
                  <span>🧪</span>
                  <p>Kirim pesan untuk test AI Sales Assistant</p>
                  <p className="text-sm text-muted">AI akan menjawab berdasarkan katalog produk kamu</p>
                </div>
              )}

              {messages.map((msg, i) => (
                <div key={i} className={`${styles.msgRow} ${msg.role === "ai" || msg.role === "assistant" ? styles.msgAi : styles.msgCustomer}`}>
                  <div className={`chat-bubble ${msg.role === "ai" || msg.role === "assistant" ? "ai" : "customer"}`}>
                    {msg.content}
                    <div className="time">
                      {msg.created_at ? new Date(msg.created_at).toLocaleTimeString("id-ID", { hour: "2-digit", minute: "2-digit" }) : ""}
                    </div>
                  </div>
                </div>
              ))}

              {sending && (
                <div className={`${styles.msgRow} ${styles.msgAi}`}>
                  <div className="typing-indicator">
                    <span></span><span></span><span></span>
                  </div>
                </div>
              )}

              <div ref={chatEndRef} />
            </div>

            <form className={styles.chatInput} onSubmit={handleSendTest}>
              <input
                type="text"
                className="input"
                placeholder="Ketik pesan untuk test AI..."
                value={testMessage}
                onChange={(e) => setTestMessage(e.target.value)}
                disabled={sending}
              />
              <button type="submit" className="btn btn-primary" disabled={sending}>
                {sending ? "..." : "Kirim"}
              </button>
            </form>
          </>
        ) : (
          <div className={styles.chatPlaceholder}>
            <span>💬</span>
            <h3>Pilih Percakapan</h3>
            <p className="text-muted">Pilih percakapan di kiri atau klik &quot;Test Chat AI&quot; untuk menguji</p>
          </div>
        )}
      </div>
    </div>
  );
}
