"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { api, inboxManageLabel, inboxAddNote, inboxListNotes, listCannedReplies } from "@/lib/api";
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
  const [searchQ, setSearchQ] = useState("");
  const [notes, setNotes] = useState([]);
  const [noteText, setNoteText] = useState("");
  const [cannedReplies, setCannedReplies] = useState([]);
  const [showCanned, setShowCanned] = useState(false);
  const [labelInput, setLabelInput] = useState("");
  const detailRequestRef = useRef(0);
  const notesRequestRef = useRef(0);
  const activeIdRef = useRef(null);

  const loadThreads = useCallback(async () => {
    setError("");
    try {
      const params = searchQ ? `?q=${encodeURIComponent(searchQ)}&limit=50` : "?limit=50";
      const data = await api.getInboxThreads(params);
      setThreads(data);
      setActiveId((current) => current || data[0]?.id || null);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, [searchQ]);

  async function loadDetail(id) {
    const requestId = ++detailRequestRef.current;
    setDetail(null);
    if (!id) return;
    setError("");
    try {
      const nextDetail = await api.getInboxThread(id);
      if (requestId === detailRequestRef.current) setDetail(nextDetail);
    } catch (e) {
      if (requestId === detailRequestRef.current) {
        setError(e.message);
        setDetail(null);
      }
    }
  }

  useEffect(() => {
    loadThreads();
  }, [loadThreads]);

  useEffect(() => {
    activeIdRef.current = activeId;
    setReply("");
    setNoteText("");
    setLabelInput("");
    loadDetail(activeId);
    loadNotes(activeId);
  }, [activeId]);

  useEffect(() => {
    listCannedReplies().then(setCannedReplies).catch(() => {});
  }, []);

  async function loadNotes(threadId) {
    const requestId = ++notesRequestRef.current;
    setNotes([]);
    if (!threadId) return;
    try {
      const nextNotes = await inboxListNotes(threadId);
      if (requestId === notesRequestRef.current) setNotes(nextNotes);
    } catch {
      if (requestId === notesRequestRef.current) setNotes([]);
    }
  }

  async function addNote() {
    if (!noteText.trim() || !activeId) return;
    const threadId = activeId;
    try {
      await inboxAddNote(threadId, noteText.trim());
      if (activeIdRef.current === threadId) {
        setNoteText("");
        await loadNotes(threadId);
      }
    } catch (e) { setError(e.message); }
  }

  async function addLabel(threadId) {
    if (!labelInput.trim()) return;
    try {
      await inboxManageLabel(threadId, labelInput.trim(), "add");
      setLabelInput("");
      await loadThreads();
    } catch (e) { setError(e.message); }
  }

  async function removeLabel(threadId, label) {
    try {
      await inboxManageLabel(threadId, label, "remove");
      await loadThreads();
    } catch (e) { setError(e.message); }
  }

  async function changeMode(mode) {
    if (!activeId || detail?.id !== activeId) return;
    const threadId = activeId;
    try {
      await api.updateInboxThreadMode(threadId, { mode });
      if (activeIdRef.current === threadId) await loadDetail(threadId);
      await loadThreads();
    } catch (e) {
      setError(e.message);
    }
  }

  async function sendReply(e) {
    e.preventDefault();
    if (!activeId || detail?.id !== activeId || !reply.trim() || sending) return;
    const threadId = activeId;
    setSending(true);
    setError("");
    try {
      await api.replyInboxThread(threadId, { text: reply.trim() });
      if (activeIdRef.current === threadId) {
        setReply("");
        await loadDetail(threadId);
      }
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
        <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
          <input
            className="input"
            placeholder="🔍 Cari nama/nomor..."
            value={searchQ}
            onChange={(e) => setSearchQ(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && loadThreads()}
            style={{ width: 200 }}
          />
          <button className="btn btn-outline" onClick={loadThreads}>Refresh</button>
        </div>
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
                {thread.labels && thread.labels.length > 0 && (
                  <div style={{ display: "flex", gap: 4, flexWrap: "wrap", marginTop: 4 }}>
                    {thread.labels.map((lbl) => (
                      <span key={lbl} className="badge badge-muted" style={{ fontSize: "0.7em", padding: "1px 6px", cursor: "pointer" }}
                        onClick={(e) => { e.stopPropagation(); removeLabel(thread.id, lbl); }}
                      >🏷 {lbl} ✕</span>
                    ))}
                  </div>
                )}
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
                    <div className={styles.messageTime}>
                      {fmtDate(msg.created_at)} / {msg.role}
                      {msg.status && msg.status !== "received" && (
                        <span className={`badge ${msg.status === "sent" ? "badge-success" : msg.status === "failed" ? "badge-danger" : "badge-warning"}`} style={{marginLeft: 6, fontSize: "0.7em"}}>
                          {msg.status}
                        </span>
                      )}
                    </div>
                    {msg.role === "ai" && msg.direction === "outbound" && (
                      <div style={{display: "flex", gap: 4, marginTop: 4}}>
                        <button
                          className="btn btn-sm btn-outline"
                          style={{fontSize: "0.75em", padding: "2px 8px"}}
                          onClick={async () => {
                            try {
                              await api.submitInboxFeedback(msg.id, { rating: "up" });
                              alert("Feedback disimpan 👍");
                            } catch (err) { setError(err.message); }
                          }}
                        >👍</button>
                        <button
                          className="btn btn-sm btn-outline"
                          style={{fontSize: "0.75em", padding: "2px 8px"}}
                          onClick={async () => {
                            try {
                              await api.submitInboxFeedback(msg.id, { rating: "down" });
                              alert("Feedback disimpan 👎");
                            } catch (err) { setError(err.message); }
                          }}
                        >👎</button>
                      </div>
                    )}
                  </div>
                ))}
              </div>
              <form className={styles.replyBar} onSubmit={sendReply}>
                <div style={{ display: "flex", gap: 4, width: "100%", alignItems: "center" }}>
                  <button type="button" className="btn btn-sm btn-outline" onClick={() => setShowCanned(!showCanned)} title="Canned Replies"
                    style={{ fontSize: "0.85rem", padding: "4px 8px" }}>⚡</button>
                  <input className="input" value={reply} onChange={(e) => setReply(e.target.value)} placeholder="Balas manual..." disabled={sending} style={{ flex: 1 }} />
                  <button className="btn btn-primary" disabled={sending || !reply.trim()}>{sending ? "..." : "Kirim"}</button>
                </div>
                {showCanned && cannedReplies.length > 0 && (
                  <div style={{ display: "flex", gap: 4, flexWrap: "wrap", marginTop: 6 }}>
                    {cannedReplies.map((cr) => (
                      <button key={cr.id} type="button" className="badge badge-primary" style={{ cursor: "pointer", padding: "4px 10px" }}
                        onClick={() => { setReply(cr.content); setShowCanned(false); }}>
                        {cr.title}
                      </button>
                    ))}
                  </div>
                )}
              </form>
              {/* Labels & Notes Panel */}
              <div style={{ padding: 10, borderTop: "1px solid var(--border)", display: "flex", gap: 8, alignItems: "center" }}>
                <input className="input" value={labelInput} onChange={(e) => setLabelInput(e.target.value)}
                  placeholder="+ Label" style={{ width: 100, fontSize: "0.8rem" }}
                  onKeyDown={(e) => e.key === "Enter" && addLabel(detail.id)} />
                <button className="btn btn-sm btn-outline" onClick={() => addLabel(detail.id)}>🏷</button>
                <span style={{ flex: 1 }} />
                <span className="text-xs text-muted">{notes.length} notes</span>
              </div>
              {notes.length > 0 && (
                <div style={{ padding: "0 10px 10px", maxHeight: 120, overflow: "auto" }}>
                  {notes.map((n) => (
                    <div key={n.id} style={{ fontSize: "0.8rem", padding: "4px 0", borderBottom: "1px solid var(--border-light)" }}>
                      <span className="text-muted">{fmtDate(n.created_at)}</span>: {n.content}
                    </div>
                  ))}
                </div>
              )}
              <div style={{ padding: "0 10px 10px", display: "flex", gap: 4 }}>
                <input className="input" value={noteText} onChange={(e) => setNoteText(e.target.value)}
                  placeholder="Tambah catatan internal..." style={{ flex: 1, fontSize: "0.8rem" }}
                  onKeyDown={(e) => e.key === "Enter" && addNote()} />
                <button className="btn btn-sm btn-outline" onClick={addNote} disabled={!noteText.trim()}>📝</button>
              </div>
            </>
          ) : (
            <div className={styles.stateBox}>Pilih thread untuk melihat percakapan.</div>
          )}
        </div>
      </div>
    </div>
  );
}
