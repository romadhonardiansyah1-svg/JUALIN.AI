"use client";
import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";
import styles from "../scale.module.css";

function fmtDate(value) {
  if (!value) return "-";
  return new Date(value).toLocaleString("id-ID", { dateStyle: "medium", timeStyle: "short" });
}

export default function InboxPage() {
  const [threads, setThreads] = useState([]);
  const [activeId, setActiveId] = useState(null);
  const [detail, setDetail] = useState(null);
  const [reply, setReply] = useState("");
  const [loading, setLoading] = useState(true);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState("");

  const loadThreads = useCallback(async () => {
    setError("");
    try {
      const data = await api.getInboxThreads();
      setThreads(data);
      if (!activeId && data.length) setActiveId(data[0].id);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, [activeId]);

  async function loadDetail(id) {
    if (!id) return;
    setError("");
    try {
      setDetail(await api.getInboxThread(id));
    } catch (e) {
      setError(e.message);
      setDetail(null);
    }
  }

  useEffect(() => {
    loadThreads();
  }, [loadThreads]);

  useEffect(() => {
    loadDetail(activeId);
  }, [activeId]);

  async function changeMode(mode) {
    if (!detail) return;
    try {
      await api.updateInboxThreadMode(detail.id, { mode });
      await loadDetail(detail.id);
      await loadThreads();
    } catch (e) {
      setError(e.message);
    }
  }

  async function sendReply(e) {
    e.preventDefault();
    if (!detail || !reply.trim() || sending) return;
    setSending(true);
    setError("");
    try {
      await api.replyInboxThread(detail.id, { text: reply.trim() });
      setReply("");
      await loadDetail(detail.id);
      await loadThreads();
    } catch (e) {
      setError(e.message);
    } finally {
      setSending(false);
    }
  }

  return (
    <div className={styles.page}>
      <div className={styles.header}>
        <div className={styles.titleBlock}>
          <h2>WhatsApp Inbox</h2>
          <p className={styles.muted}>Thread masuk dari channel resmi, dengan kontrol AI/manual per percakapan.</p>
        </div>
        <button className="btn btn-outline" onClick={loadThreads}>Refresh</button>
      </div>
      {error && <div className={styles.error}>{error}</div>}
      <div className={styles.twoColumn}>
        <div className={styles.panel}>
          <div className={styles.panelHeader}>
            <strong>Threads</strong>
            <span className="badge badge-primary">{threads.length}</span>
          </div>
          {loading && <div className={styles.stateBox}>Memuat inbox...</div>}
          {!loading && threads.length === 0 && <div className={styles.stateBox}>Belum ada thread WhatsApp.</div>}
          <div className={styles.list}>
            {threads.map((thread) => (
              <button
                key={thread.id}
                className={`${styles.listItem} ${activeId === thread.id ? styles.listItemActive : ""}`}
                onClick={() => setActiveId(thread.id)}
              >
                <div className={styles.listTitle}>
                  <span>{thread.contact?.name || "Customer"}</span>
                  <span className={`badge ${thread.mode === "ai" ? "badge-success" : "badge-warning"}`}>{thread.mode}</span>
                </div>
                <div className={styles.listMeta}>
                  <span>{thread.contact?.phone || "-"}</span>
                  <span>{fmtDate(thread.last_message_at)}</span>
                  {thread.unread_count > 0 && <span>{thread.unread_count} unread</span>}
                </div>
                <div className={styles.muted}>{thread.last_message_preview || "Belum ada preview"}</div>
              </button>
            ))}
          </div>
        </div>
        <div className={`${styles.panel} ${styles.conversation}`}>
          {detail ? (
            <>
              <div className={styles.panelHeader}>
                <div>
                  <strong>{detail.contact?.name || "Customer"}</strong>
                  <div className={styles.muted}>{detail.channel?.display_name} / {detail.contact?.phone || "-"}</div>
                </div>
                <div className={styles.toolbar}>
                  <button className={`btn btn-sm ${detail.mode === "ai" ? "btn-primary" : "btn-outline"}`} onClick={() => changeMode("ai")}>AI</button>
                  <button className={`btn btn-sm ${detail.mode === "manual" ? "btn-primary" : "btn-outline"}`} onClick={() => changeMode("manual")}>Manual</button>
                </div>
              </div>
              <div className={styles.messages}>
                {detail.messages.length === 0 && <div className={styles.stateBox}>Belum ada pesan di thread ini.</div>}
                {detail.messages.map((msg) => (
                  <div key={msg.id} className={`${styles.bubble} ${msg.direction === "outbound" ? styles.bubbleOutbound : styles.bubbleInbound}`}>
                    {msg.content || `[${msg.content_type}]`}
                    <div className={styles.messageTime}>{fmtDate(msg.created_at)} / {msg.role}</div>
                  </div>
                ))}
              </div>
              <form className={styles.replyBar} onSubmit={sendReply}>
                <input className="input" value={reply} onChange={(e) => setReply(e.target.value)} placeholder="Balas manual..." disabled={sending} />
                <button className="btn btn-primary" disabled={sending || !reply.trim()}>{sending ? "Mengirim..." : "Kirim"}</button>
              </form>
            </>
          ) : (
            <div className={styles.stateBox}>Pilih thread untuk melihat percakapan.</div>
          )}
        </div>
      </div>
    </div>
  );
}
