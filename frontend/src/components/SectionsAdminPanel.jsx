import { useEffect, useState } from "react";
import { api } from "../api.js";

const SECTIONS = [
  { key: "details", label: "Details" },
  { key: "description_features", label: "Description & Key Features" },
  { key: "nearest_stations", label: "Nearest stations" },
  { key: "floorplans", label: "Floorplans" },
  { key: "epc", label: "EPC" },
  { key: "room_sizes", label: "Room Sizes" },
  { key: "commute", label: "Commute" },
  { key: "frequent_destinations", label: "Frequent Destinations" },
  { key: "mortgage", label: "Mortgage" },
  { key: "crime", label: "Crime" },
  { key: "jobs", label: "Jobs" },
];

export default function SectionsAdminPanel({ active }) {
  const [loaded, setLoaded] = useState(false);
  const [config, setConfig] = useState(null);
  const [error, setError] = useState(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!active || loaded) return;
    api.detailSections
      .get()
      .then((c) => {
        setConfig(c);
        setLoaded(true);
      })
      .catch((err) => setError(err.message));
  }, [active, loaded]);

  if (!active) return null;
  if (error) return <p className="error">{error}</p>;
  if (!loaded) return <p>Loading…</p>;

  function toggle(key) {
    setConfig((prev) => ({ ...prev, [`${key}_expanded`]: !prev[`${key}_expanded`] }));
  }

  async function handleSave() {
    setSaving(true);
    setError(null);
    try {
      setConfig(await api.detailSections.put(config));
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  }

  return (
    <div>
      <h2>Detail Page Sections</h2>
      <p className="hint">
        Choose whether each listing detail page section starts expanded or collapsed. Manual
        toggles on the listing page never persist — every page load resets to what's set here.
      </p>

      {error && <p className="error">{error}</p>}

      <ul className="admin-rules">
        {SECTIONS.map((section) => (
          <li key={section.key} className="admin-rule-row">
            <span className="admin-rule-text">{section.label}</span>
            <span className="admin-rule-actions">
              <label>
                <input
                  type="checkbox"
                  checked={config[`${section.key}_expanded`]}
                  onChange={() => toggle(section.key)}
                />
                Expanded by default
              </label>
            </span>
          </li>
        ))}
      </ul>

      <button className="status-toggle-btn" onClick={handleSave} disabled={saving}>
        {saving ? "Saving…" : "Save"}
      </button>
    </div>
  );
}
