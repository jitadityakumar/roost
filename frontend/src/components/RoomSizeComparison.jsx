// Renders a floorplan-comparison payload from
// GET /api/listings/{id}/floorplan-comparison (see app/floorplan/compare.py)
// per the approved mockup: https://claude.ai/code/artifact/d89fcfe7-493a-45cf-b508-476e94555049

// isNew (listing has a room/space the baseline doesn't) is a bonus, not a
// shortfall -- style it like a positive delta, not the same alarming red as
// "n/a" (baseline has it, the listing doesn't).
// `neutral` covers rows where a null side means "this figure couldn't be
// computed" rather than "this room doesn't exist" -- Hallway/Storage's
// remainder rows, where a null side means the internal sq ft input was
// never entered on that side, not that the space is missing or a bonus.
// Coloring that "new" (green) or "n/a" (red) would misrepresent it as a
// real gain/shortfall, so it gets a neutral grey badge instead.
function deltaClass(deltaPct, isNew, neutral) {
  if (deltaPct === null) return neutral ? "neutral" : isNew ? "good" : "bad";
  if (deltaPct >= 0) return "good";
  if (deltaPct >= -10) return "warn";
  return "bad";
}

function formatDelta(deltaPct, isNew, neutral) {
  if (deltaPct === null) return neutral ? "n/a" : isNew ? "new" : "n/a";
  const sign = deltaPct >= 0 ? "+" : "";
  return `${sign}${deltaPct.toFixed(1)}%`;
}

// Group totals are usually always-numeric (summed from traced shapes), but
// Hallway/Storage's totals are a remainder derived from an internal sq ft
// input that may not have been entered yet -- null rather than 0, so this
// renders "n/a" instead of implying there's no hallway/storage space.
function formatTotal(sqft) {
  return sqft === null ? "n/a" : `${sqft.toFixed(0)} sq ft`;
}

function StatCard({ label, baseline, listing, deltaPct }) {
  return (
    <div className="rs-stat">
      <div className="rs-stat-label">{label}</div>
      <div className="rs-stat-figs">
        <span className="rs-stat-val">{listing.toFixed(0)} sq ft</span>
        <span className="rs-stat-base">vs {baseline.toFixed(0)}</span>
        <span className={`rs-stat-delta ${deltaClass(deltaPct, listing > 0)}`}>{formatDelta(deltaPct, listing > 0)}</span>
      </div>
    </div>
  );
}

function RoomRow({ room, neutralUnknown }) {
  const { rank, baseline_sqft: baselineSqft, listing_sqft: listingSqft, delta_pct: deltaPct } = room;
  const isNew = !neutralUnknown && baselineSqft === null && listingSqft !== null;
  // Hallway/Storage's remainder can go negative (traced rooms exceeding the
  // entered internal sq ft) -- clamp bar *width* to 0 so a negative value
  // doesn't invert or overflow the bar, while still showing the real
  // (possibly negative) number in the label text below.
  const baseWidth = Math.max(baselineSqft || 0, 0);
  const listingWidth = Math.max(listingSqft || 0, 0);
  const maxVal = Math.max(baseWidth, listingWidth) || 1;
  return (
    <div className="rs-room">
      <div className="rs-room-label">
        <span className="rs-room-num">{rank}</span>
        <span className={`rs-room-delta ${deltaClass(deltaPct, isNew, neutralUnknown)}`}>{formatDelta(deltaPct, isNew, neutralUnknown)}</span>
      </div>
      <div className="rs-bars">
        <div className="rs-bar-row">
          <div className="rs-bar-track">
            <div className="rs-bar-fill base" style={{ width: `${(baseWidth / maxVal) * 100}%` }} />
          </div>
          <span className="rs-bar-val">{baselineSqft === null ? "— none" : `${baselineSqft.toFixed(0)} sq ft`}</span>
        </div>
        <div className="rs-bar-row">
          <div className="rs-bar-track">
            <div className="rs-bar-fill listing" style={{ width: `${(listingWidth / maxVal) * 100}%` }} />
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
              {formatTotal(t.listing_total)} listing <b>vs</b> {formatTotal(t.baseline_total)} yours
            </span>
          </div>
          <div className="rs-rooms">
            {t.type === "hallway_storage" && (
              <p className="rs-hallway-hint">Not traced directly -- the remainder of the internal sq ft after the rooms above.</p>
            )}
            {t.rooms.map((room) => (
              <RoomRow key={room.rank} room={room} neutralUnknown={t.type === "hallway_storage"} />
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}
