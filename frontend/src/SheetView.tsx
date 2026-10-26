import { useCallback, useEffect, useMemo, useState } from "react";
import { api, ApiError, SheetRecord } from "./api";
import { RecordsTable } from "./RecordsTable";
import { ConfirmDialog, DownloadDialog, fileSafe, gbp, today } from "./ui";

export function SheetView({ employee, toast, onSheetChanged, onGoSearch }: {
  employee: string; toast: (t: string, tone?: "good" | "bad") => void;
  onSheetChanged: (total: number) => void; onGoSearch: () => void;
}) {
  const [rows, setRows] = useState<SheetRecord[] | null>(null);
  const [text, setText] = useState("");
  const [desc, setDesc] = useState("");
  const [search, setSearch] = useState("");
  const [downloadOpen, setDownloadOpen] = useState(false);
  const [clearOpen, setClearOpen] = useState(false);

  const load = useCallback(() => {
    api.sheet(employee)
      .then((d) => { setRows(d.items); onSheetChanged(d.total); })
      .catch(() => setRows([]));
  }, [employee, onSheetChanged]);
  useEffect(load, [load]);

  const descriptions = useMemo(() => [...new Set((rows ?? []).map((r) => r.description))].sort(), [rows]);
  const searches = useMemo(() => [...new Set((rows ?? []).map((r) => r.search))], [rows]);
  const shown = useMemo(() => {
    const t = text.trim().toLowerCase();
    return (rows ?? []).filter((r) =>
      (!desc || r.description === desc) && (!search || r.search === search) &&
      (!t || `${r.business_name} ${r.business_address} ${r.address} ${r.phone} ${r.postcode}`.toLowerCase().includes(t)));
  }, [rows, text, desc, search]);
  const filtered = rows !== null && shown.length !== rows.length;
  const totalRv = shown.reduce((a, r) => a + r.rv, 0);

  async function remove(uarn: string) {
    try {
      const r = await api.sheetRemove(employee, [uarn]);
      setRows((xs) => (xs ?? []).filter((x) => x.uarn !== uarn));
      onSheetChanged(r.total);
    } catch (err) {
      toast(err instanceof ApiError ? err.messages[0] : "Could not remove the row.", "bad");
    }
  }

  async function clear() {
    try {
      await api.sheetClear(employee);
      setRows([]);
      onSheetChanged(0);
      toast("Your sheet is now empty.");
    } catch (err) {
      toast(err instanceof ApiError ? err.messages[0] : "Could not clear the sheet.", "bad");
    }
  }

  if (rows === null) return <p className="muted loading">Loading your sheet…</p>;

  return (
    <section className="sheet">
      <header className="sheet-head">
        <div>
          <h2 className="sheet-title">My sheet</h2>
          <p className="tally">
            <span className="mono">{rows.length.toLocaleString()}</span> properties
            <span className="sep">/</span>
            <span className="mono">{searches.length}</span> {searches.length === 1 ? "search" : "searches"}
          </p>
        </div>
        {rows.length > 0 && (
          <div className="job-actions">
            <button type="button" className="btn btn-primary" onClick={() => setDownloadOpen(true)}>
              {filtered ? `Download ${shown.length} shown` : `Download all ${rows.length}`}
            </button>
            <button type="button" className="btn btn-quiet" onClick={() => setClearOpen(true)}>Clear sheet</button>
          </div>
        )}
      </header>

      {rows.length === 0 ? (
        <div className="empty-sheet">
          <p>Your sheet is empty.</p>
          <p className="muted">Run a search, then choose <strong>Add to My sheet</strong>. Each search you add is appended here.</p>
          <button type="button" className="btn btn-primary" onClick={onGoSearch}>Start a search</button>
        </div>
      ) : (
        <>
          <div className="filters">
            <label className="field">
              <span className="field-label">Find</span>
              <input value={text} onChange={(e) => setText(e.target.value)} placeholder="Name, address, phone…" />
            </label>
            <label className="field">
              <span className="field-label">Description</span>
              <select value={desc} onChange={(e) => setDesc(e.target.value)}>
                <option value="">All descriptions</option>
                {descriptions.map((d) => <option key={d}>{d}</option>)}
              </select>
            </label>
            <label className="field">
              <span className="field-label">Added from</span>
              <select value={search} onChange={(e) => setSearch(e.target.value)}>
                <option value="">All searches</option>
                {searches.map((s) => <option key={s}>{s}</option>)}
              </select>
            </label>
            {filtered && (
              <button type="button" className="btn btn-quiet reset" onClick={() => { setText(""); setDesc(""); setSearch(""); }}>
                Show all
              </button>
            )}
          </div>
          <p className="muted small shown-line">
            Showing <span className="mono">{shown.length}</span> of <span className="mono">{rows.length}</span> · combined rateable value <span className="mono">{gbp(totalRv)}</span>
          </p>
          <RecordsTable items={shown} onRemove={remove} showSearch empty="No rows match these filters." />
        </>
      )}

      <DownloadDialog
        open={downloadOpen}
        defaultName={fileSafe(`${employee} - My sheet - ${today()}`)}
        summary={filtered
          ? `${shown.length} of ${rows.length} rows (only the ones matching your filters).`
          : `All ${rows.length} rows in your sheet.`}
        onDownload={(name) => api.sheetDownload(employee, name, filtered ? shown.map((r) => r.uarn) : null)}
        onClose={() => setDownloadOpen(false)}
      />
      <ConfirmDialog
        open={clearOpen}
        title="Clear your sheet?"
        body={`All ${rows.length} rows will be removed from ${employee}’s sheet. Download it first if you need a copy.`}
        confirm="Clear sheet"
        onConfirm={clear}
        onClose={() => setClearOpen(false)}
      />
    </section>
  );
}
