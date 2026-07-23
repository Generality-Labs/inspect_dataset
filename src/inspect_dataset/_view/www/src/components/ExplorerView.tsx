import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { AgGridReact } from "ag-grid-react";
import {
  AllCommunityModule,
  ModuleRegistry,
  themeQuartz,
} from "ag-grid-community";
import type { ColDef, GridApi, ICellRendererParams } from "ag-grid-community";
import { useStore } from "../store";
import {
  fetchExplorerRecord,
  fetchExplorerRecords,
  fetchExplorerSchema,
  fetchScanners,
  runExplorerScan,
} from "../api";
import type {
  CellValue,
  ExploreFinding,
  ExploreRecordDetail,
  ExploreRow,
  ScannerInfo,
  SchemaField,
  SchemaInfo,
} from "../types";

// Readable, theme-adaptive row selection color for the AG Grid checkbox
// selection (the previous dark default made cell text unreadable).
const gridTheme = themeQuartz.withParams({
  selectedRowBackgroundColor: "rgba(13, 110, 253, 0.14)",
});

// ── Resizable side panel (drag handle on the left edge) ─────────────────────

function ResizablePanel({
  width,
  onWidth,
  min = 280,
  max = 900,
  children,
}: {
  width: number;
  onWidth: (w: number) => void;
  min?: number;
  max?: number;
  children: React.ReactNode;
}) {
  const dragging = useRef(false);

  useEffect(() => {
    const move = (e: MouseEvent) => {
      if (!dragging.current) return;
      const next = window.innerWidth - e.clientX;
      onWidth(Math.min(max, Math.max(min, next)));
    };
    const up = () => {
      if (!dragging.current) return;
      dragging.current = false;
      document.body.style.userSelect = "";
      document.body.style.cursor = "";
    };
    window.addEventListener("mousemove", move);
    window.addEventListener("mouseup", up);
    return () => {
      window.removeEventListener("mousemove", move);
      window.removeEventListener("mouseup", up);
    };
  }, [onWidth, min, max]);

  return (
    <div className="d-flex" style={{ width, minWidth: width, height: "100%" }}>
      <div
        onMouseDown={() => {
          dragging.current = true;
          document.body.style.userSelect = "none";
          document.body.style.cursor = "col-resize";
        }}
        title="Drag to resize"
        style={{ width: 6, cursor: "col-resize", flexShrink: 0 }}
        className="bg-body-secondary border-start"
      />
      <div className="flex-grow-1" style={{ minWidth: 0, height: "100%" }}>
        {children}
      </div>
    </div>
  );
}

ModuleRegistry.registerModules([AllCommunityModule]);

// ── Cell renderers ─────────────────────────────────────────────────────────

// Single-line JSON for expanded nested values; tooltip capped so a huge
// cell can't produce a megabyte hover.
function NestedJson({ value }: { value: CellValue }) {
  const str = JSON.stringify(value) ?? "";
  return (
    <span
      className="font-monospace small"
      title={str.length > 1000 ? `${str.slice(0, 1000)}…` : str}
      style={{
        overflow: "hidden",
        textOverflow: "ellipsis",
        whiteSpace: "nowrap",
        display: "block",
      }}
    >
      {str}
    </span>
  );
}

function CellRenderer({
  value,
  expandNested,
}: {
  value: CellValue;
  expandNested: boolean;
}) {
  if (value === null || value === undefined) {
    return (
      <span className="fst-italic" style={{ opacity: 0.55 }}>
        null
      </span>
    );
  }
  if (value === "") {
    return (
      <span className="fst-italic" style={{ opacity: 0.55 }}>
        empty
      </span>
    );
  }
  if (typeof value === "object" && !Array.isArray(value)) {
    const obj = value as Record<string, unknown>;
    if (obj.__type === "image") {
      return (
        <span className="badge bg-info text-dark">
          <i className="bi bi-image me-1" />
          image
        </span>
      );
    }
    if (obj.__type === "bytes") {
      return (
        <span className="small" style={{ opacity: 0.7 }}>
          {String(obj.size)} bytes
        </span>
      );
    }
    if (expandNested) return <NestedJson value={value} />;
    return (
      <span
        className="font-monospace small"
        title={JSON.stringify(value)}
        style={{
          opacity: 0.7,
          overflow: "hidden",
          textOverflow: "ellipsis",
          whiteSpace: "nowrap",
          display: "block",
          maxWidth: 200,
        }}
      >
        {"{…}"}
      </span>
    );
  }
  if (Array.isArray(value)) {
    if (expandNested) return <NestedJson value={value} />;
    return (
      <span className="small" style={{ opacity: 0.7 }}>
        [{value.length} items]
      </span>
    );
  }
  const str = String(value);
  return (
    <span
      title={str}
      style={{
        display: "block",
        overflow: "hidden",
        textOverflow: "ellipsis",
        whiteSpace: "nowrap",
      }}
    >
      {str}
    </span>
  );
}

