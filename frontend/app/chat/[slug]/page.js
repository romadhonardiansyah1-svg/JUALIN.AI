"use client";
import { useState, useRef, useEffect, useCallback } from "react";
import { useParams } from "next/navigation";
import { api, sendChatStream } from "@/lib/api";
import styles from "./public-chat.module.css";

/**
 * PUBLIC CHAT PAGE — /chat/[slug]
 * Customer-facing: no login needed.
 * Features: SSE streaming with word-by-word rendering,
 * typing indicator, quick replies, sales stage badge.
 */
export default function PublicChatPage() {
  const params = useParams();
  const slug = params.slug;
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [streaming, setStreaming] = useState(false);
  const [sessionId, setSessionId] = useState("");
  const [storeName, setStoreName] = useState("");
  const [quotaExceeded, setQuotaExceeded] = useState(false);
  const [salesStage, setSalesStage] = useState("greeting");
  const chatEndRef = useRef(null);
  const abortRef = useRef(null);

  useEffect(() => {
    const formattedName = slug
      .split("-")
      .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
      .join(" ");
    setStoreName(formattedName);

    const existingSession = sessionStorage.getItem(`jualin_session_${slug}`);
    if (existingSession) {
      setSessionId(existingSession);
      loadHistory(existingSession);
    } else {
      const newSession = `cust-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
      setSessionId(newSession);
      sessionStorage.setItem(`jualin_session_${slug}`, newSession);

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

  // Poll pesan baru saat idle — agar balasan "owner sudah ACC" muncul tanpa refresh
  useEffect(() => {
    if (!sessionId) return;
    const t = setInterval(async () => {
      if (sending || streaming || document.visibilityState !== "visible") return;
      try {
        const data = await api.getChatHistory(sessionId);
        if (data.messages && data.messages.length > messages.length) {
          setMessages(
            data.messages.map((m) => ({
              role: m.role === "customer" ? "customer" : "ai",
              content: m.content,
              time: m.created_at
                ? new Date(m.created_at).toLocaleTimeString("id-ID", { hour: "2-digit", minute: "2-digit" })
                : "",
            }))
          );
        }
      } catch (e) { /* diam saja */ }
    }, 5000);
    return () => clearInterval(t);
  }, [sessionId, sending, streaming, messages.length]);

  // Cleanup: abort stream on unmount
  useEffect(() => {
    return () => {
      if (abortRef.current) abortRef.current();
    };
  }, []);

  async function loadHistory(sid) {
    try {
      const data = await api.getChatHistory(sid);
      if (data.messages?.length > 0) {
        setMessages(
          data.messages.map((m) => ({
            role: m.role === "customer" ? "customer" : "ai",
            content: m.content,
            time: m.created_at
              ? new Date(m.created_at).toLocaleTimeString("id-ID", { hour: "2-digit", minute: "2-digit" })
              : "",
          }))
        );
      }
    } catch (e) {
      // No history, that's fine
    }
  }

  const handleSendFallback = useCallback(async (userMessage) => {
    try {
      const data = await api.sendChat({
        message: userMessage,
        session_id: sessionId,
        seller_slug: slug,
      });

      setMessages((prev) => {
        const updated = [...prev];
        const lastAi = updated[updated.length - 1];
        if (lastAi && lastAi.role === "ai") {
          updated[updated.length - 1] = {
            ...lastAi,
            content: data.response,
            isStreaming: false,
          };
        }
        return updated;
      });

      if (data.quota_exceeded) setQuotaExceeded(true);
    } catch (e) {
      setMessages((prev) => {
        const updated = [...prev];
        const lastAi = updated[updated.length - 1];
        if (lastAi && lastAi.role === "ai") {
          updated[updated.length - 1] = {
            ...lastAi,
            content: "Maaf kak, terjadi gangguan. Coba kirim lagi ya.",
            isStreaming: false,
          };
        }
        return updated;
      });
    }
    setSending(false);
    setStreaming(false);
    abortRef.current = null;
  }, [sessionId, slug]);

  const handleSend = useCallback(
    async (e) => {
      e?.preventDefault();
      if (!input.trim() || sending || streaming || quotaExceeded) return;

      const userMessage = input.trim();
      const userMsg = {
        role: "customer",
        content: userMessage,
        time: new Date().toLocaleTimeString("id-ID", { hour: "2-digit", minute: "2-digit" }),
      };

      setMessages((prev) => [...prev, userMsg]);
      setInput("");
      setSending(true);
      setStreaming(true);

      // Add a placeholder AI message that we'll stream into
      setMessages((prev) => [
        ...prev,
        {
          role: "ai",
          content: "",
          time: new Date().toLocaleTimeString("id-ID", { hour: "2-digit", minute: "2-digit" }),
          isStreaming: true,
        },
      ]);

      // Stream with SSE
      const abort = sendChatStream({
        body: {
          message: userMessage,
          session_id: sessionId,
          seller_slug: slug,
        },
        onMetadata: (data) => {
          if (data.stage) setSalesStage(data.stage);
        },
        onNego: (ev) => {
          setMessages((prev) => {
            const updated = [...prev];
            const lastAi = updated[updated.length - 1];
            if (lastAi && lastAi.role === "ai") {
              updated[updated.length - 1] = { ...lastAi, nego: ev };
            }
            return updated;
          });
        },
        onToken: (token) => {
          setMessages((prev) => {
            const updated = [...prev];
            const lastAi = updated[updated.length - 1];
            if (lastAi && lastAi.role === "ai") {
              updated[updated.length - 1] = {
                ...lastAi,
                content: lastAi.content + token,
              };
            }
            return updated;
          });
        },
        onDone: (data) => {
          // Mark streaming as done
          setMessages((prev) => {
            const updated = [...prev];
            const lastAi = updated[updated.length - 1];
            if (lastAi && lastAi.role === "ai") {
              updated[updated.length - 1] = {
                ...lastAi,
                content: data.full_response || lastAi.content,
                isStreaming: false,
              };
            }
            return updated;
          });

          if (data.quota_exceeded) setQuotaExceeded(true);
          if (data.session_id) setSessionId(data.session_id);
          if (data.stage) setSalesStage(data.stage);

          setSending(false);
          setStreaming(false);
          abortRef.current = null;
        },
        onError: (err) => {
          console.error("Stream error:", err);
          // Fallback to non-streaming
          handleSendFallback(userMessage);
        },
      });

      abortRef.current = abort;
    },
    [input, sending, streaming, quotaExceeded, sessionId, slug, handleSendFallback]
  );

  // Quick reply suggestions
  const quickReplies = [
    "Ada produk apa aja?",
    "Produk paling laris?",
    "Harga termurah?",
    "Cara order gimana?",
  ];

  // Sales stage display
  const stageLabels = {
    greeting: null,
    discovery: "🔍 Eksplorasi",
    presentation: "🎯 Presentasi",
    negotiation: "💬 Negosiasi",
    closing: "🛒 Closing",
    post_sale: "✅ Selesai",
  };
  const stageLabel = stageLabels[salesStage];

  return (
    <div className={styles.chatPage}>
      {/* Header */}
      <header className={styles.header}>
        <div className={styles.headerInfo}>
          <div className={styles.storeAvatar}>{storeName.charAt(0)}</div>
          <div>
            <h1 className={styles.storeName}>{storeName}</h1>
            <span className={styles.status}>
              <span className={styles.onlineDot}></span>
              AI Assistant · Online
            </span>
          </div>
        </div>
        <div className={styles.headerRight}>
          {stageLabel && <span className={styles.stageBadge}>{stageLabel}</span>}
          <div className={styles.poweredBy}>
            Powered by <strong>JUALIN.AI</strong>
          </div>
        </div>
      </header>

      {/* Messages */}
      <div className={styles.messagesArea}>
        {messages.map((msg, i) => (
          <div
            key={i}
            className={`${styles.msgRow} ${msg.role === "ai" ? styles.msgAi : styles.msgCustomer}`}
          >
            {msg.role === "ai" && <div className={styles.aiAvatar}>🤖</div>}
            <div
              className={`${styles.bubble} ${msg.role === "ai" ? styles.bubbleAi : styles.bubbleCustomer}`}
            >
              <div className={styles.bubbleContent}>
                {msg.content}
                {msg.isStreaming && <span className={styles.streamCursor}>▍</span>}
              </div>
              {msg.nego && (
                <div className={styles.negoBadge}>
                  🛡️ Mesin Nego JUALIN — diskon {msg.nego.discount_pct}% ({msg.nego.decision === "counter_floor" ? "batas aman tercapai" : msg.nego.decision === "accept" ? "deal!" : "penawaran"})
                  {msg.nego.requires_approval ? " · ⏳ menunggu ACC owner" : " · ✅ dalam batas aman owner"}
                </div>
              )}
              <span className={styles.bubbleTime}>{msg.time}</span>
            </div>
          </div>
        ))}

        {sending && !streaming && (
          <div className={`${styles.msgRow} ${styles.msgAi}`}>
            <div className={styles.aiAvatar}>🤖</div>
            <div className="typing-indicator">
              <span></span>
              <span></span>
              <span></span>
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
              onClick={() => setInput(qr)}
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
            <button
              type="submit"
              className={styles.sendBtn}
              disabled={sending || !input.trim()}
            >
              {sending ? "⏳" : "➤"}
            </button>
          </>
        )}
      </form>
    </div>
  );
}
