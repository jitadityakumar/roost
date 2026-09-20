import { useEffect, useState } from "react";
import { api } from "../api.js";
import CollapsibleSection from "./CollapsibleSection.jsx";
import { NEUTRAL_GREY, PARTY_SHORT, partyColor, readableTextColor } from "../partyColors.js";

const TITLE_WORDS = new Set(["mr", "mrs", "ms", "miss", "dr", "dame", "sir", "lord", "lady", "rt", "hon", "mp", "prof"]);

export function initials(name) {
  const words = (name || "")
    .replace(/[.,]/g, "")
    .split(/\s+/)
    .filter((w) => w && !TITLE_WORDS.has(w.toLowerCase()));
  if (words.length === 0) return "?";
  const first = words[0][0];
  const last = words.length > 1 ? words[words.length - 1][0] : "";
  return (first + last).toUpperCase();
}

export function headlineText(headline) {
  if (headline.status === "majority") return `${headline.party} majority`;
  return headline.party ? `No overall majority. ${headline.party} largest party` : "No overall majority";
}

export function headlineSeats(headline) {
  return headline.seats != null
    ? `${headline.seats} of ${headline.total} seats`
    : `${headline.total} seats`;
}

export function formatChange(change) {
  if (change == null) return { text: "—", tone: "muted" };
  if (change === 0) return { text: "0", tone: "muted" };
  return change > 0 ? { text: `+${change}`, tone: "up" } : { text: `−${Math.abs(change)}`, tone: "down" };
}

function parishText(parish) {
  if (!parish) return "—";
  return /unparished/i.test(parish) ? "None (unparished)" : parish;
}

const fmt = (n) => (n == null ? "—" : n.toLocaleString("en-GB"));

function Portrait({ mp }) {
  const [failed, setFailed] = useState(false);
  if (failed || !mp.thumbnail_url) {
    return (
      <div className="lp-portrait lp-portrait-fallback" aria-hidden="true">
        {initials(mp.name)}
      </div>
    );
  }
  return (
    <img
      className="lp-portrait"
      src={mp.thumbnail_url}
      alt=""
      loading="lazy"
      onError={() => setFailed(true)}
    />
  );
}

function MpBlock({ mp }) {
  if (!mp) {
    return (
      <div className="lp-block">
        <h4 className="lp-label">Member of Parliament</h4>
        <p className="empty-state">MP details aren't available for this constituency yet.</p>
      </div>
    );
  }
  const colour = mp.party_colour || NEUTRAL_GREY;
  return (
    <div className="lp-block">
      <h4 className="lp-label">Member of Parliament</h4>
      <div className="lp-mp">
        <Portrait mp={mp} />
        <div>
          <div className="lp-mp-name">{mp.name}</div>
          {mp.party_name && (
            <span className="lp-pill" style={{ background: colour, color: readableTextColor(colour) }}>
              {mp.party_name}
            </span>
          )}
          <div className="lp-muted">{mp.constituency}</div>
        </div>
      </div>
      <div className="lp-stats">
        <div>
          <div className="lp-stat-value">{fmt(mp.majority)}</div>
          <div className="lp-muted">2024 majority</div>
        </div>
        <div>
          <div className="lp-stat-value">{mp.turnout_pct != null ? `${mp.turnout_pct}%` : "—"}</div>
          <div className="lp-muted">turnout · {fmt(mp.turnout)} votes</div>
        </div>
        <div>
          <div className="lp-stat-value">{mp.result || "—"}</div>
          <div className="lp-muted">2024 general election</div>
        </div>
      </div>
    </div>
  );
}

function CouncilBlock({ council }) {
  return (
    <div className="lp-block">
      <h4 className="lp-label">Local council</h4>
      {council ? (
        <dl className="lp-facts">
          <dt>Council</dt>
          <dd>{council.name}</dd>
          <dt>County council</dt>
          <dd>{council.county || "None (unitary authority)"}</dd>
          <dt>Ward</dt>
          <dd>{council.ward || "—"}</dd>
          <dt>Parish</dt>
          <dd>{parishText(council.parish)}</dd>
        </dl>
      ) : (
        <p className="empty-state">Council details aren't available yet.</p>
      )}
    </div>
  );
}

