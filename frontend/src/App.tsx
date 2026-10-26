import { useCallback, useEffect, useState } from "react";
import { api, Meta } from "./api";
import { SearchView } from "./SearchView";
import { SheetView } from "./SheetView";
import { NameDialog, storage, Toasts, useToasts, when } from "./ui";

type Tab = "search" | "sheet";

export default function App() {
  const [meta, setMeta] = useState<Meta | null>(null);
  const [employee, setEmployee] = useState(() => storage.get("ukbf.employee"));
  const [renaming, setRenaming] = useState(false);
  const [tab, setTab] = useState<Tab>(() => (storage.get("ukbf.tab") === "sheet" ? "sheet" : "search"));
  const [sheetCount, setSheetCount] = useState<number | null>(null);
  const toasts = useToasts();

  useEffect(() => { api.meta().then(setMeta).catch(() => setMeta(null)); }, []);
  useEffect(() => {
    if (employee) api.sheet(employee).then((d) => setSheetCount(d.total)).catch(() => undefined);
  }, [employee]);
  useEffect(() => storage.set("ukbf.tab", tab), [tab]);

  const saveName = (name: string) => {
    storage.set("ukbf.employee", name);
    setEmployee(name);
    setRenaming(false);
  };
  const onSheetChanged = useCallback((n: number) => setSheetCount(n), []);

  return (
    <div className="app">
      <header className="masthead">
        <div className="masthead-inner">
          <div className="brand">
            <span className="brand-mark" aria-hidden="true" />
            <span className="brand-name">Copilot</span>
          </div>
          <nav className="tabs" aria-label="Sections">
            <button type="button" className={tab === "search" ? "on" : ""} aria-current={tab === "search"} onClick={() => setTab("search")}>
              Search
            </button>
            <button type="button" className={tab === "sheet" ? "on" : ""} aria-current={tab === "sheet"} onClick={() => setTab("sheet")}>
              My sheet{sheetCount != null && <span className="count mono">{sheetCount}</span>}
            </button>
          </nav>
          {employee && (
            <button type="button" className="who" onClick={() => setRenaming(true)} title="Change name">
              <span className="who-initial" aria-hidden="true">{employee.slice(0, 1).toUpperCase()}</span>
              <span className="who-name">{employee}</span>
            </button>
          )}
        </div>
      </header>

      <main className="page">
        {!employee ? null : tab === "search" ? (
          <SearchView meta={meta} employee={employee} toast={toasts.push} onSheetChanged={onSheetChanged} />
        ) : (
          <SheetView employee={employee} toast={toasts.push} onSheetChanged={onSheetChanged} onGoSearch={() => setTab("search")} />
        )}
      </main>

      <footer className="foot">
        {meta?.voa_dataset ? (
          <span>
            VO {meta.voa_dataset.list_year} rating list · {Number(meta.voa_dataset.row_count).toLocaleString()} properties ·
            updated {when(meta.voa_dataset.imported_at)}
            {meta.contact_providers.length === 0 && <strong className="warn"> · phone data not loaded yet</strong>}
          </span>
        ) : (
          <span className="warn">The rating list hasn’t been loaded on this server yet.</span>
        )}
        <span>Business listings: Overture Maps Foundation (CDLA-Permissive-2.0)</span>
      </footer>

      <NameDialog open={!employee || renaming} initial={employee} onSave={saveName} onClose={employee ? () => setRenaming(false) : undefined} />
      <Toasts items={toasts.items} />
    </div>
  );
}
