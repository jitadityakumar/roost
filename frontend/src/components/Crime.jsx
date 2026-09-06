import { useEffect, useState } from "react";
import { api } from "../api.js";

// A null ratio means the baseline had zero of this category -- distinguish
// "n/a" (listing also has zero, nothing to compare) from "new" (listing has
// some, baseline has none), matching crime_compare.py's convention.
function ratioLabel(ratio, candidateIsPositive) {
  if (ratio === null) return candidateIsPositive ? "new" : "n/a";
  return `${ratio.toFixed(1)}x`;
}

function barFillClass(ratio, isProperty) {
  if (isProperty) return "crime-bar-fill-property";
  if (ratio === null) return "crime-bar-fill-neutral";
  if (ratio <= 1.1) return "crime-bar-fill-good";
  if (ratio <= 1.5) return "crime-bar-fill-warn";
  return "crime-bar-fill-bad";
}

// With a reference baseline configured (e.g. "Barnes"), every row is shown
// relative to *its* score rather than the listing's -- the reference always
// reads 1.0x. Falls back to the listing-as-base behavior (each baseline's
// own score_ratio, already computed server-side as candidate/baseline) when
// no baseline has been marked as the reference yet.
function relativeRatio(score, referenceScore) {
  if (referenceScore === 0) return null;
  return score / referenceScore;
}

function CrimeBarChart({ baselines, propertyPostcode }) {
  const ok = baselines.filter((b) => b.comparison);
  const errored = baselines.filter((b) => b.error);
  const reference = ok.find((b) => b.is_reference) ?? null;
  const referenceScore = reference ? reference.comparison.baseline_score : null;

  const rows = ok.length
    ? [
        {
          key: "property",
          label: "This property",
          postcode: propertyPostcode ?? null,
          score: ok[0].comparison.candidate_score,
          candidateScore: ok[0].comparison.candidate_score,
          ratio:
            referenceScore === null
              ? 1
              : relativeRatio(ok[0].comparison.candidate_score, referenceScore),
          isProperty: true,
        },
        ...ok.map((b) => ({
          key: b.id,
          label: b.label,
          postcode: b.postcode,
          score: b.comparison.baseline_score,
          candidateScore: b.comparison.candidate_score,
          ratio:
            referenceScore === null
              ? b.comparison.score_ratio
              : b.is_reference
                ? 1
                : relativeRatio(b.comparison.baseline_score, referenceScore),
          isProperty: false,
        })),
      ].sort((a, b) => b.score - a.score)
    : [];

  // Pad the scale a little past the largest score so the longest bar
  // doesn't touch the row's right edge.
  const maxScore = Math.max(0, ...rows.map((r) => r.score));
  const scale = maxScore > 0 ? maxScore * 1.15 : 1;

  return (
    <div className="crime-bar-chart">
      {rows.map((row) => {
        const ratioText =
          row.ratio === null ? ratioLabel(null, row.candidateScore > 0) : `${row.ratio.toFixed(1)}×`;
        const tooltip = row.postcode
          ? `${row.label} (${row.postcode}) — score ${row.score.toFixed(1)}, ${ratioText}`
          : `${row.label} — score ${row.score.toFixed(1)}, ${ratioText}`;
        return (
          <div key={row.key} className="crime-bar-row" title={tooltip}>
            <div className="crime-bar-label">
              <span className="crime-bar-label-name">{row.label}</span>
              {row.postcode && <span className="crime-bar-postcode">{row.postcode}</span>}
            </div>
            <div className="crime-bar-track">
              <div
                className={`crime-bar-fill ${barFillClass(row.ratio, row.isProperty)}`}
                style={{ width: `${(row.score / scale) * 100}%` }}
              />
            </div>
            <span className="crime-bar-ratio">{ratioText}</span>
          </div>
        );
      })}
      {errored.map((b) => (
        <div
          key={b.id}
          className="crime-bar-row"
          title={`Couldn't load: ${b.error}`}
          aria-label={`${b.label}: couldn't load, ${b.error}`}
        >
          <div className="crime-bar-label">
            <span className="crime-bar-label-name">{b.label}</span>
            <span className="crime-bar-postcode">{b.postcode}</span>
          </div>
          <span className="crime-bar-error-text">Couldn't load</span>
        </div>
      ))}
    </div>
  );
}

function CategoryTable({ baselines }) {
  const ok = baselines.filter((b) => b.comparison);
  if (ok.length === 0) return null;
  // Each baseline's category list is computed independently server-side
  // (union of the listing's categories with that baseline's own), so two
  // baselines can disagree on which categories appear -- union them here
  // rather than assuming ok[0]'s list covers every row.
  const categories = [...new Set(ok.flatMap((b) => b.comparison.categories.map((c) => c.category)))].sort();
  const candidateCountFor = (category) =>
    ok[0].comparison.categories.find((c) => c.category === category)?.candidate_count ?? 0;

  return (
    <div className="crime-category-table-wrap">
      <table className="crime-category-table">
        <thead>
          <tr>
            <th>Category</th>
            <th>Listing</th>
            {ok.map((b) => (
              <th key={b.id}>{b.label}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {categories.map((category) => {
            const candidateCount = candidateCountFor(category);
            return (
              <tr key={category}>
                <td>{category}</td>
                <td>{candidateCount}</td>
                {ok.map((b) => {
                  const row = b.comparison.categories.find((c) => c.category === category);
                  const baselineCount = row?.baseline_count ?? 0;
                  const ratio = row?.ratio ?? null;
                  return (
                    <td key={b.id}>{`${baselineCount} (${ratioLabel(ratio, candidateCount > 0)})`}</td>
                  );
                })}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

export default function Crime({ listingId, ready }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [expanded, setExpanded] = useState(false);

  useEffect(() => {
    if (!ready) return;
    let cancelled = false;
    setData(null);
    setError(null);
    api
      .crime(listingId)
      .then((result) => {
        if (!cancelled) setData(result);
      })
      .catch((err) => {
        if (!cancelled) setError(err.message);
      });
    return () => {
      cancelled = true;
    };
  }, [listingId, ready]);

  if (!ready) return <p className="coming-soon">Waiting for listing details…</p>;
  if (error) return <p className="error">Couldn't load crime data: {error}</p>;
  if (data === null) return <p>Loading…</p>;
  if (data.unavailable) return <p className="coming-soon">{data.unavailable}</p>;
  if (data.baselines.length === 0) {
    return <p className="coming-soon">Add a baseline in Admin to compare crime data.</p>;
  }

  return (
    <div className="crime-section">
      <CrimeBarChart baselines={data.baselines} propertyPostcode={data.postcode} />
      <button className="crime-details-toggle" onClick={() => setExpanded((e) => !e)}>
        {expanded ? "Hide details" : "Show details"}
      </button>
      {expanded && <CategoryTable baselines={data.baselines} />}
    </div>
  );
}
