import { useEffect } from "react";
import {
  EMPTY_FILTERS,
  TENURE_OPTIONS,
  activeFilterCount,
  toggleIn,
  visibleOptions,
} from "../listingFilters.js";

const tenureLabel = (value) => TENURE_OPTIONS.find((o) => o.value === value)?.label || value;

export function FilterPills({ filters, onChange }) {
  const pills = [
    ...filters.tenure.map((v) => ({
      key: `t-${v}`,
      label: tenureLabel(v),
      remove: () => onChange({ ...filters, tenure: filters.tenure.filter((x) => x !== v) }),
    })),
    ...(filters.chainFree
      ? [{ key: "chain", label: "Chain free", remove: () => onChange({ ...filters, chainFree: false }) }]
      : []),
    ...filters.epc.map((b) => ({
      key: `e-${b}`,
      label: `EPC ${b}`,
      remove: () => onChange({ ...filters, epc: filters.epc.filter((x) => x !== b) }),
    })),
  ];
  return pills.map((p) => (
    <button key={p.key} type="button" className="filter-pill" onClick={p.remove} aria-label={`Remove filter ${p.label}`}>
      {p.label} <span aria-hidden="true">×</span>
    </button>
  ));
}

export function FiltersButton({ filters, onClick }) {
  const n = activeFilterCount(filters);
  return (
    <button type="button" className="filters-btn" aria-haspopup="dialog" onClick={onClick}>
      Filters{n > 0 && <span className="filter-count-badge">{n}</span>}
    </button>
  );
}

export function FiltersDialog({ options, filters, onChange, resultCount, onClose }) {
  useEffect(() => {
    const onKey = (e) => e.key === "Escape" && onClose();
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose]);

  const vis = visibleOptions(options, filters);
  const hasAny = vis.tenure.length > 0 || vis.epc.length > 0 || vis.showChainFree;

  return (
    <div className="modal-overlay filters-overlay" onClick={onClose}>
      <div
        className="modal filters-dialog"
        role="dialog"
        aria-modal="true"
        aria-label="Filters"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="filters-header">
          <h3>Filters</h3>
          <button
            type="button"
            className="link-btn"
            onClick={() => onChange(EMPTY_FILTERS)}
            disabled={activeFilterCount(filters) === 0}
          >
            Clear all
          </button>
        </div>

        {!hasAny && <p className="muted">Nothing to filter on yet.</p>}

        {vis.tenure.length > 0 && (
          <fieldset className="filter-group">
            <legend>Tenure</legend>
            <div className="filter-options">
              {vis.tenure.map((o) => (
                <button
                  key={o.value}
                  type="button"
                  className={`filter-option${filters.tenure.includes(o.value) ? " selected" : ""}${o.count === 0 ? " empty" : ""}`}
                  aria-pressed={filters.tenure.includes(o.value)}
                  onClick={() => onChange({ ...filters, tenure: toggleIn(filters.tenure, o.value) })}
                >
                  {o.label}
                  <span className="count-badge">{o.count}</span>
                </button>
              ))}
            </div>
          </fieldset>
        )}

        {vis.showChainFree && (
          <fieldset className="filter-group">
            <legend>Chain</legend>
            <div className="filter-options">
              <button
                type="button"
                className={`filter-option${filters.chainFree ? " selected" : ""}${vis.chainFreeCount === 0 ? " empty" : ""}`}
                aria-pressed={filters.chainFree}
                onClick={() => onChange({ ...filters, chainFree: !filters.chainFree })}
              >
                Chain free
                <span className="count-badge">{vis.chainFreeCount}</span>
              </button>
            </div>
          </fieldset>
        )}

        {vis.epc.length > 0 && (
          <fieldset className="filter-group">
            <legend>EPC band</legend>
            <div className="filter-options">
              {vis.epc.map((o) => (
                <button
                  key={o.value}
                  type="button"
                  className={`filter-option epc-option epc-${o.value}${filters.epc.includes(o.value) ? " selected" : ""}${o.count === 0 ? " empty" : ""}`}
                  aria-pressed={filters.epc.includes(o.value)}
                  onClick={() => onChange({ ...filters, epc: toggleIn(filters.epc, o.value) })}
                >
                  {o.label}
                  <span className="count-badge">{o.count}</span>
                </button>
              ))}
            </div>
          </fieldset>
        )}

        <button type="button" className="filters-show" onClick={onClose}>
          Show {resultCount} {resultCount === 1 ? "home" : "homes"}
        </button>
      </div>
    </div>
  );
}
