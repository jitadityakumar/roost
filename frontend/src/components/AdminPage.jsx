import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api.js";
import {
  BOOLEAN_FIELDS,
  BOOLEAN_OPERATORS,
  EPC_BAND_FIELDS,
  EPC_BAND_OPERATORS,
  EPC_BANDS,
  FIELD_LABELS,
  NUMERIC_FIELDS,
  NUMERIC_OPERATORS,
  fieldType,
} from "../standardsFields.js";

const OPERATOR_LABELS = Object.fromEntries(
  [...NUMERIC_OPERATORS, ...BOOLEAN_OPERATORS, ...EPC_BAND_OPERATORS].map((o) => [o.value, o.label])
);

const ALL_FIELDS = { ...NUMERIC_FIELDS, ...BOOLEAN_FIELDS, ...EPC_BAND_FIELDS };
const DEFAULT_FIELD = Object.keys(ALL_FIELDS)[0];

function operatorsFor(kind) {
  if (kind === "boolean") return BOOLEAN_OPERATORS;
  if (kind === "epc_band") return EPC_BAND_OPERATORS;
  return NUMERIC_OPERATORS;
}

function defaultValueFor(kind) {
  if (kind === "boolean") return "true";
  if (kind === "epc_band") return EPC_BANDS[2]; // "C"
  return "";
}

function describeRule(rule) {
  const label = FIELD_LABELS[rule.field] || rule.field;
  const symbol = OPERATOR_LABELS[rule.operator] || rule.operator;
  return `${label} ${symbol} ${rule.value}`;
}

const MAX_BASELINES = 3;

const DAY_OPTIONS = [
  { value: 0, label: "Monday" },
  { value: 1, label: "Tuesday" },
  { value: 2, label: "Wednesday" },
  { value: 3, label: "Thursday" },
  { value: 4, label: "Friday" },
  { value: 5, label: "Saturday" },
  { value: 6, label: "Sunday" },
];

// TfL StopPoint mode ids -> a short display label, for the "Name (Mode)"
// search-result format (issue #47 UX addendum) -- lets the admin
// distinguish same-named stops on different lines (e.g. Wimbledon National
// Rail vs. Wimbledon Tram). A match can carry more than one mode (a
// multi-modal interchange), joined with "/".
const TFL_MODE_LABELS = {
  "national-rail": "National Rail",
  tube: "Underground",
  overground: "Overground",
  dlr: "DLR",
  tram: "Tram",
  "elizabeth-line": "Elizabeth line",
};

function formatModes(modes) {
  return (modes || []).map((m) => TFL_MODE_LABELS[m] || m).join("/");
}

// Council tax rates panel (issue #60) -- one row per council, keyed by GSS
// code (never council_name, which is display-only and can change).
const BAND_LETTERS = ["A", "B", "C", "D", "E", "F", "G", "H"];
const BAND_COLUMNS = BAND_LETTERS.map((letter) => `band_${letter.toLowerCase()}`);

function councilNeedsRates(council) {
  return BAND_COLUMNS.some((col) => council[col] === null || council[col] === undefined);
}

function CouncilRow({ council, onSave, onClear }) {
  const [expanded, setExpanded] = useState(false);
  const [bands, setBands] = useState(() =>
    Object.fromEntries(BAND_COLUMNS.map((col) => [col, council[col] ?? ""]))
  );
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    setBands(Object.fromEntries(BAND_COLUMNS.map((col) => [col, council[col] ?? ""])));
  }, [council]);

  const needsRates = councilNeedsRates(council);

  async function handleSave() {
    setSaving(true);
    setError(null);
    try {
      const payload = Object.fromEntries(
        BAND_COLUMNS.map((col) => [col, bands[col] === "" ? null : Number(bands[col])])
      );
      await onSave(council.gss_code, council.council_name, payload);
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  }

  return (
    <li className={`council-row ${needsRates ? "needs" : ""} ${expanded ? "expanded" : ""}`}>
      <div className="council-head" onClick={() => setExpanded((v) => !v)}>
        <div className="council-name-wrap">
          <span className="council-name">{council.council_name}</span>
          <span className={`status-chip ${needsRates ? "new" : "complete"}`}>
            {needsRates ? "New — needs rates" : "Complete"}
          </span>
        </div>
        <span className="chev-btn">▸</span>
      </div>
      {expanded && (
        <div className="council-body">
          {error && <p className="error">{error}</p>}
          {BAND_LETTERS.map((letter, i) => (
            <div className="band-field" key={letter}>
              <label htmlFor={`band-${council.gss_code}-${letter}`}>
                <span className="band-letter">{letter}</span> Band {letter}
              </label>
              <div className="band-field-wrap">
                <span className="currency">£</span>
                <input
                  id={`band-${council.gss_code}-${letter}`}
                  type="number"
                  value={bands[BAND_COLUMNS[i]]}
                  onChange={(e) =>
                    setBands((prev) => ({ ...prev, [BAND_COLUMNS[i]]: e.target.value }))
                  }
                  placeholder="Not set"
                />
              </div>
            </div>
          ))}
          <div className="council-body-foot">
            <span className="gss">GSS {council.gss_code}</span>
            <span className="admin-rule-actions">
              <button type="button" className="remove-link" onClick={() => onClear(council.gss_code)}>
                Clear rates
              </button>
              <button
                type="button"
                className="status-toggle-btn"
                onClick={handleSave}
                disabled={saving}
              >
                {saving ? "Saving…" : "Save"}
              </button>
            </span>
          </div>
        </div>
      )}
    </li>
  );
}

