import { useState } from "react";

export default function CollapsibleSection({
  title,
  defaultExpanded,
  actions,
  hasData = true,
  emptyMessage,
  className,
  children,
}) {
  const [expanded, setExpanded] = useState(defaultExpanded);

  return (
    <div className={`collapsible-section ${expanded ? "expanded" : ""} ${className || ""}`}>
      <div className="section-heading">
        <button
          className="collapsible-section-toggle"
          aria-expanded={expanded}
          onClick={() => setExpanded((v) => !v)}
        >
          <span className="chev-btn">▸</span>
          <h3>{title}</h3>
        </button>
        {actions}
      </div>
      {expanded && (hasData ? children : <p className="empty-state">{emptyMessage}</p>)}
    </div>
  );
}
