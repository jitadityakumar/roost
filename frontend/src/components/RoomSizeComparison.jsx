// Renders a floorplan-comparison payload from
// GET /api/listings/{id}/floorplan-comparison (see app/floorplan/compare.py)
// per the approved mockup: https://claude.ai/code/artifact/d89fcfe7-493a-45cf-b508-476e94555049

function deltaClass(deltaPct) {
  if (deltaPct === null) return "bad";
  if (deltaPct >= 0) return "good";
  if (deltaPct >= -10) return "warn";
  return "bad";
}

function formatDelta(deltaPct, isNew) {
  if (deltaPct === null) return isNew ? "new" : "n/a";
  const sign = deltaPct >= 0 ? "+" : "";
  return `${sign}${deltaPct.toFixed(1)}%`;
}

function StatCard({ label, baseline, listing, deltaPct }) {
  return (
    <div className="rs-stat">
      <div className="rs-stat-label">{label}</div>
      <div className="rs-stat-figs">
        <span className="rs-stat-val">{listing.toFixed(0)} sq ft</span>
        <span className="rs-stat-base">vs {baseline.toFixed(0)}</span>
        <span className={`rs-stat-delta ${deltaClass(deltaPct)}`}>{formatDelta(deltaPct, listing > 0)}</span>
      </div>
    </div>
  );
}

function RoomRow({ room }) {
  const { rank, baseline_sqft: baselineSqft, listing_sqft: listingSqft, delta_pct: deltaPct } = room;
  const isNew = baselineSqft === null && listingSqft !== null;
  const maxVal = Math.max(baselineSqft || 0, listingSqft || 0) || 1;
  return (
    <div className="rs-room">
      <div className="rs-room-label">
        <span className="rs-room-num">{rank}</span>
        <span className={`rs-room-delta ${deltaClass(deltaPct)}`}>{formatDelta(deltaPct, isNew)}</span>
      </div>
      <div className="rs-bars">
        <div className="rs-bar-row">
          <div className="rs-bar-track">
            <div className="rs-bar-fill base" style={{ width: `${((baselineSqft || 0) / maxVal) * 100}%` }} />
          </div>
          <span className="rs-bar-val">{baselineSqft === null ? "— none" : `${baselineSqft.toFixed(0)} sq ft`}</span>
        </div>
        <div className="rs-bar-row">
          <div className="rs-bar-track">
            <div className="rs-bar-fill listing" style={{ width: `${((listingSqft || 0) / maxVal) * 100}%` }} />
          </div>
          <span className="rs-bar-val">{listingSqft === null ? "— none" : `${listingSqft.toFixed(0)} sq ft`}</span>
        </div>
      </div>
    </div>
  );
}

export default function RoomSizeComparison({ data }) {
  const { summary, types } = data;

  return (
    <div className="room-size-comparison">
      <div className="rs-legend">
        <span><i className="i-base" /> Your current flat</span>
        <span><i className="i-listing" /> This listing</span>
      </div>

      <div className="rs-summary">
        <StatCard label="Indoor total" baseline={summary.indoor.baseline} listing={summary.indoor.listing} deltaPct={summary.indoor.delta_pct} />
        <StatCard label="Outdoor total" baseline={summary.outdoor.baseline} listing={summary.outdoor.listing} deltaPct={summary.outdoor.delta_pct} />
        <StatCard label="Grand total" baseline={summary.grand.baseline} listing={summary.grand.listing} deltaPct={summary.grand.delta_pct} />
        {summary.floor_area_cross_check && (
          <StatCard
            label="Traced vs stated floor area"
            baseline={summary.floor_area_cross_check.stated_floor_area}
            listing={summary.floor_area_cross_check.traced_indoor}
            deltaPct={summary.floor_area_cross_check.delta_pct}
          />
        )}
      </div>

      {types.map((t) => (
        <div className="rs-group" key={t.type}>
          <div className="rs-group-head">
            <span className="rs-group-title">{t.label}</span>
            <span className="rs-group-total">
              {t.listing_total.toFixed(0)} sq ft listing <b>vs</b> {t.baseline_total.toFixed(0)} sq ft yours
            </span>
          </div>
          <div className="rs-rooms">
            {t.rooms.map((room) => (
              <RoomRow key={room.rank} room={room} />
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}
