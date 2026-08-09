import { useEffect, useState } from "react";
import { api } from "../api.js";

function formatMoney(v) {
  return `£${Math.round(v).toLocaleString("en-GB")}`;
}

// mirrors mortgage-calculator's own convention: elapsed = fromMonth - 1;
// 0y0m -> "From the start"; otherwise "Xy" / "Ym" / "Xy Ym"
function formatMonthCompact(fromMonth) {
  const elapsed = fromMonth - 1;
  if (elapsed === 0) return "From the start";
  const years = Math.floor(elapsed / 12);
  const months = elapsed % 12;
  return [years > 0 ? `${years}y` : null, months > 0 ? `${months}m` : null]
    .filter(Boolean)
    .join(" ");
}

function Row({ label, value, accent }) {
  return (
    <div className="field-row">
      <span className="field-label-col">
        <span className="field-label">{label}</span>
      </span>
      <span className={accent ? "field-value mortgage-accent" : "field-value"}>{value}</span>
    </div>
  );
}

export default function Mortgage({ listingId, priceGbp, ready }) {
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (!ready || priceGbp == null) return;
    let cancelled = false;
    setResult(null);
    setError(null);
    api
      .mortgage(listingId)
      .then((data) => {
        if (cancelled) return;
        if (data.error) setError(data.error);
        else setResult(data.result);
      })
      .catch((err) => {
        if (!cancelled) setError(err.message);
      });
    return () => {
      cancelled = true;
    };
  }, [listingId, ready, priceGbp]);

  if (!ready) return <p className="coming-soon">Waiting for listing details…</p>;
  if (priceGbp == null) return <p className="coming-soon">No price on this listing yet.</p>;
  if (error) return <p className="error">Couldn't load mortgage estimate: {error}</p>;
  if (result === null) return <p>Loading…</p>;
  if (result.monthlyPayments.length === 0) {
    return <p className="error">Couldn't load mortgage estimate: no payment schedule returned.</p>;
  }

  const initialPayment = result.monthlyPayments[0].payment;
  const payoffElapsed = result.payoffMonth - 1;
  const payoffYears = Math.floor(payoffElapsed / 12);
  const payoffMonths = payoffElapsed % 12;

  return (
    <div className="mortgage-summary">
      <Row label="Initial monthly payment" value={formatMoney(initialPayment)} accent />
      <Row
        label="Time to payoff"
        value={[payoffYears > 0 ? `${payoffYears}y` : null, payoffMonths > 0 ? `${payoffMonths}m` : null]
          .filter(Boolean)
          .join(" ")}
      />
      <Row label="Stamp duty" value={formatMoney(result.sdltPaid)} />
      <Row label="Total interest paid" value={formatMoney(result.totalInterestPaid)} />
      <Row label="Total paid" value={formatMoney(result.totalPaid)} />
      <Row label="Property value" value={formatMoney(priceGbp)} />

      {result.monthlyPayments.length > 1 && (
        <div className="mortgage-schedule">
          <h5>Monthly payment over time</h5>
          <ul className="mortgage-schedule-list">
            {result.monthlyPayments.map((p) => (
              <li key={p.fromMonth} className="mortgage-schedule-row">
                <span>
                  {formatMonthCompact(p.fromMonth)} ({p.isVariable ? "variable" : "fixed"})
                </span>
                <span>{formatMoney(p.payment)}/mo</span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
