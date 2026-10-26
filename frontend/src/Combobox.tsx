import { useEffect, useId, useRef, useState } from "react";

export type Option = { value: string; count: number };

/** Text box with a suggestion list: type freely, or pick with mouse / arrow keys + Enter. */
export function Combobox({ label, value, onChange, load, placeholder, onPick, inputClass }: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  load: (q: string) => Promise<Option[]>;
  placeholder?: string;
  /** Called after an option is picked; return true to keep the list open (e.g. to drill down). */
  onPick?: (v: string) => boolean | void;
  inputClass?: string;
}) {
  const id = useId();
  const [open, setOpen] = useState(false);
  const [options, setOptions] = useState<Option[]>([]);
  const [active, setActive] = useState(-1);
  const [loading, setLoading] = useState(false);
  const seq = useRef(0);
  const wrap = useRef<HTMLDivElement>(null);
  const list = useRef<HTMLUListElement>(null);

  function fetchFor(q: string) {
    const n = ++seq.current;
    setLoading(true);
    load(q)
      .then((opts) => { if (n === seq.current) { setOptions(opts); setActive(-1); } })
      .catch(() => { if (n === seq.current) setOptions([]); })
      .finally(() => { if (n === seq.current) setLoading(false); });
  }

  // refetch (debounced) while typing
  useEffect(() => {
    if (!open) return;
    const t = setTimeout(() => fetchFor(value), 140);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [value, open]);

  // close when clicking elsewhere
  useEffect(() => {
    const onDown = (e: MouseEvent) => { if (!wrap.current?.contains(e.target as Node)) setOpen(false); };
    document.addEventListener("mousedown", onDown);
    return () => document.removeEventListener("mousedown", onDown);
  }, []);

  useEffect(() => {
    list.current?.querySelector<HTMLElement>(`[data-i="${active}"]`)?.scrollIntoView({ block: "nearest" });
  }, [active]);

  function pick(v: string) {
    onChange(v);
    const keepOpen = onPick?.(v);
    if (!keepOpen) setOpen(false);
  }

  function onKey(e: React.KeyboardEvent<HTMLInputElement>) {
    if (e.key === "ArrowDown") { e.preventDefault(); setOpen(true); setActive((a) => Math.min(a + 1, options.length - 1)); }
    else if (e.key === "ArrowUp") { e.preventDefault(); setActive((a) => Math.max(a - 1, 0)); }
    else if (e.key === "Enter" && open && active >= 0 && options[active]) { e.preventDefault(); pick(options[active].value); }
    else if (e.key === "Escape") setOpen(false);
  }

  const listId = `${id}-list`;
  return (
    <div className="field combo" ref={wrap}>
      <label className="field-label" htmlFor={`${id}-input`}>{label}</label>
      <input
        id={`${id}-input`}
        className={inputClass}
        role="combobox"
        aria-expanded={open}
        aria-controls={listId}
        aria-autocomplete="list"
        aria-activedescendant={active >= 0 ? `${id}-o${active}` : undefined}
        autoComplete="off"
        value={value}
        placeholder={placeholder}
        onChange={(e) => { onChange(e.target.value); setOpen(true); }}
        onFocus={() => setOpen(true)}
        onKeyDown={onKey}
      />
      {open && (
        <ul className="combo-list" id={listId} role="listbox" ref={list}>
          {options.map((o, i) => (
            <li
              key={o.value}
              id={`${id}-o${i}`}
              data-i={i}
              role="option"
              aria-selected={i === active}
              className={i === active ? "active" : ""}
              onMouseDown={(e) => { e.preventDefault(); pick(o.value); }}
              onMouseEnter={() => setActive(i)}
            >
              <span>{o.value}</span>
              <span className="combo-count">{o.count.toLocaleString()}</span>
            </li>
          ))}
          {!loading && options.length === 0 && <li className="combo-empty">No matches</li>}
        </ul>
      )}
    </div>
  );
}
