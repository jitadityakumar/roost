const TYPE_ICONS = {
  LONDON_UNDERGROUND: { icon: "Ⓤ", label: "Underground" },
  LONDON_OVERGROUND: { icon: "🚈", label: "Overground" },
  ELIZABETH_LINE: { icon: "🚈", label: "Elizabeth line" },
  DLR: { icon: "🚝", label: "DLR" },
  TRAMLINK: { icon: "🚋", label: "Tram" },
  NATIONAL_TRAIN: { icon: "🚆", label: "National Rail" },
};
const DEFAULT_TYPE_ICON = { icon: "🚉", label: "Station" };

function formatDistance(distance, unit) {
  if (distance === null || distance === undefined) return null;
  return `${Number(distance).toFixed(2)} ${unit || "mi"}`;
}

export default function NearestStations({ stations }) {
  if (!stations || stations.length === 0) return null;

  return (
    <ul className="station-list">
      {stations.map((s) => (
        <li key={s.name} className="station-row">
          <span className="station-icons">
            {(s.types && s.types.length > 0 ? s.types : ["_"]).map((t) => {
              const { icon, label } = TYPE_ICONS[t] || DEFAULT_TYPE_ICON;
              return (
                <span key={t} className="station-icon" title={label} aria-label={label}>
                  {icon}
                </span>
              );
            })}
          </span>
          <span className="station-name">{s.name}</span>
          <span className="station-distance">{formatDistance(s.distance, s.unit)}</span>
        </li>
      ))}
    </ul>
  );
}
