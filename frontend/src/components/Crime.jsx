import { useEffect, useState } from "react";
import { api } from "../api.js";

// A null ratio means the baseline had zero of this category -- distinguish
// "n/a" (listing also has zero, nothing to compare) from "new" (listing has
// some, baseline has none), matching crime_compare.py's convention.
function ratioLabel(ratio, candidateIsPositive) {
  if (ratio === null) return candidateIsPositive ? "new" : "n/a";
  return `${ratio.toFixed(1)}x`;
}

function ratioBadgeClass(ratio) {
  if (ratio === null) return "badge-crime-neutral";
  if (ratio <= 1.1) return "badge-crime-good";
  if (ratio <= 1.5) return "badge-crime-warn";
  return "badge-crime-bad";
}

function BaselineSummaryRow({ baseline }) {
  if (baseline.error) {
    return (
      <li className="crime-baseline-row">
        <span className="crime-baseline-label">{baseline.label}</span>
        <span className="error">Couldn't load: {baseline.error}</span>
      </li>
    );
  }
  const ratio = baseline.comparison.score_ratio;
  const label = ratioLabel(ratio, baseline.comparison.candidate_score > 0);
  return (
    <li className="crime-baseline-row">
      <span className="crime-baseline-label">vs {baseline.label}</span>
      <span className={`badge ${ratioBadgeClass(ratio)}`}>{label}</span>
    </li>
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
      <ul className="crime-baseline-list">
        {data.baselines.map((baseline) => (
          <BaselineSummaryRow key={baseline.id} baseline={baseline} />
        ))}
      </ul>
      <button className="edit-btn" onClick={() => setExpanded((e) => !e)}>
        {expanded ? "Hide categories" : "Show categories"}
      </button>
      {expanded && <CategoryTable baselines={data.baselines} />}
    </div>
  );
}
