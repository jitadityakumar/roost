import { useEffect, useState } from "react";
import { api } from "../api.js";
import {
  COLORABLE_FIELD_LABELS,
  COLORABLE_FIELD_ORDER,
  EPC_BANDS,
  colorableFieldKind,
} from "../fieldColorFields.js";

function emptyRow(kind) {
  return { green_cutoff: "", red_cutoff: "", higher_is_better: kind === "numeric" ? true : null };
}

function rowsFromThresholds(thresholds) {
  const byField = Object.fromEntries(thresholds.map((t) => [t.field, t]));
  const rows = {};
  for (const field of COLORABLE_FIELD_ORDER) {
    const kind = colorableFieldKind(field);
    const stored = byField[field];
    rows[field] = stored
      ? {
          green_cutoff: stored.green_cutoff ?? "",
          red_cutoff: stored.red_cutoff ?? "",
          higher_is_better: kind === "numeric" ? Boolean(stored.higher_is_better) : null,
        }
      : emptyRow(kind);
  }
  return rows;
}

export default function FieldColorsAdminPanel({ active }) {
  const [loaded, setLoaded] = useState(false);
  const [rows, setRows] = useState({});
  const [error, setError] = useState(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!active || loaded) return;
    api.fieldColors
      .list()
      .then((thresholds) => {
        setRows(rowsFromThresholds(thresholds));
        setLoaded(true);
      })
      .catch((err) => setError(err.message));
  }, [active, loaded]);

  if (!active) return null;
  if (error) return <p className="error">{error}</p>;
  if (!loaded) return <p>Loading…</p>;

  function updateRow(field, changes) {
    setRows((prev) => ({ ...prev, [field]: { ...prev[field], ...changes } }));
  }

  async function handleSave() {
    setSaving(true);
    setError(null);
    try {
      for (const field of COLORABLE_FIELD_ORDER) {
        const row = rows[field];
        const hasCutoff = row.green_cutoff !== "" || row.red_cutoff !== "";
        if (!hasCutoff) {
          await api.fieldColors.remove(field).catch(() => {}); // fine if there was nothing to clear
          continue;
        }
        await api.fieldColors.put(field, {
          green_cutoff: row.green_cutoff === "" ? null : row.green_cutoff,
          red_cutoff: row.red_cutoff === "" ? null : row.red_cutoff,
          higher_is_better: row.higher_is_better,
        });
      }
      const thresholds = await api.fieldColors.list();
      setRows(rowsFromThresholds(thresholds));
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  }

  return (
    <div>
      <h2>Field colour thresholds</h2>
      <p className="hint">
        Set green / amber / red cutoffs for each field below. These don't gate anything — they
        only change the colour shown on the listing detail page's Details section. A cutoff is
        inclusive of the value it names (e.g. "Green at/above C" colours a C green, not just
        better-than-C); leaving both cutoffs blank removes the colour for that field.
      </p>

      {error && <p className="error">{error}</p>}

      <div className="threshold-legend">
        <span><span className="sw" style={{ background: "var(--accent)" }} />Green</span>
        <span><span className="sw" style={{ background: "var(--warn)" }} />Amber</span>
        <span><span className="sw" style={{ background: "var(--danger)" }} />Red</span>
      </div>

      {COLORABLE_FIELD_ORDER.map((field) => {
        const kind = colorableFieldKind(field);
        const row = rows[field];
        return (
          <div className="rule-card" key={field}>
            <div className="rule-card-head">
              <span className="field-name">{COLORABLE_FIELD_LABELS[field]}</span>
              {kind === "numeric" ? (
                <div className="direction-toggle">
                  <button
                    type="button"
                    className={row.higher_is_better === false ? "active" : ""}
                    onClick={() => updateRow(field, { higher_is_better: false })}
                  >
                    Lower = better
                  </button>
                  <button
                    type="button"
                    className={row.higher_is_better === true ? "active" : ""}
                    onClick={() => updateRow(field, { higher_is_better: true })}
                  >
                    Higher = better
                  </button>
                </div>
              ) : (
                <span className="admin-rule-text">band, A best</span>
              )}
            </div>

            {kind === "epc_band" ? (
              <>
                <div className="threshold-row">
                  <span className="swatch" style={{ background: "var(--accent)" }} />
                  <span className="lbl">Green at/above</span>
                  <select value={row.green_cutoff} onChange={(e) => updateRow(field, { green_cutoff: e.target.value })}>
                    <option value="">Not set</option>
                    {EPC_BANDS.map((band) => (
                      <option key={band} value={band}>{band}</option>
                    ))}
                  </select>
                </div>
                <div className="threshold-row">
                  <span className="swatch" style={{ background: "var(--danger)" }} />
                  <span className="lbl">Red at/below</span>
                  <select value={row.red_cutoff} onChange={(e) => updateRow(field, { red_cutoff: e.target.value })}>
                    <option value="">Not set</option>
                    {EPC_BANDS.map((band) => (
                      <option key={band} value={band}>{band}</option>
                    ))}
                  </select>
                </div>
              </>
            ) : (
              <>
                <div className="threshold-row">
                  <span className="swatch" style={{ background: "var(--accent)" }} />
                  <span className="lbl">Green {row.higher_is_better ? "at/above" : "at/below"}</span>
                  <input
                    type="number"
                    value={row.green_cutoff}
                    onChange={(e) => updateRow(field, { green_cutoff: e.target.value })}
                    placeholder="Not set"
                  />
                </div>
                <div className="threshold-row">
                  <span className="swatch" style={{ background: "var(--danger)" }} />
                  <span className="lbl">Red {row.higher_is_better ? "at/below" : "at/above"}</span>
                  <input
                    type="number"
                    value={row.red_cutoff}
                    onChange={(e) => updateRow(field, { red_cutoff: e.target.value })}
                    placeholder="Not set"
                  />
                </div>
              </>
            )}
          </div>
        );
      })}

      <div className="no-threshold-note">
        <b>Chain free</b> has no threshold form — it's boolean and stays hard-coded to
        "green on Yes, no chip on No".
      </div>

      <button className="status-toggle-btn" onClick={handleSave} disabled={saving}>
        {saving ? "Saving…" : "Save thresholds"}
      </button>
    </div>
  );
}
