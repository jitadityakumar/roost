import { useEffect, useState } from "react";
import { api } from "../api.js";

const IN_FLIGHT = ["queued", "running"];
const POLL_MS = 2000;

function formatDate(iso) {
  if (!iso) return null;
  const d = new Date(`${iso}T00:00:00`);
  return Number.isNaN(d.getTime())
    ? iso
    : d.toLocaleDateString("en-GB", { day: "numeric", month: "long", year: "numeric" });
}

function isExpired(iso) {
  if (!iso) return false;
  return new Date(`${iso}T23:59:59`) < new Date();
}

// Issue #115: manually attach a gov.uk EPC certificate URL and show what the
// fetch job parsed from it. `job` is the latest epc_certificate_fetch job
// row (or undefined); `onUpdate` receives the refreshed listing after
// attach/remove; `onReload` re-fetches the listing + jobs (used to poll
// while the fetch is in flight).
export default function EpcCertificate({ listing, job, onUpdate, onReload }) {
  const [url, setUrl] = useState("");
  const [replacing, setReplacing] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  const cert = listing.epc_certificate;
  const attachedUrl = listing.epc_certificate_url;
  const inFlight = !!attachedUrl && !cert && (!job || IN_FLIGHT.includes(job.status));
  const failed = !!attachedUrl && !cert && job?.status === "failed";

  useEffect(() => {
    if (!inFlight) return undefined;
    const t = setTimeout(onReload, POLL_MS);
    return () => clearTimeout(t);
  }, [inFlight, job, onReload]);

  async function attach(e) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      onUpdate(await api.setEpcCertificate(listing.id, url.trim()));
      setUrl("");
      setReplacing(false);
      // onUpdate only swaps the listing; `jobs` still holds the previous
      // fetch job (done/failed), which would hide "Fetching…" and stop
      // polling. Reload so the new queued job is seen.
      onReload();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  async function remove() {
    if (!window.confirm("Remove the attached EPC certificate? Its stored details will be deleted.")) return;
    setBusy(true);
    setError(null);
    try {
      onUpdate(await api.removeEpcCertificate(listing.id));
      onReload();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  const form = (
    <form className="epc-cert-form" onSubmit={attach}>
      <input
        type="url"
        placeholder="https://find-energy-certificate.service.gov.uk/energy-certificate/…"
        aria-label="EPC certificate URL"
        value={url}
        onChange={(e) => setUrl(e.target.value)}
        required
      />
      <button type="submit" disabled={busy || !url.trim()}>
        {attachedUrl ? "Replace" : "Attach certificate"}
      </button>
      {replacing && (
        <button type="button" onClick={() => setReplacing(false)}>
          Cancel
        </button>
      )}
    </form>
  );

  return (
    <div className="epc-certificate">
      {!attachedUrl && (
        <>
          <p className="meta">
            Rightmove often only has a low-quality EPC image. Paste the certificate URL from gov.uk “Find an
            energy certificate” to add the full address, ratings and breakdown.
          </p>
          {form}
        </>
      )}

      {attachedUrl && (
        <p className="epc-cert-source">
          <a href={attachedUrl} target="_blank" rel="noreferrer">
            EPC certificate ↗
          </a>
          {" · "}
          <button type="button" className="link-btn" onClick={() => setReplacing((v) => !v)}>
            Replace
          </button>
          {" · "}
          <button type="button" className="link-btn" onClick={remove} disabled={busy}>
            Remove
          </button>
        </p>
      )}
      {attachedUrl && replacing && form}
      {error && <p className="pending-banner failed">{error}</p>}

      {inFlight && <p className="meta">Fetching certificate…</p>}
      {failed && (
        <p className="pending-banner failed">
          Couldn’t read the certificate{job.last_error ? `: ${job.last_error}` : ""}. Use Replace with the same URL
          to retry.
        </p>
      )}

      {cert && (
        <>
          {cert.postcode_mismatch && (
            <p className="pending-banner failed" role="alert">
              Postcode mismatch: this certificate is for {cert.postcode}, but the listing’s postcode is{" "}
              {listing.postcode}. Check it is the right certificate.
            </p>
          )}

          <p className="epc-cert-address">{cert.address}</p>
          <p className="epc-cert-summary">
            <b>
              {cert.current_rating} ({cert.current_score})
            </b>{" "}
            now
            {cert.potential_rating && (
              <>
                {" "}
                · potential{" "}
                <b>
                  {cert.potential_rating} ({cert.potential_score})
                </b>
              </>
            )}
          </p>
          <p className="meta">
            {cert.certificate_date && <>Certificate dated {formatDate(cert.certificate_date)}. </>}
            {cert.valid_until &&
              (isExpired(cert.valid_until) ? (
                <span className="epc-expired">Expired {formatDate(cert.valid_until)}. </span>
              ) : (
                <>Valid until {formatDate(cert.valid_until)}. </>
              ))}
            Older certificates may not reflect later improvements.
          </p>

          {cert.features?.length > 0 && (
            <>
              <h4>Breakdown of property’s energy performance</h4>
              <table className="epc-table">
                <thead>
                  <tr>
                    <th>Feature</th>
                    <th>Description</th>
                    <th>Rating</th>
                  </tr>
                </thead>
                <tbody>
                  {cert.features.map((f, i) => (
                    <tr key={`${f.feature}-${i}`}>
                      <th scope="row">{f.feature}</th>
                      <td>{f.description}</td>
                      <td>{f.rating}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </>
          )}

          {cert.steps?.length > 0 && (
            <>
              <h4>Steps you could take to save energy</h4>
              <table className="epc-table">
                <thead>
                  <tr>
                    <th>Step</th>
                    <th>Typical cost</th>
                    <th>Yearly saving</th>
                    <th>Rating after</th>
                  </tr>
                </thead>
                <tbody>
                  {cert.steps.map((s) => (
                    <tr key={s.step}>
                      <th scope="row">
                        {s.step}. {s.title}
                      </th>
                      <td>{s.installation_cost ?? "—"}</td>
                      <td>{s.yearly_saving_gbp != null ? `£${s.yearly_saving_gbp.toLocaleString("en-GB")}` : "—"}</td>
                      <td>{s.potential_rating ?? "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </>
          )}
        </>
      )}
    </div>
  );
}
