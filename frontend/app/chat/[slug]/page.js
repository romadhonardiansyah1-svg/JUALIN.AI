"use client";
import { useState, useRef, useEffect } from "react";
import { useParams } from "next/navigation";
import { api } from "@/lib/api";
import styles from "./public-chat.module.css";

/**
 * PUBLIC CHAT PAGE — /chat/[slug]
 * Customer-facing: no login needed.
 * This is the page customers use to chat with a store's AI.
 */
export default function PublicChatPage() {
  const params = useParams();
  const slug = params.slug;
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [sessionId, setSessionId] = useState("");
  const [storeName, setStoreName] = useState("");
  const [quotaExceeded, setQuotaExceeded] = useState(false);
  const chatEndRef = useRef(null);

  useEffect(() => {
    const formattedName = slug.split("-").map(w => w.charAt(0).toUpperCase() + w.slice(1)).join(" ");
    setStoreName(formattedName);

    // Generate unique session ID for this customer
    const existingSession = sessionStorage.getItem(`jualin_session_${slug}`);
    if (existingSession) {
      setSessionId(existingSession);
      // Load existing chat history (no welcome msg — returning customer)
      loadHistory(existingSession);
    } else {
      const newSession = `cust-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
      setSessionId(newSession);
      sessionStorage.setItem(`jualin_session_${slug}`, newSession);
      
      // BUG 18 FIX: Only show welcome for NEW sessions
      setMessages([
        {
          role: "ai",
          content: `Hai kak! 👋 Selamat datang di ${formattedName}. Ada yang bisa kami bantu? Silakan tanya-tanya produk kami ya 😊`,
          time: new Date().toLocaleTimeString("id-ID", { hour: "2-digit", minute: "2-digit" }),
        },
      ]);
    }
  }, [slug]);

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  async function loadHistory(sid) {
    try {
      const data = await api.getChatHistory(sid);
      if (data.messages?.length > 0) {
        setMessages(data.messages.map(m => ({
          role: m.role === "customer" ? "customer" : "ai",
          content: m.content,
          time: m.created_at ? new Date(m.created_at).toLocaleTimeString("id-ID", { hour: "2-digit", minute: "2-digit" }) : "",
        })));
      }
    } catch (e) {
      // No history found, that's fine
    }
  }

  const handleSend = async (e) => {
    e.preventDefault();
    if (!input.trim() || sending || quotaExceeded) return;

    const userMsg = {
      role: "customer",
      content: input.trim(),
      time: new Date().toLocaleTimeString("id-ID", { hour: "2-digit", minute: "2-digit" }),
    };

    setMessages((prev) => [...prev, userMsg]);
    setInput("");
    setSending(true);

    try {
      const data = await api.sendChat({
        message: userMsg.content,
        session_id: sessionId,
        seller_slug: slug,
      });

      if (data.quota_exceeded) {
        setQuotaExceeded(true);
      }

      setMessages((prev) => [
        ...prev,
        {
          role: "ai",
          content: data.response,
          time: new Date().toLocaleTimeString("id-ID", { hour: "2-digit", minute: "2-digit" }),
        },
      ]);
    } catch (e) {
      setMessages((prev) => [
        ...prev,
        {
          role: "ai",
          content: "Maaf kak, terjadi gangguan. Coba kirim lagi ya 🙏",
          time: new Date().toLocaleTimeString("id-ID", { hour: "2-digit", minute: "2-digit" }),
        },
      ]);
    }

    setSending(false);
  };

  // Quick reply suggestions
  const quickReplies = [
    "Ada produk apa aja?",
    "Produk paling laris?",
    "Harga termurah?",
    "Cara order gimana?",
  ];

  return (
    <div className={styles.chatPage}>
      {/* Header */}
      <header className={styles.header}>
        <div className={styles.headerInfo}>
          <div className={styles.storeAvatar}>
            {storeName.charAt(0)}
          </div>
          <div>
            <h1 className={styles.storeName}>{storeName}</h1>
            <span className={styles.status}>
              <span className={styles.onlineDot}></span>
              AI Assistant · Online
            </span>
          </div>
        </div>
        <div className={styles.poweredBy}>
          Powered by <strong>JUALIN.AI</strong>
        </div>
      </header>

      {/* Messages */}
      <div className={styles.messagesArea}>
        {messages.map((msg, i) => (
          <div key={i} className={`${styles.msgRow} ${msg.role === "ai" ? styles.msgAi : styles.msgCustomer}`}>
            {msg.role === "ai" && (
              <div className={styles.aiAvatar}>🤖</div>
            )}
            <div className={`${styles.bubble} ${msg.role === "ai" ? styles.bubbleAi : styles.bubbleCustomer}`}>
              <div className={styles.bubbleContent}>{msg.content}</div>
              <span className={styles.bubbleTime}>{msg.time}</span>
            </div>
          </div>
        ))}

        {sending && (
          <div className={`${styles.msgRow} ${styles.msgAi}`}>
            <div className={styles.aiAvatar}>🤖</div>
            <div className="typing-indicator">
              <span></span><span></span><span></span>
            </div>
          </div>
        )}

        <div ref={chatEndRef} />
      </div>

      {/* Quick Replies */}
      {messages.length <= 2 && (
        <div className={styles.quickReplies}>
          {quickReplies.map((qr, i) => (
            <button
              key={i}
              className={styles.quickReplyBtn}
              onClick={() => { setInput(qr); }}
            >
              {qr}
            </button>
          ))}
        </div>
      )}

      {/* Input */}
      <form className={styles.inputArea} onSubmit={handleSend}>
        {quotaExceeded ? (
          <div className={styles.quotaMsg}>
            ⚠️ Seller sedang tidak tersedia. Silakan hubungi langsung.
          </div>
        ) : (
          <>
            <input
              type="text"
              className={styles.chatInput}
              placeholder="Ketik pesan..."
              value={input}
              onChange={(e) => setInput(e.target.value)}
              disabled={sending}
              autoFocus
            />
            <button type="submit" className={styles.sendBtn} disabled={sending || !input.trim()}>
              {sending ? "⏳" : "➤"}
            </button>
          </>
        )}
      </form>
    </div>
  );
}
