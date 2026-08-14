import { useEffect, useState } from "react";
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

function DestinationForm({ onAdded, onCancel }) {
  const [name, setName] = useState("");
  const [dayOfWeek, setDayOfWeek] = useState(0);
  const [time, setTime] = useState("08:30");
  const [query, setQuery] = useState("");
  const [results, setResults] = useState([]);
  const [station, setStation] = useState(null);
  const [error, setError] = useState(null);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (!query.trim()) {
      setResults([]);
      return;
    }
    let cancelled = false;
    const timer = setTimeout(() => {
      api.destinations
        .searchStations(query)
        .then((r) => {
          if (!cancelled) setResults(r);
        })
        .catch(() => {
          if (!cancelled) setResults([]);
        });
    }, 200);
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [query]);

  async function handleSubmit(e) {
    e.preventDefault();
    setError(null);
    if (!name.trim() || !station) {
      setError("Name and station are both required.");
      return;
    }
    setSubmitting(true);
    try {
      await api.destinations.create({
        name: name.trim(),
        crs: station.crs,
        station_name: station.name,
        day_of_week: dayOfWeek,
        time,
      });
      onAdded();
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
            <input type="radio" name="dest-type" value="station" checked readOnly />
            Station
          </label>
        </div>
      </div>

      <div>
        <label className="form-label" htmlFor="station-search">Nearest station</label>
        {station ? (
          <div className="station-chip">
            <span>
              <span className="station-chip-name">{station.name}</span>
              <span className="station-chip-crs">{station.crs}</span>
            </span>
            <button type="button" onClick={() => setStation(null)} aria-label="Clear station">
              ✕
            </button>
          </div>
        ) : (
          <div className="station-search-wrap">
            <input
              id="station-search"
              type="text"
              placeholder="Search station name…"
              autoComplete="off"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
            />
            {results.length > 0 && (
              <div className="station-search-results">
                {results.map((s) => (
                  <div
                    key={s.crs}
                    className="station-search-result"
                    onClick={() => {
                      setStation(s);
                      setQuery("");
                      setResults([]);
                    }}
                  >
                    <span>{s.name}</span>
                    <span className="station-search-result-crs">{s.crs}</span>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </div>

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

      {submitting && (
        <p className="hint destination-form-status">
          <span className="spinner" /> Computing journeys for every listing…
        </p>
      )}

      <div className="form-actions">
        <button type="button" className="status-toggle-btn secondary" onClick={onCancel} disabled={submitting}>
          Cancel
        </button>
        <button type="submit" className="status-toggle-btn" disabled={submitting || !name.trim() || !station}>
          {submitting ? "Adding…" : "Add destination"}
        </button>
      </div>
    </form>
  );
}

export default function AdminPage() {
  const navigate = useNavigate();
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
      setDestinations(await api.destinations.list());
    } catch (err) {
      setDestinationError(err.message);
    }
  }

  useEffect(() => {
    load();
    loadBaselines();
    loadDestinations();
  }, []);

  async function handleDestinationAdded() {
    setShowDestinationForm(false);
    await loadDestinations();
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

  return (
    <div className="admin-page">
      <button className="back-btn" onClick={() => navigate("/")}>
        ← Back to Home
      </button>
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

      <h2>Frequent destinations</h2>
      <p className="hint">
        Places you travel to often (office, family, an airport terminal). Roost computes the
        best train journey from every station near a listing to each destination's day/time,
        once, when the listing is added — recompute manually from the listing detail page.
      </p>

      {destinationError && <p className="error">{destinationError}</p>}

      {destinations.length === 0 ? (
        <p className="empty-state">No destinations yet.</p>
      ) : (
        <ul className="admin-rules">
          {destinations.map((destination) => (
            <li key={destination.id} className="admin-rule-row">
              <span className="admin-rule-text">
                <div className="admin-rule-title">{destination.name}</div>
                <div className="admin-rule-sub">
                  <span className="badge badge-station">Station</span>
                  {DAY_OPTIONS[destination.day_of_week].label} · {destination.time} · nearest station{" "}
                  {destination.station_name} ({destination.crs})
                </div>
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
          ))}
        </ul>
      )}

      {showDestinationForm ? (
        <DestinationForm onAdded={handleDestinationAdded} onCancel={() => setShowDestinationForm(false)} />
      ) : (
        <button className="status-toggle-btn ghost" type="button" onClick={() => setShowDestinationForm(true)}>
          + New destination
        </button>
      )}
    </div>
  );
}