// ── Schema panel ────────────────────────────────────────────────────────────

const TYPE_BADGE: Record<string, string> = {
  str: "bg-primary",
  int: "bg-success",
  float: "bg-success",
  bool: "bg-warning text-dark",
  image: "bg-info text-dark",
  list: "bg-secondary",
  dict: "bg-secondary",
  null: "bg-light text-dark border",
};

function SchemaPanel({
  schema,
  onClose,
  hiddenColumns,
  onToggleColumn,
}: {
  schema: SchemaField[];
  onClose: () => void;
  hiddenColumns: Set<string>;
  onToggleColumn: (name: string, visible: boolean) => void;
}) {
  return (
    <div
      className="d-flex flex-column bg-body"
      style={{ width: "100%", height: "100%", overflowY: "auto" }}
    >
      <div className="p-3 border-bottom d-flex justify-content-between align-items-center">
        <div>
          <h6 className="mb-0 fw-semibold">Schema</h6>
          <span className="small text-body-secondary">
            Tick a field to show its column
          </span>
        </div>
        <button
          className="btn btn-sm btn-close"
          onClick={onClose}
          aria-label="Close schema panel"
        />
      </div>
      <div className="px-3 py-2">
        {schema.map((f) => (
          <div key={f.name} className="mb-3 d-flex align-items-start">
            <input
              type="checkbox"
              className="form-check-input mt-1 me-2 flex-shrink-0"
              checked={!hiddenColumns.has(f.name)}
              onChange={(e) => onToggleColumn(f.name, e.target.checked)}
              title={hiddenColumns.has(f.name) ? "Show column" : "Hide column"}
            />
            <div className="flex-grow-1" style={{ minWidth: 0 }}>
              <div className="d-flex justify-content-between align-items-center mb-1">
                <span className="fw-semibold small me-2">{f.name}</span>
                <span
                  className={`badge small flex-shrink-0 ${TYPE_BADGE[f.type] ?? "bg-secondary"}`}
                >
                  {f.type}
                </span>
              </div>
              <div className="small text-body-secondary">
                {f.null_count > 0 && (
                  <span className="me-2">
                    {f.null_count} null (
                    {Math.round((f.null_count / f.total) * 100)}%)
                  </span>
                )}
                {f.unique_count !== undefined && (
                  <span className="me-2">{f.unique_count} unique</span>
                )}
                {f.avg_length !== undefined && (
                  <span>avg {f.avg_length} chars</span>
                )}
                {f.mean !== undefined && (
                  <span>
                    {f.min}–{f.max} (mean {f.mean})
                  </span>
                )}
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

// ── Record detail panel ─────────────────────────────────────────────────────

function RecordDetailPanel({
  sessionId,
  idx,
  onClose,
  onPrev,
  onNext,
  hasPrev,
  hasNext,
}: {
  sessionId: string;
  idx: number;
  onClose: () => void;
  onPrev: () => void;
  onNext: () => void;
  hasPrev: boolean;
  hasNext: boolean;
}) {
  // Loaded detail is keyed by (sessionId, idx) so it (and the loading flag)
  // can be derived instead of set synchronously in the effect.
  const [loaded, setLoaded] = useState<{
    key: string;
    detail: ExploreRecordDetail | null;
  } | null>(null);

  useEffect(() => {
    let cancelled = false;
    const key = `${sessionId}:${idx}`;
    fetchExplorerRecord(sessionId, idx).then((d) => {
      if (!cancelled) setLoaded({ key, detail: d });
    });
    return () => {
      cancelled = true;
    };
  }, [sessionId, idx]);

  const currentKey = `${sessionId}:${idx}`;
  const detail = loaded && loaded.key === currentKey ? loaded.detail : null;
  const loading = loaded === null || loaded.key !== currentKey;

  return (
    <div
      className="d-flex flex-column bg-body"
      style={{ width: "100%", height: "100%", overflowY: "auto" }}
    >
      <div className="p-3 border-bottom d-flex justify-content-between align-items-center">
        <h6 className="mb-0 fw-semibold">Record #{idx}</h6>
        <button className="btn-close" onClick={onClose} aria-label="Close" />
      </div>

      {loading && <div className="p-3 text-body-secondary small">Loading…</div>}

      {detail && (
        <div className="flex-grow-1" style={{ overflowY: "auto" }}>
          {/* Images */}
          {detail.images.length > 0 && (
            <div className="p-3 border-bottom">
              <div className="text-uppercase small text-body-secondary fw-semibold mb-2">
                Images
              </div>
              {detail.images.map((img) => (
                <div key={img.field} className="mb-2">
                  <div className="small text-body-secondary mb-1">
                    {img.field}
                  </div>
                  <img
                    src={img.data_url}
                    alt={img.field}
                    className="img-fluid rounded"
                    style={{ maxHeight: 240 }}
                  />
                </div>
              ))}
            </div>
          )}

          {/* Fields */}
          <div className="p-3">
            <div className="text-uppercase small text-body-secondary fw-semibold mb-2">
              Fields
            </div>
            <dl className="mb-0">
              {Object.entries(detail.record).map(([key, val]) => (
                <div key={key} className="mb-2">
                  <dt className="small fw-semibold text-body-secondary">
                    {key}
                  </dt>
                  <dd className="mb-0 small">
                    <FieldValue value={val} />
                  </dd>
                </div>
              ))}
            </dl>
          </div>
        </div>
      )}

      {/* Navigation */}
      <div className="p-3 border-top d-flex justify-content-between">
        <button
          className="btn btn-sm btn-outline-secondary"
          onClick={onPrev}
          disabled={!hasPrev}
        >
          <i className="bi bi-chevron-left me-1" />
          Prev
        </button>
        <button
          className="btn btn-sm btn-outline-secondary"
          onClick={onNext}
          disabled={!hasNext}
        >
          Next
          <i className="bi bi-chevron-right ms-1" />
        </button>
      </div>
    </div>
  );
}

function FieldValue({ value }: { value: CellValue }) {
  if (value === null || value === undefined) {
    return <span className="text-body-secondary fst-italic">null</span>;
  }
  if (value === "") {
    return <span className="text-body-secondary fst-italic">empty</span>;
  }
  if (typeof value === "object" && !Array.isArray(value)) {
    const obj = value as Record<string, unknown>;
    if (obj.__type === "image") {
      return (
        <span className="badge bg-info text-dark">
          <i className="bi bi-image me-1" />
          image (see above)
        </span>
      );
    }
    return (
      <pre
        className="small bg-body-secondary rounded p-2 mb-0"
        style={{ maxHeight: 200, overflowY: "auto", whiteSpace: "pre-wrap" }}
      >
        {JSON.stringify(value, null, 2)}
      </pre>
    );
  }
  if (Array.isArray(value)) {
    return (
      <pre
        className="small bg-body-secondary rounded p-2 mb-0"
        style={{ maxHeight: 200, overflowY: "auto", whiteSpace: "pre-wrap" }}
      >
        {JSON.stringify(value, null, 2)}
      </pre>
    );
  }
  const str = String(value);
  if (str.length > 300) {
    return (
      <details>
        <summary className="small text-body-secondary">
          {str.slice(0, 80)}…
        </summary>
        <p className="mb-0 small mt-1" style={{ whiteSpace: "pre-wrap" }}>
          {str}
        </p>
      </details>
    );
  }
  return <span style={{ whiteSpace: "pre-wrap" }}>{str}</span>;
}

// ── Scanners panel ──────────────────────────────────────────────────────────

const SEVERITY_BADGE: Record<string, string> = {
  high: "bg-danger",
  medium: "bg-warning text-dark",
  low: "bg-secondary",
};

function ScannersPanel({
  sessionId,
  onClose,
  onJumpToRow,
}: {
  sessionId: string;
  onClose: () => void;
  onJumpToRow: (idx: number) => void;
}) {
  const [scanners, setScanners] = useState<ScannerInfo[]>([]);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [model, setModel] = useState("");
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [findings, setFindings] = useState<ExploreFinding[] | null>(null);

  useEffect(() => {
    fetchScanners().then((list) => {
      setScanners(list);
      // Default: select all static scanners.
      setSelected(
        new Set(list.filter((s) => s.kind === "static").map((s) => s.name)),
      );
    });
  }, []);

  const toggle = (name: string) =>
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(name)) next.delete(name);
      else next.add(name);
      return next;
    });

  const run = async () => {
    setRunning(true);
    setError(null);
    try {
      const result = await runExplorerScan(
        sessionId,
        [...selected],
        model.trim() || undefined,
      );
      setFindings(result.findings);
    } catch (e) {
      setError(String(e instanceof Error ? e.message : e));
    } finally {
      setRunning(false);
    }
  };

  const bySeverity = { high: 0, medium: 0, low: 0 };
  for (const f of findings ?? [])
    bySeverity[f.severity] = (bySeverity[f.severity] ?? 0) + 1;

  const needsModel = [...selected].some(
    (n) => scanners.find((s) => s.name === n)?.kind === "llm",
  );

  return (
    <div
      className="d-flex flex-column bg-body"
      style={{ width: "100%", height: "100%", overflowY: "auto" }}
    >
      <div className="p-3 border-bottom d-flex justify-content-between align-items-center">
        <h6 className="mb-0 fw-semibold">Scanners</h6>
        <button
          className="btn btn-sm btn-close"
          onClick={onClose}
          aria-label="Close scanners panel"
        />
      </div>

      <div className="px-3 py-2 border-bottom">
        {scanners.map((s) => (
          <div key={s.name} className="form-check mb-1" title={s.description}>
            <input
              type="checkbox"
              className="form-check-input"
              id={`scanner-${s.name}`}
              checked={selected.has(s.name)}
              onChange={() => toggle(s.name)}
            />
            <label
              className="form-check-label small"
              htmlFor={`scanner-${s.name}`}
            >
              {s.name}
              {s.kind === "llm" && (
                <span className="badge bg-info text-dark ms-1">LLM</span>
              )}
            </label>
          </div>
        ))}

        {needsModel && (
          <input
            type="text"
            className="form-control form-control-sm mt-2"
            placeholder="model (e.g. openai/gpt-4o-mini)"
            value={model}
            onChange={(e) => setModel(e.target.value)}
          />
        )}

        <button
          className="btn btn-sm btn-primary w-100 mt-2"
          onClick={run}
          disabled={running || selected.size === 0}
        >
          {running ? (
            <>
              <span className="spinner-border spinner-border-sm me-1" />
              Running…
            </>
          ) : (
            <>
              <i className="bi bi-play-fill me-1" />
              Run {selected.size} scanner{selected.size === 1 ? "" : "s"}
            </>
          )}
        </button>
      </div>

      {error && (
        <div className="alert alert-danger m-2 small mb-0">{error}</div>
      )}

      {findings !== null && !error && (
        <div className="flex-grow-1" style={{ overflowY: "auto" }}>
          <div className="px-3 py-2 border-bottom small text-body-secondary d-flex gap-2 align-items-center">
            <span className="fw-semibold text-body">
              {findings.length} finding{findings.length === 1 ? "" : "s"}
            </span>
            {bySeverity.high > 0 && (
              <span className="badge bg-danger">{bySeverity.high} high</span>
            )}
            {bySeverity.medium > 0 && (
              <span className="badge bg-warning text-dark">
                {bySeverity.medium} medium
              </span>
            )}
            {bySeverity.low > 0 && (
              <span className="badge bg-secondary">{bySeverity.low} low</span>
            )}
          </div>
          {findings.length === 0 ? (
            <div className="p-3 text-body-secondary small">
              No issues found.
            </div>
          ) : (
            <ul className="list-group list-group-flush">
              {findings.map((f) => (
                <li key={f.id} className="list-group-item py-2">
                  <button
                    className="btn btn-link btn-sm p-0 text-start w-100"
                    onClick={() => onJumpToRow(f.sample_index)}
                    title="Jump to this record"
                  >
                    <div className="d-flex justify-content-between align-items-center mb-1">
                      <span className="fw-semibold small text-body">
                        {f.scanner}
                      </span>
                      <span
                        className={`badge small ${SEVERITY_BADGE[f.severity] ?? "bg-secondary"}`}
                      >
                        {f.severity}
                      </span>
                    </div>
                    <div
                      className="small text-body-secondary"
                      style={{ whiteSpace: "normal" }}
                    >
                      <span className="text-body">#{f.sample_index}</span>{" "}
                      {f.explanation}
                    </div>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}

// ── Main explorer view ──────────────────────────────────────────────────────

const PAGE_SIZE = 200;

export function ExplorerView() {
  const { sessionId } = useParams<{ sessionId: string }>();
  const navigate = useNavigate();
  const explorerSession = useStore((s) => s.explorerSession);
  const explorerSchema = useStore((s) => s.explorerSchema);
  const clearSession = useStore((s) => s.clearExplorerSession);

  const [rows, setRows] = useState<ExploreRow[]>([]);
  const [total, setTotal] = useState(0);
  const [loadingRows, setLoadingRows] = useState(false);
  const [rowError, setRowError] = useState<string | null>(null);
  const [showSchema, setShowSchema] = useState(false);
  const [showScanners, setShowScanners] = useState(false);
  const [selectedIdx, setSelectedIdx] = useState<number | null>(null);
  const [offset, setOffset] = useState(0);
  const [localSchema, setLocalSchema] = useState<SchemaInfo | null>(null);
  const [hiddenColumns, setHiddenColumns] = useState<Set<string>>(new Set());
  const [schemaWidth, setSchemaWidth] = useState(360);
  const [recordWidth, setRecordWidth] = useState(440);
  const [scannersWidth, setScannersWidth] = useState(360);
  const [expandNested, setExpandNested] = useState(false);
  // Read by cell renderers via ref so colDefs stay referentially stable
  // (invalidating them on toggle would reset manual column resizes).
  const expandNestedRef = useRef(expandNested);
  const gridApi = useRef<GridApi | null>(null);

  const sid = sessionId ?? explorerSession?.session_id ?? null;

  // When navigating directly to a session URL (page reload), fetch schema from
  // the API since the Zustand store is empty.
  useEffect(() => {
    if (!sid) {
      navigate("/", { replace: true });
      return;
    }
    if (!explorerSchema && !explorerSession) {
      fetchExplorerSchema(sid)
        .then(setLocalSchema)
        .catch(() => setLocalSchema(null));
    }
  }, [sid, explorerSchema, explorerSession, navigate]);

  // Load first page of records. Rows accumulate across this effect and the
  // paginated loadMore callback below, so (unlike the sibling detail-fetch
  // effects in this file) loading/error can't be derived from a single keyed
  // result — they're reset here deliberately when the session changes.
  useEffect(() => {
    if (!sid) return;
    setLoadingRows(true);
    setRowError(null);
    fetchExplorerRecords(sid, 0, PAGE_SIZE)
      .then((page) => {
        setRows(page.rows);
        setTotal(page.total);
        setOffset(PAGE_SIZE);
        setLoadingRows(false);
      })
      .catch((e) => {
        setRowError(String(e));
        setLoadingRows(false);
      });
  }, [sid]);

  const loadMore = useCallback(() => {
    if (!sid || loadingRows || offset >= total) return;
    setLoadingRows(true);
    fetchExplorerRecords(sid, offset, PAGE_SIZE)
      .then((page) => {
        setRows((prev) => [...prev, ...page.rows]);
        setOffset((prev) => prev + PAGE_SIZE);
        setLoadingRows(false);
      })
      .catch(() => setLoadingRows(false));
  }, [sid, loadingRows, offset, total]);

  const schema = (explorerSchema ?? localSchema)?.schema ?? [];
  const session = explorerSession;

  // Derive column names: prefer schema fields, fall back to session.columns
  const columnNames: string[] =
    schema.length > 0
      ? schema.filter((f) => !f.name.startsWith("__")).map((f) => f.name)
      : (session?.columns ?? []).filter((c) => !c.startsWith("__"));

  const columnKey = columnNames.join("\u0000");

  // Sample of the first page of rows, used to estimate content-based column
  // widths. Keyed on (session, rows-arrived) rather than the rows array so
  // loadMore appends don't produce a new sample — colDefs would change
  // identity and reset the user's manual column resizes.
  const hasRows = rows.length > 0;
  const sampleRows: ExploreRow[] = useMemo(
    () => rows.slice(0, 50),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [sid, hasRows],
  );

  // Size each column at least to fit its header text, widened toward the
  // content's typical width (90th percentile of the sampled rows' display
  // length) up to a 600px cap, so text-heavy datasets get readable columns
  // while wide datasets still scroll horizontally. Memoised so user resizes
  // and visibility toggles (applied imperatively) aren't reset on re-render.
  const colDefs: ColDef<ExploreRow>[] = useMemo(() => {
    const headerWidth = (name: string) =>
      Math.min(560, Math.max(120, name.length * 8.5 + 56));

    // Approximate on-screen length of a cell's collapsed rendering.
    const displayLength = (v: CellValue): number => {
      if (v === null || v === undefined) return 4;
      if (typeof v === "string") return v.length;
      if (Array.isArray(v)) return 10; // "[x items]"
      if (typeof v === "object") return 8; // "{…}" / image / bytes badge
      return String(v).length;
    };

    const contentWidth = (name: string): number => {
      const lengths = sampleRows
        .map((r) => displayLength(r[name] as CellValue))
        .sort((a, b) => a - b);
      if (lengths.length === 0) return 0;
      const p90 =
        lengths[Math.min(lengths.length - 1, Math.floor(lengths.length * 0.9))];
      return p90 * 7.5 + 40; // ~avg char width in the cell font + padding
    };

    return [
      {
        headerName: "#",
        field: "__index",
        width: 72,
        pinned: "left" as const,
        sort: "asc" as const,
        sortable: true,
      },
      ...columnNames.map((name) => ({
        headerName: name,
        field: name as keyof ExploreRow & string,
        width: Math.min(600, Math.max(headerWidth(name), contentWidth(name))),
        minWidth: 80,
        sortable: true,
        filter: true,
        resizable: true,
        valueFormatter: () => "",
        cellRenderer: (params: ICellRendererParams<ExploreRow>) => (
          <CellRenderer
            value={params.value as CellValue}
            expandNested={expandNestedRef.current}
          />
        ),
      })),
    ];
    // columnKey captures the (ordered) column set; schema identity is stable.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [columnKey, sampleRows]);

  const toggleExpandNested = useCallback((on: boolean) => {
    expandNestedRef.current = on;
    setExpandNested(on);
    // Renderers read the ref, so force re-render of already-drawn cells.
    gridApi.current?.refreshCells({ force: true });
  }, []);

  const toggleColumn = useCallback((name: string, visible: boolean) => {
    gridApi.current?.setColumnsVisible([name], visible);
    setHiddenColumns((prev) => {
      const next = new Set(prev);
      if (visible) next.delete(name);
      else next.add(name);
      return next;
    });
  }, []);

  const jumpToRow = useCallback((idx: number) => {
    setSelectedIdx(idx);
    gridApi.current?.ensureIndexVisible(idx, "middle");
  }, []);

  const handleClose = () => {
    clearSession();
    navigate("/");
  };

  if (!sid) return null;

  return (
    <div className="d-flex flex-column vh-100">
      {/* Header */}
      <nav className="navbar bg-body-tertiary border-bottom px-3 flex-shrink-0">
        <button
          className="btn btn-sm btn-outline-secondary me-2"
          onClick={handleClose}
          title="Back to home"
        >
          <i className="bi bi-arrow-left" />
        </button>
        <span className="navbar-brand fw-bold me-2">inspect-dataset</span>
        {session && (
          <span className="navbar-text me-auto">
            <span className="fw-semibold">{session.source}</span>
            {session.source_type === "hf" && (
              <>
                <a
                  href={`https://huggingface.co/datasets/${session.source}`}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="ms-2"
                  title="View on HuggingFace"
                >
                  <i className="bi bi-box-arrow-up-right" />
                </a>
                <span className="text-body-secondary ms-1">
                  [{session.split}]
                </span>
              </>
            )}
            <span className="text-body-secondary ms-2">
              {total.toLocaleString()} records
            </span>
          </span>
        )}
        <div className="d-flex gap-2 align-items-center">
          <div
            className="form-check form-switch mb-0 me-1 small"
            title="Show list/object contents as JSON in cells"
          >
            <input
              className="form-check-input"
              type="checkbox"
              role="switch"
              id="expand-nested-switch"
              checked={expandNested}
              onChange={(e) => toggleExpandNested(e.target.checked)}
            />
            <label className="form-check-label" htmlFor="expand-nested-switch">
              Expand nested
            </label>
          </div>
          <button
            className={`btn btn-sm ${showSchema ? "btn-secondary" : "btn-outline-secondary"}`}
            onClick={() => setShowSchema((v) => !v)}
            title="Toggle schema panel"
          >
            <i className="bi bi-table me-1" />
            Schema
          </button>
          <button
            className={`btn btn-sm ${showScanners ? "btn-secondary" : "btn-outline-secondary"}`}
            onClick={() => setShowScanners((v) => !v)}
            title="Toggle scanners panel"
          >
            <i className="bi bi-search me-1" />
            Scanners
          </button>
        </div>
      </nav>

      {/* Error */}
      {rowError && (
        <div className="alert alert-danger m-2 mb-0">{rowError}</div>
      )}

      {/* Main content */}
      <div className="d-flex flex-grow-1" style={{ minHeight: 0 }}>
        {/* Table */}
        <div
          className="flex-grow-1 d-flex flex-column"
          style={{ minHeight: 0 }}
        >
          {loadingRows && rows.length === 0 ? (
            <div className="d-flex align-items-center justify-content-center flex-grow-1 text-body-secondary">
              <div className="spinner-border me-2" />
              Loading records…
            </div>
          ) : (
            <>
              <div style={{ flex: 1, minHeight: 0 }}>
                <AgGridReact<ExploreRow>
                  theme={gridTheme}
                  rowData={rows}
                  columnDefs={colDefs}
                  onGridReady={(p) => {
                    gridApi.current = p.api;
                  }}
                  onRowClicked={(e) => {
                    const idx = e.data?.__index;
                    if (idx !== undefined) setSelectedIdx(idx);
                  }}
                  rowSelection={{
                    mode: "singleRow",
                    enableClickSelection: true,
                  }}
                  getRowStyle={(p) =>
                    p.data?.__index === selectedIdx
                      ? {
                          background: "var(--bs-primary-bg-subtle)",
                          color: "var(--bs-primary-text-emphasis)",
                        }
                      : undefined
                  }
                />
              </div>
              {/* Load more footer */}
              {offset < total && (
                <div className="border-top px-3 py-2 d-flex align-items-center gap-3 bg-body-tertiary small">
                  <span className="text-body-secondary">
                    Showing {rows.length.toLocaleString()} of{" "}
                    {total.toLocaleString()} records
                  </span>
                  <button
                    className="btn btn-sm btn-outline-secondary"
                    onClick={loadMore}
                    disabled={loadingRows}
                  >
                    {loadingRows ? (
                      <span className="spinner-border spinner-border-sm me-1" />
                    ) : (
                      <i className="bi bi-plus-circle me-1" />
                    )}
                    Load {Math.min(PAGE_SIZE, total - offset).toLocaleString()}{" "}
                    more
                  </button>
                </div>
              )}
            </>
          )}
        </div>

        {/* Schema panel */}
        {showSchema && schema.length > 0 && (
          <ResizablePanel width={schemaWidth} onWidth={setSchemaWidth}>
            <SchemaPanel
              schema={schema}
              onClose={() => setShowSchema(false)}
              hiddenColumns={hiddenColumns}
              onToggleColumn={toggleColumn}
            />
          </ResizablePanel>
        )}

        {/* Scanners panel */}
        {showScanners && (
          <ResizablePanel width={scannersWidth} onWidth={setScannersWidth}>
            <ScannersPanel
              sessionId={sid}
              onClose={() => setShowScanners(false)}
              onJumpToRow={jumpToRow}
            />
          </ResizablePanel>
        )}

        {/* Record detail panel */}
        {selectedIdx !== null && sid && (
          <ResizablePanel width={recordWidth} onWidth={setRecordWidth}>
            <RecordDetailPanel
              sessionId={sid}
              idx={selectedIdx}
              onClose={() => setSelectedIdx(null)}
              onPrev={() =>
                setSelectedIdx((i) => (i !== null && i > 0 ? i - 1 : i))
              }
              onNext={() =>
                setSelectedIdx((i) => (i !== null && i < total - 1 ? i + 1 : i))
              }
              hasPrev={selectedIdx > 0}
              hasNext={selectedIdx < total - 1}
            />
          </ResizablePanel>
        )}
      </div>
    </div>
  );
}