function CouncilTaxPanel({ councils, error, onSave, onClear }) {
  const needsCount = councils.filter(councilNeedsRates).length;

  return (
    <>
      <h2>Council tax rates</h2>
      <p className="hint">
        Roost resolves each listing's council automatically when it's added. Enter each band's
        annual rate once per council — new councils appear here as soon as a listing needs one,
        nothing to add by hand.
      </p>

      {error && <p className="error">{error}</p>}

      <div className="summary-strip">
        <div className="stat-chip">
          <span>Councils tracked</span> <b>{councils.length}</b>
        </div>
        {needsCount > 0 && (
          <div className="stat-chip warn">
            <span>Needs rates</span> <b>{needsCount}</b>
          </div>
        )}
      </div>

      {councils.length === 0 ? (
        <p className="empty-state">No councils yet — add a listing to get started.</p>
      ) : (
        <ul className="council-list">
          {councils.map((c) => (
            <CouncilRow key={c.gss_code} council={c} onSave={onSave} onClear={onClear} />
          ))}
        </ul>
      )}

      <div className="add-council-note">
        <span className="icon">ⓘ</span>
        <span>
          Councils appear here automatically the first time a listing resolves to them — nothing
          to add manually. Clearing a council's rates doesn't remove it from this list if a
          listing still resolves to it.
        </span>
      </div>
    </>
  );
}