function ControlBlock({ control }) {
  if (!control) {
    return (
      <div className="lp-block lp-control">
        <h4 className="lp-label">Council control</h4>
        <p className="empty-state">Council seat data isn't available for this council yet.</p>
      </div>
    );
  }
  const { headline, parties, total, majority_threshold: threshold } = control;
  return (
    <div className="lp-block lp-control">
      <h4 className="lp-label">Council control</h4>
      <div className="lp-headline">
        <strong>{headlineText(headline)}</strong>
        <span className="lp-muted">
          {headlineSeats(headline)} · as of May {control.year}
        </span>
      </div>
      <div className="lp-bar-wrap">
        <div className="lp-bar" role="img" aria-label="Council seat split">
          {parties
            .filter((p) => p.seats > 0)
            .map((p) => (
              <div
                key={p.key}
                className="lp-bar-seg"
                style={{ width: `${(p.seats / total) * 100}%`, background: partyColor(p.key) }}
                title={`${p.name}: ${p.seats}`}
              >
                {(p.seats / total) * 100 >= 10 ? `${PARTY_SHORT[p.key]} ${p.seats}` : ""}
              </div>
            ))}
        </div>
        <div className="lp-majority-marker" style={{ left: `${(threshold / total) * 100}%` }}>
          <span>majority: {threshold}</span>
        </div>
      </div>
      <div className="lp-table-wrap">
        <table className="lp-table">
          <thead>
            <tr>
              <th>Party</th>
              <th>Seats</th>
              <th>Share</th>
              <th>vs {control.previous_year ?? "previous"}</th>
            </tr>
          </thead>
          <tbody>
            {parties.map((p) => {
              const change = formatChange(p.change);
              return (
                <tr key={p.key}>
                  <td>
                    <span className="lp-dot" style={{ background: partyColor(p.key) }} />
                    {p.name}
                  </td>
                  <td>{p.seats}</td>
                  <td>{p.share}%</td>
                  <td className={`lp-change lp-change-${change.tone}`}>{change.text}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export default function LocalPolitics({ listingId, ready, defaultExpanded }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [refreshing, setRefreshing] = useState(false);
  const [refreshMessage, setRefreshMessage] = useState(null);

  useEffect(() => {
    if (!ready) return;
    setData(null);
    setError(null);
    setRefreshMessage(null);
    api
      .localPolitics(listingId)
      .then(setData)
      .catch((err) => setError(err.message));
  }, [listingId, ready]);

  async function handleRefresh() {
    setRefreshing(true);
    setRefreshMessage(null);
    try {
      const result = await api.refreshLocalPolitics(listingId);
      setData(result);
      if (!result.refresh.ok) setRefreshMessage(result.refresh.message);
    } catch (err) {
      // Stored data is untouched on failure -- keep showing it.
      setRefreshMessage(`Refresh failed: ${err.message}`);
    } finally {
      setRefreshing(false);
    }
  }

  return (
    <CollapsibleSection
      title="Local Politics"
      defaultExpanded={defaultExpanded}
      actions={
        ready && (
          <button className="lp-refresh" onClick={handleRefresh} disabled={refreshing}>
            {refreshing ? "Refreshing…" : "Refresh"}
          </button>
        )
      }
    >
      {refreshMessage && (
        <p role="alert" className="error">
          {refreshMessage}
        </p>
      )}
      {!ready ? (
        <p className="coming-soon">Waiting for listing details…</p>
      ) : error ? (
        <p className="error">Couldn't load local politics: {error}</p>
      ) : data === null ? (
        <p>Loading…</p>
      ) : !data.has_data ? (
        <p className="empty-state">
          Nothing could be found for this listing's area yet. Use Refresh to try again.
        </p>
      ) : (
        <div className="local-politics">
          <div className="lp-columns">
            <MpBlock mp={data.mp} />
            <CouncilBlock council={data.council} />
          </div>
          <ControlBlock control={data.control} />
          <p className="lp-source lp-muted">
            Sources: Open Council Data UK (council seats, snapshot after the May {data.control?.year ?? ""}
            {" "}elections; later by-elections aren't reflected), UK Parliament Members API (MP), postcodes.io
            (area).
          </p>
        </div>
      )}
    </CollapsibleSection>
  );
}
