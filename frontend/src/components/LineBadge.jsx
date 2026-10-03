import { lookupLineBadge, textColorFor } from "../lineBadges.js";
import { logoUrlForType } from "./networkLogos.js";

// Renders both the large and small tile; CSS shows one by viewport width
// (`size="auto"`, the default) or the caller pins one with "lg" / "sm".
// Large: neutral logo cell (omitted when the gitignored logo is absent) +
// coloured name cell. Small: shape-coded code tile, full name on hover/focus.
export default function LineBadge({ name, size = "auto" }) {
  const badge = lookupLineBadge(name);
  const logoUrl = logoUrlForType(badge.logoType);
  const style = { backgroundColor: badge.color, color: textColorFor(badge) };

  return (
    <span className={`line-badge line-badge-${size} line-badge-${badge.group}`}>
      <span className="line-badge-lg-tile">
        {logoUrl && <img className="line-badge-logo" src={logoUrl} alt="" />}
        <span className="line-badge-name" style={style}>
          {badge.name}
        </span>
      </span>
      <span
        className="line-badge-sm-tile"
        style={style}
        tabIndex={0}
        role="img"
        aria-label={badge.name}
        data-label={badge.name}
      >
        {badge.code}
      </span>
    </span>
  );
}