function DestinationForm({ onAdded, onCancel }) {
  const [name, setName] = useState("");
  const [destinationType, setDestinationType] = useState("station");
  const [dayOfWeek, setDayOfWeek] = useState(0);
  const [time, setTime] = useState("08:30");
  const [query, setQuery] = useState("");
  const [results, setResults] = useState([]);
  const [searching, setSearching] = useState(false);
  const [station, setStation] = useState(null);
  const [postcode, setPostcode] = useState("");
  const [error, setError] = useState(null);
  const [submitting, setSubmitting] = useState(false);

  async function handleSearch(e) {
    e.preventDefault();
    if (!query.trim()) return;
    setSearching(true);
    try {
      setResults(await api.destinations.searchStations(query));
    } catch {
      setResults([]);
    } finally {
      setSearching(false);
    }
  }

  function handleTypeChange(nextType) {
    setDestinationType(nextType);
    setStation(null);
    setQuery("");
    setResults([]);
    setPostcode("");
  }

  const postcodeValid = /^[A-Za-z]{1,2}\d[A-Za-z\d]?\s*\d[A-Za-z]{2}$/.test(postcode.trim());
  const canSubmit = name.trim() && (destinationType === "station" ? station : postcodeValid);

  async function handleSubmit(e) {
    e.preventDefault();
    setError(null);
    if (!canSubmit) {
      setError(
        destinationType === "station"
          ? "Name and station are both required."
          : "Name and a valid postcode are both required."
      );
      return;
    }
    setSubmitting(true);
    try {
      const created = await api.destinations.create({
        name: name.trim(),
        destination_type: destinationType,
        tfl_identifier: destinationType === "station" ? station.id : postcode.trim(),
        station_name: destinationType === "station" ? station.name : postcode.trim(),
        day_of_week: dayOfWeek,
        time,
      });
      onAdded(created);
    } catch (err) {
      setError(err.message);
      setSubmitting(false);
    }
  }

  return (
    <form className="admin-add-rule destination-form" onSubmit={handleSubmit}>
      {error && <p className="error">{error}</p>}
      <div>
        <label className="form-label" htmlFor="dest-name">Name</label>
        <input
          id="dest-name"
          type="text"
          placeholder="e.g. Office, Mum &amp; Dad's"
          value={name}
          onChange={(e) => setName(e.target.value)}
        />
      </div>

      <div>
        <span className="form-label">Type</span>
        <div className="radio-group" role="radiogroup" aria-label="Destination type">
          <label className="radio-option">
            <input
              type="radio"
              name="dest-type"
              value="station"
              checked={destinationType === "station"}
              onChange={() => handleTypeChange("station")}
            />
            Station
          </label>
          <label className="radio-option">
            <input
              type="radio"
              name="dest-type"
              value="postcode"
              checked={destinationType === "postcode"}
              onChange={() => handleTypeChange("postcode")}
            />
            Postcode
          </label>
        </div>
      </div>

      {destinationType === "station" ? (
        <div>
          <label className="form-label" htmlFor="station-search">Station</label>
          {station ? (
            <div className="station-chip">
              <span>
                <span className="station-chip-name">{station.name}</span>
                <span className="station-chip-crs">{formatModes(station.modes)}</span>
              </span>
              <button type="button" onClick={() => setStation(null)} aria-label="Clear station">
                ✕
              </button>
            </div>
          ) : (
            <div className="station-search-wrap">
              <div className="station-search-row">
                <input
                  id="station-search"
                  type="text"
                  placeholder="Search station name…"
                  autoComplete="off"
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                />
                <button
                  type="button"
                  className="status-toggle-btn secondary"
                  onClick={handleSearch}
                  disabled={searching || !query.trim()}
                >
                  {searching ? "Searching…" : "Search"}
                </button>
              </div>
              {results.length > 0 && (
                <div className="station-search-results">
                  {results.map((s) => (
                    <div
                      key={s.id}
                      className="station-search-result"
                      onClick={() => {
                        setStation(s);
                        setQuery("");
                        setResults([]);
                      }}
                    >
                      <span>{s.name}</span>
                      <span className="station-search-result-crs">{formatModes(s.modes)}</span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
      ) : (
        <div>
          <label className="form-label" htmlFor="dest-postcode">Postcode</label>
          <input
            id="dest-postcode"
            type="text"
            placeholder="e.g. NW1 7JN"
            autoComplete="off"
            value={postcode}
            onChange={(e) => setPostcode(e.target.value)}
          />
        </div>
      )}

      <div className="form-row">
        <div>
          <label className="form-label" htmlFor="dest-day">Day</label>
          <select id="dest-day" value={dayOfWeek} onChange={(e) => setDayOfWeek(Number(e.target.value))}>
            {DAY_OPTIONS.map((d) => (
              <option key={d.value} value={d.value}>
                {d.label}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label className="form-label" htmlFor="dest-time">Time</label>
          <input id="dest-time" type="time" value={time} onChange={(e) => setTime(e.target.value)} />
        </div>
      </div>

      <div className="form-actions">
        <button type="button" className="status-toggle-btn secondary" onClick={onCancel} disabled={submitting}>
          Cancel
        </button>
        <button type="submit" className="status-toggle-btn" disabled={submitting || !canSubmit}>
          {submitting ? "Adding…" : "Add destination"}
        </button>
      </div>
    </form>
  );
}

const NAV_ITEMS = [
  { key: "standards", label: "Standards" },
  { key: "crime", label: "Crime baselines" },
  { key: "destinations", label: "Frequent destinations" },
  { key: "counciltax", label: "Council tax rates" },
];

export default function AdminPage() {
  const navigate = useNavigate();
  const [activePanel, setActivePanel] = useState("standards");
  const [rules, setRules] = useState([]);
  const [error, setError] = useState(null);

  const [field, setField] = useState(DEFAULT_FIELD);
  const [operator, setOperator] = useState(NUMERIC_OPERATORS[0].value);
  const [value, setValue] = useState("");

  const [baselines, setBaselines] = useState([]);
  const [baselineError, setBaselineError] = useState(null);
  const [baselineLabel, setBaselineLabel] = useState("");
  const [baselinePostcode, setBaselinePostcode] = useState("");

  const [destinations, setDestinations] = useState([]);
  const [destinationError, setDestinationError] = useState(null);
  const [showDestinationForm, setShowDestinationForm] = useState(false);
  // destinationId -> {status, done, total} -- see GitHub issue #36. Polled
  // from the backend's in-memory backfill_status (not persisted there
  // either), so this is purely a "is a backfill running right now, and how
  // far along" display, reconstructed on every mount rather than trusted
  // as durable state.
  const [backfills, setBackfills] = useState({});
  const mountedRef = useRef(true);

  const [councils, setCouncils] = useState([]);
  const [councilTaxError, setCouncilTaxError] = useState(null);

  const kind = fieldType(field);
  const operators = operatorsFor(kind);

  async function load() {
    try {
      setRules(await api.standards.list());
    } catch (err) {
      setError(err.message);
    }
  }

  async function loadBaselines() {
    try {
      setBaselines(await api.crimeBaselines.list());
    } catch (err) {
      setBaselineError(err.message);
    }
  }

  async function loadDestinations() {
    try {
      const list = await api.destinations.list();
      setDestinations(list);
      return list;
    } catch (err) {
      setDestinationError(err.message);
      return [];
    }
  }

  async function loadCouncilTax() {
    try {
      setCouncils(await api.councilTax.list());
    } catch (err) {
      setCouncilTaxError(err.message);
    }
  }

  // Polls a single destination's backfill status until it stops running --
  // used both right after this tab starts a backfill (create/edit) and on
  // mount for every existing destination, so navigating away mid-backfill
  // and coming back still shows live progress (not just "it happened to
  // finish while I was gone"). Deliberately kept lifted here in AdminPage
  // (not inside a per-panel component that only mounts when selected) --
  // see issue #60's admin-page redesign: every panel below renders on every
  // mount regardless of which nav item is active, only visibility toggles
  // via CSS, so this poller's mount-scoped guarantee survives switching to
  // the Council tax nav item mid-backfill.
  async function pollBackfillStatus(destinationId) {
    let status;
    try {
      status = await api.destinations.backfillStatus(destinationId);
    } catch {
      return; // best-effort progress display -- a failed poll just stops silently
    }
    if (!mountedRef.current) return;
    setBackfills((prev) => ({ ...prev, [destinationId]: status }));
    if (status.status === "queued" || status.status === "running") {
      setTimeout(() => pollBackfillStatus(destinationId), 1000);
    }
  }

  useEffect(() => {
    mountedRef.current = true;
    load();
    loadBaselines();
    loadCouncilTax();
    loadDestinations().then((list) => {
      list.forEach((d) => pollBackfillStatus(d.id));
    });
    return () => {
      mountedRef.current = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function handleDestinationAdded(created) {
    setShowDestinationForm(false);
    await loadDestinations();
    if (created?.id) pollBackfillStatus(created.id);
  }

  async function handleDeleteDestination(destination) {
    await api.destinations.remove(destination.id);
    await loadDestinations();
  }

  function handleFieldChange(nextField) {
    setField(nextField);
    const nextKind = fieldType(nextField);
    setOperator(operatorsFor(nextKind)[0].value);
    setValue(defaultValueFor(nextKind));
  }

  async function handleAdd(e) {
    e.preventDefault();
    setError(null);
    if (kind === "numeric" && value.trim() === "") {
      setError("Value is required.");
      return;
    }
    try {
      await api.standards.create({ field, operator, value: String(value) });
      setValue(defaultValueFor(kind));
      await load();
    } catch (err) {
      setError(err.message);
    }
  }

  async function handleToggle(rule) {
    await api.standards.patch(rule.id, { enabled: !rule.enabled });
    await load();
  }

  async function handleDelete(rule) {
    await api.standards.remove(rule.id);
    await load();
  }

  async function handleAddBaseline(e) {
    e.preventDefault();
    setBaselineError(null);
    if (!baselineLabel.trim() || !baselinePostcode.trim()) {
      setBaselineError("Label and postcode are both required.");
      return;
    }
    try {
      await api.crimeBaselines.create({ label: baselineLabel.trim(), postcode: baselinePostcode.trim() });
      setBaselineLabel("");
      setBaselinePostcode("");
      await loadBaselines();
    } catch (err) {
      setBaselineError(err.message);
    }
  }

  async function handleDeleteBaseline(baseline) {
    await api.crimeBaselines.remove(baseline.id);
    await loadBaselines();
  }

  async function handleSaveCouncilRates(gssCode, councilName, bands) {
    setCouncilTaxError(null);
    try {
      await api.councilTax.update(gssCode, { council_name: councilName, ...bands });
      await loadCouncilTax();
    } catch (err) {
      setCouncilTaxError(err.message);
      throw err;
    }
  }

  async function handleClearCouncilRates(gssCode) {
    setCouncilTaxError(null);
    try {
      await api.councilTax.remove(gssCode);
      await loadCouncilTax();
    } catch (err) {
      setCouncilTaxError(err.message);
    }
  }

  const councilsNeedingRatesCount = councils.filter(councilNeedsRates).length;

  return (
    <div className="admin-page admin-shell">
      <nav className="admin-nav">
        <button className="back-btn" onClick={() => navigate("/")}>
          ← Back to Home
        </button>
        <div className="nav-title">Admin</div>
        {NAV_ITEMS.map((item) => (
          <button
            key={item.key}
            className={activePanel === item.key ? "active" : ""}
            onClick={() => setActivePanel(item.key)}
          >
            {item.label}
            {item.key === "counciltax" && councilsNeedingRatesCount > 0 && (
              <span
                className="dot"
                title={`${councilsNeedingRatesCount} council${councilsNeedingRatesCount === 1 ? "" : "s"} need${
                  councilsNeedingRatesCount === 1 ? "s" : ""
                } rates`}
              />
            )}
          </button>
        ))}
      </nav>

      <div className="admin-main">
        <div className={`admin-panel ${activePanel === "standards" ? "" : "admin-panel-hidden"}`}>
          <h2>Standards</h2>
          <p className="hint">
            Rules here don't change any listing — they just flag on the listing detail page when a
            property fails one of your own standards.
          </p>

          {error && <p className="error">{error}</p>}

          {rules.length === 0 ? (
            <p className="empty-state">No rules yet.</p>
          ) : (
            <ul className="admin-rules">
              {rules.map((rule) => (
                <li key={rule.id} className={`admin-rule-row ${rule.enabled ? "" : "disabled"}`}>
                  <span className="admin-rule-text">{describeRule(rule)}</span>
                  <span className="admin-rule-actions">
                    <button className="edit-btn" onClick={() => handleToggle(rule)}>
                      {rule.enabled ? "Disable" : "Enable"}
                    </button>
                    <button
                      className="icon-btn danger"
                      onClick={() => handleDelete(rule)}
                      title="Delete"
                      aria-label="Delete rule"
                    >
                      ✕
                    </button>
                  </span>
                </li>
              ))}
            </ul>
          )}

          <form className="admin-add-rule" onSubmit={handleAdd}>
            <select value={field} onChange={(e) => handleFieldChange(e.target.value)}>
              {Object.entries(ALL_FIELDS).map(([key, label]) => (
                <option key={key} value={key}>
                  {label}
                </option>
              ))}
            </select>

            <select value={operator} onChange={(e) => setOperator(e.target.value)}>
              {operators.map((o) => (
                <option key={o.value} value={o.value}>
                  {o.label}
                </option>
              ))}
            </select>

            {kind === "boolean" ? (
              <select value={value} onChange={(e) => setValue(e.target.value)}>
                <option value="true">true</option>
                <option value="false">false</option>
              </select>
            ) : kind === "epc_band" ? (
              <select value={value} onChange={(e) => setValue(e.target.value)}>
                {EPC_BANDS.map((band) => (
                  <option key={band} value={band}>
                    {band}
                  </option>
                ))}
              </select>
            ) : (
              <input
                type="number"
                value={value}
                onChange={(e) => setValue(e.target.value)}
                placeholder="Value"
              />
            )}

            <button className="status-toggle-btn" type="submit">
              Add rule
            </button>
          </form>
        </div>

        <div className={`admin-panel ${activePanel === "crime" ? "" : "admin-panel-hidden"}`}>
          <h2>Crime baselines</h2>
          <p className="hint">
            Up to {MAX_BASELINES} postcodes (e.g. your current home) to compare a listing's crime
            stats against on the listing detail page.
          </p>

          {baselineError && <p className="error">{baselineError}</p>}

          {baselines.length === 0 ? (
            <p className="empty-state">No baselines yet.</p>
          ) : (
            <ul className="admin-rules">
              {baselines.map((baseline) => (
                <li key={baseline.id} className="admin-rule-row">
                  <span className="admin-rule-text">
                    {baseline.label} — {baseline.postcode}
                  </span>
                  <span className="admin-rule-actions">
                    <button
                      className="icon-btn danger"
                      onClick={() => handleDeleteBaseline(baseline)}
                      title="Delete"
                      aria-label="Delete baseline"
                    >
                      ✕
                    </button>
                  </span>
                </li>
              ))}
            </ul>
          )}

          {baselines.length < MAX_BASELINES && (
            <form className="admin-add-rule" onSubmit={handleAddBaseline}>
              <input
                type="text"
                value={baselineLabel}
                onChange={(e) => setBaselineLabel(e.target.value)}
                placeholder="Label (e.g. Home)"
              />
              <input
                type="text"
                value={baselinePostcode}
                onChange={(e) => setBaselinePostcode(e.target.value)}
                placeholder="Postcode"
              />
              <button className="status-toggle-btn" type="submit">
                Add baseline
              </button>
            </form>
          )}
        </div>

        <div className={`admin-panel ${activePanel === "destinations" ? "" : "admin-panel-hidden"}`}>
          <h2>Frequent destinations</h2>
          <p className="hint">
            Places you travel to often (office, family, an airport terminal). Roost computes the
            best TfL journey from a listing to each destination's day/time, once, when the listing
            is added — recompute manually from the listing detail page.
          </p>

          {destinationError && <p className="error">{destinationError}</p>}

          {destinations.length === 0 ? (
            <p className="empty-state">No destinations yet.</p>
          ) : (
            <ul className="admin-rules">
              {destinations.map((destination) => {
                const backfill = backfills[destination.id];
                return (
                  <li key={destination.id} className="admin-rule-row">
                    <span className="admin-rule-text">
                      <div className="admin-rule-title">
                        {destination.name}
                        <span className={`badge badge-${destination.destination_type}`}>
                          {destination.destination_type === "station" ? "Station" : "Postcode"}
                        </span>
                      </div>
                      <div className="admin-rule-sub">
                        {DAY_OPTIONS[destination.day_of_week].label} · {destination.time} ·{" "}
                        {destination.station_name}
                      </div>
                      {backfill?.status === "queued" && (
                        <p className="backfill-progress-queued">
                          Queued — waiting for another destination's backfill to finish…
                        </p>
                      )}
                      {backfill?.status === "running" && (
                        <div className="backfill-progress" role="progressbar" aria-label="Backfill progress"
                          aria-valuenow={backfill.done} aria-valuemin={0} aria-valuemax={backfill.total}>
                          <div className="backfill-progress-track">
                            <div
                              className="backfill-progress-fill"
                              style={{ width: `${backfill.total ? (backfill.done / backfill.total) * 100 : 0}%` }}
                            />
                          </div>
                          <span className="backfill-progress-label">
                            Backfilling journeys… {backfill.total ? Math.round((backfill.done / backfill.total) * 100) : 0}%
                            ({backfill.done}/{backfill.total})
                          </span>
                        </div>
                      )}
                      {backfill?.status === "failed" && (
                        <p className="backfill-progress-error">
                          Backfill failed partway ({backfill.done}/{backfill.total} listings updated) — edit
                          the destination again to retry.
                        </p>
                      )}
                    </span>
                    <span className="admin-rule-actions">
                      <button
                        className="icon-btn danger"
                        onClick={() => handleDeleteDestination(destination)}
                        title="Delete"
                        aria-label="Delete destination"
                      >
                        ✕
                      </button>
                    </span>
                  </li>
                );
              })}
            </ul>
          )}

          <button className="status-toggle-btn ghost" type="button" onClick={() => setShowDestinationForm(true)}>
            + New destination
          </button>

          {showDestinationForm && (
            <div className="modal-overlay">
              <div className="modal">
                <h3>New destination</h3>
                <DestinationForm onAdded={handleDestinationAdded} onCancel={() => setShowDestinationForm(false)} />
              </div>
            </div>
          )}
        </div>

        <div className={`admin-panel ${activePanel === "counciltax" ? "" : "admin-panel-hidden"}`}>
          <CouncilTaxPanel
            councils={councils}
            error={councilTaxError}
            onSave={handleSaveCouncilRates}
            onClear={handleClearCouncilRates}
          />
        </div>
      </div>
    </div>
  );
}
