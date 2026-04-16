import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { AgGridReact } from "ag-grid-react";
import {
  AllCommunityModule,
  ModuleRegistry,
  themeQuartz,
} from "ag-grid-community";
import type {
  ColDef,
  GridApi,
  ICellRendererParams,
} from "ag-grid-community";
import { useStore } from "../store";
import {
  fetchExplorerRecord,
  fetchExplorerRecords,
  fetchExplorerSchema,
} from "../api";
import type {
  CellValue,
  ExploreRecordDetail,
  ExploreRow,
  SchemaField,
  SchemaInfo,
} from "../types";

ModuleRegistry.registerModules([AllCommunityModule]);

// ── Cell renderers ─────────────────────────────────────────────────────────

function CellRenderer({ value }: { value: CellValue }) {
  if (value === null || value === undefined) {
    return <span className="fst-italic" style={{ opacity: 0.55 }}>null</span>;
  }
  if (value === "") {
    return <span className="fst-italic" style={{ opacity: 0.55 }}>empty</span>;
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
    return (
      <span className="small" style={{ opacity: 0.7 }}>[{value.length} items]</span>
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
}: {
  schema: SchemaField[];
  onClose: () => void;
}) {
  return (
    <div
      className="border-start d-flex flex-column bg-body"
      style={{ width: 300, minWidth: 300, overflowY: "auto" }}
    >
      <div className="p-3 border-bottom d-flex justify-content-between align-items-center">
        <h6 className="mb-0 fw-semibold">Schema</h6>
        <button
          className="btn btn-sm btn-close"
          onClick={onClose}
          aria-label="Close schema panel"
        />
      </div>
      <div className="px-3 py-2">
        {schema.map((f) => (
          <div key={f.name} className="mb-3">
            <div className="d-flex justify-content-between align-items-center mb-1">
              <span className="fw-semibold small text-truncate me-2">
                {f.name}
              </span>
              <span
                className={`badge small flex-shrink-0 ${TYPE_BADGE[f.type] ?? "bg-secondary"}`}
              >
                {f.type}
              </span>
            </div>
            <div className="small text-body-secondary">
              {f.null_count > 0 && (
                <span className="me-2">
                  {f.null_count} null ({Math.round((f.null_count / f.total) * 100)}%)
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
  const [detail, setDetail] = useState<ExploreRecordDetail | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    setDetail(null);
    setLoading(true);
    fetchExplorerRecord(sessionId, idx).then((d) => {
      setDetail(d);
      setLoading(false);
    });
  }, [sessionId, idx]);

  return (
    <div
      className="border-start d-flex flex-column bg-body"
      style={{ width: 360, minWidth: 360, overflowY: "auto" }}
    >
      <div className="p-3 border-bottom d-flex justify-content-between align-items-center">
        <h6 className="mb-0 fw-semibold">Record #{idx}</h6>
        <button className="btn-close" onClick={onClose} aria-label="Close" />
      </div>

      {loading && (
        <div className="p-3 text-body-secondary small">Loading…</div>
      )}

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
  return (
    <span style={{ whiteSpace: "pre-wrap" }}>{str}</span>
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
  const [selectedIdx, setSelectedIdx] = useState<number | null>(null);
  const [offset, setOffset] = useState(0);
  const [localSchema, setLocalSchema] = useState<SchemaInfo | null>(null);
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

  // Load first page of records
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

  const colDefs: ColDef<ExploreRow>[] = [
    {
      headerName: "#",
      field: "__index",
      width: 65,
      pinned: "left" as const,
      sort: "asc" as const,
      sortable: true,
    },
    ...columnNames.map((name) => {
      const schemaField = schema.find((f) => f.name === name);
      return {
        headerName: name,
        field: name as keyof ExploreRow & string,
        flex: schemaField?.type === "str" ? 2 : 1,
        minWidth: 80,
        sortable: true,
        filter: true,
        valueFormatter: () => "",
        cellRenderer: (params: ICellRendererParams<ExploreRow>) => (
          <CellRenderer value={params.value as CellValue} />
        ),
      };
    }),
  ];

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
        <div className="d-flex gap-2">
          <button
            className={`btn btn-sm ${showSchema ? "btn-secondary" : "btn-outline-secondary"}`}
            onClick={() => setShowSchema((v) => !v)}
            title="Toggle schema panel"
          >
            <i className="bi bi-table me-1" />
            Schema
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
        <div className="flex-grow-1 d-flex flex-column" style={{ minHeight: 0 }}>
          {loadingRows && rows.length === 0 ? (
            <div className="d-flex align-items-center justify-content-center flex-grow-1 text-body-secondary">
              <div className="spinner-border me-2" />
              Loading records…
            </div>
          ) : (
            <>
              <div style={{ flex: 1, minHeight: 0 }}>
                <AgGridReact<ExploreRow>
                  theme={themeQuartz}
                  rowData={rows}
                  columnDefs={colDefs}
                  onGridReady={(p) => {
                    gridApi.current = p.api;
                  }}
                  onRowClicked={(e) => {
                    const idx = e.data?.__index;
                    if (idx !== undefined) setSelectedIdx(idx);
                  }}
                  rowSelection={{ mode: "singleRow", enableClickSelection: true }}
                  getRowStyle={(p) =>
                    p.data?.__index === selectedIdx
                      ? { background: "var(--bs-primary-bg-subtle)" }
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
                    Load {Math.min(PAGE_SIZE, total - offset).toLocaleString()} more
                  </button>
                </div>
              )}
            </>
          )}
        </div>

        {/* Schema panel */}
        {showSchema && schema.length > 0 && (
          <SchemaPanel schema={schema} onClose={() => setShowSchema(false)} />
        )}

        {/* Record detail panel */}
        {selectedIdx !== null && sid && (
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
        )}
      </div>
    </div>
  );
}
