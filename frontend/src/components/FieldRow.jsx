import { useState } from "react";

export default function FieldRow({ listing, field, label, sourceField, editable, onSave, boolean, currency, editMode }) {
  const [editing, setEditing] = useState(false);
  const [value, setValue] = useState(listing[field] ?? "");

  const isEdited = listing.edited_fields && field in listing.edited_fields;
  const source = sourceField ? listing[sourceField] : null;

  function display(v) {
    if (v === null || v === undefined || v === "") return "—";
    if (boolean) return v ? "Yes" : "No";
    if (currency) return `£${v}`;
    return String(v);
  }

  async function save() {
    let parsed = value;
    if (boolean) parsed = value === "true" || value === true;
    else if (value !== "" && !isNaN(value) && typeof listing[field] === "number") parsed = Number(value);
    await onSave(field, parsed === "" ? null : parsed);
    setEditing(false);
  }

  return (
    <div className="field-row">
      <span className="field-label-col">
        <span className="field-label">{label}</span>
        {isEdited && <span className="badge badge-edited">edited by you</span>}
        {!isEdited && source && <span className="badge badge-source">{source}</span>}
      </span>
      {editing ? (
        <span className="field-edit">
          {boolean ? (
            <select value={String(value)} onChange={(e) => setValue(e.target.value)}>
              <option value="true">Yes</option>
              <option value="false">No</option>
              <option value="">Unknown</option>
            </select>
          ) : (
            <input value={value ?? ""} onChange={(e) => setValue(e.target.value)} />
          )}
          <button onClick={save}>Save</button>
          <button onClick={() => setEditing(false)}>Cancel</button>
        </span>
      ) : (
        <span className="field-value">
          {display(listing[field])}
          {editable && editMode && (
            <button className="edit-btn" onClick={() => setEditing(true)}>
              ✎
            </button>
          )}
        </span>
      )}
    </div>
  );
}
