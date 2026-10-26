import { useState } from "react";
import { ResultRecord, SheetRecord } from "./api";
import { gbp } from "./ui";

type Row = ResultRecord | SheetRecord;

function Phone({ value }: { value: string }) {
  const [copied, setCopied] = useState(false);
  if (!value) return <span className="dash">—</span>;
  async function copy() {
    try {
      await navigator.clipboard.writeText(value);
      setCopied(true);
      setTimeout(() => setCopied(false), 1400);
    } catch {
      /* clipboard blocked: the number is still selectable */
    }
  }
  return (
    <button type="button" className="phone" onClick={copy} title="Copy number">
      <span>{value}</span>
      <span className="phone-hint" aria-live="polite">{copied ? "Copied" : "Copy"}</span>
    </button>
  );
}

function Others({ list }: { list: string[] }) {
  if (!list.length) return <span className="dash">—</span>;
  const [first, ...rest] = list;
  const line = (o: string) => {
    const i = o.lastIndexOf(": ");
    return i < 0 ? o : <><span className="other-name">{o.slice(0, i)}</span> <span className="mono">{o.slice(i + 2)}</span></>;
  };
  return (
    <div className="others">
      <div>{line(first)}</div>
      {rest.length > 0 && (
        <details>
          <summary>{rest.length} more</summary>
          {rest.map((o) => <div key={o}>{line(o)}</div>)}
        </details>
      )}
    </div>
  );
}

export function RecordsTable({ items, onRemove, showSearch = false, empty }: {
  items: Row[]; onRemove?: (uarn: string) => void; showSearch?: boolean; empty: string;
}) {
  return (
    <div className="table-wrap">
      <table className="records">
        <thead>
          <tr>
            <th>Business</th>
            <th>Address</th>
            <th className="num">Rateable value</th>
            <th>Phone</th>
            <th>Other numbers at this address</th>
            {onRemove && <th><span className="sr-only">Remove</span></th>}
          </tr>
        </thead>
        <tbody>
          {items.map((r) => (
            <tr key={r.uarn}>
              <td data-label="Business">
                <div className="biz">{r.business_name || <span className="dash">No business found</span>}</div>
                <div className="sub">{r.description}</div>
                {showSearch && "search" in r && <div className="sub from">from {r.search}</div>}
              </td>
              <td data-label="Address">
                <div>{r.business_address || r.address}</div>
                {r.business_address && <div className="sub vo" title={r.address}>VO record: {r.address}</div>}
                <div className="links">
                  <a href={r.source_url} target="_blank" rel="noreferrer" className="chip-link">Gov.uk record ↗</a>
                  <a href={r.google_maps_url} target="_blank" rel="noreferrer" className="chip-link">Google Maps ↗</a>
                </div>
              </td>
              <td data-label="Rateable value" className="num mono rv">{gbp(r.rv)}</td>
              <td data-label="Phone">
                <Phone value={r.phone} />
                {r.match_note && <div className="sub note">{r.match_note}</div>}
              </td>
              <td data-label="Other numbers"><Others list={r.other_numbers} /></td>
              {onRemove && (
                <td className="remove-cell">
                  <button type="button" className="icon-btn" onClick={() => onRemove(r.uarn)} aria-label={`Remove ${r.business_name || r.address}`} title="Remove from sheet">×</button>
                </td>
              )}
            </tr>
          ))}
          {items.length === 0 && (
            <tr className="empty-row"><td colSpan={onRemove ? 6 : 5}>{empty}</td></tr>
          )}
        </tbody>
      </table>
    </div>
  );
}
