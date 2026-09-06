import { useState } from "react";
import { api } from "../api.js";
import { getCookie, setCookie } from "../cookie.js";

const INITIALS_COOKIE = "roost_comment_initials";

function formatTimestamp(iso) {
  if (!iso) return "-";
  const d = new Date(iso);
  return {
    date: d.toLocaleDateString("en-GB"),
    time: d.toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" }),
  };
}

export default function Comments({ listing, onUpdate }) {
  const [modal, setModal] = useState(null); // { mode: "add" | "edit", comment? }
  const [text, setText] = useState("");
  const [initials, setInitials] = useState("");
  const [error, setError] = useState(null);

  const comments = listing.comments || [];

  function openAdd() {
    setText("");
    setInitials(getCookie(INITIALS_COOKIE) || "");
    setError(null);
    setModal({ mode: "add" });
  }

  function openEdit(comment) {
    setText(comment.text);
    setInitials(comment.initials || getCookie(INITIALS_COOKIE) || "");
    setError(null);
    setModal({ mode: "edit", comment });
  }

  async function handleSave() {
    if (!text.trim() || !initials.trim()) {
      setError("Text and initials are required.");
      return;
    }
    try {
      const body = { text: text.trim(), initials: initials.trim() };
      const updated =
        modal.mode === "add"
          ? await api.comments.create(listing.id, body)
          : await api.comments.update(listing.id, modal.comment.id, body);
      setCookie(INITIALS_COOKIE, initials.trim(), 365);
      onUpdate(updated);
      setModal(null);
    } catch (err) {
      setError(err.message);
    }
  }

  async function handleDelete(comment) {
    if (!confirm("Delete this comment? This cannot be undone.")) return;
    const updated = await api.comments.remove(listing.id, comment.id);
    onUpdate(updated);
  }

  return (
    <section className="comments-section">
      <div className="comments-header">
        <h3>Comments</h3>
        <button className="status-toggle-btn" onClick={openAdd}>
          + Add comment
        </button>
      </div>
      {comments.length === 0 ? (
        <p className="muted">No comments yet.</p>
      ) : (
        <ul className="comments-list">
          {comments.map((c) => {
            const ts = formatTimestamp(c.created_at);
            return (
              <li key={c.id} className="comment-row">
                <span className={`comment-dot ${c.comment_type}`} />
                <span className="comment-timestamp">
                  {ts === "-" ? (
                    <span>-</span>
                  ) : (
                    <>
                      <span>{ts.date}</span>
                      <span>{ts.time}</span>
                    </>
                  )}
                </span>
                <span className="comment-initials-badge">{c.initials || "-"}</span>
                <span className="comment-text-body">{c.text}</span>
                <span className="comment-actions">
                  <button className="icon-btn edit" title="Edit" aria-label="Edit comment" onClick={() => openEdit(c)}>
                    ✎
                  </button>
                  <button
                    className="icon-btn danger"
                    title="Delete"
                    aria-label="Delete comment"
                    onClick={() => handleDelete(c)}
                  >
                    ✕
                  </button>
                </span>
              </li>
            );
          })}
        </ul>
      )}

      {modal && (
        <div className="modal-overlay">
          <div className="modal">
            <h3>{modal.mode === "add" ? "Add comment" : "Edit comment"}</h3>
            <label htmlFor="comment-initials">Initials</label>
            <input id="comment-initials" value={initials} onChange={(e) => setInitials(e.target.value)} autoFocus />
            <label htmlFor="comment-text">Comment</label>
            <textarea id="comment-text" value={text} onChange={(e) => setText(e.target.value)} rows={4} />
            {error && <p className="error">{error}</p>}
            <div className="modal-actions">
              <button className="status-toggle-btn" onClick={handleSave}>
                Save
              </button>
              <button className="status-toggle-btn secondary" onClick={() => setModal(null)}>
                Cancel
              </button>
            </div>
          </div>
        </div>
      )}
    </section>
  );
}
