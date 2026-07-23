import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useStore } from "../store";
import {
  fetchCachedDatasetMeta,
  fetchCachedDatasetsBasic,
  fetchDatasets,
  fetchHfSchema,
  fetchInstalledTasks,
} from "../api";
import type {
  CachedDataset,
  DatasetInfo,
  InstalledTask,
  SchemaField,
} from "../types";

// ── Local findings (pre-loaded via `inspect-dataset view <dir>`) ─────────────

const SEVERITY_COLORS: Record<string, string> = {
  high: "bg-danger",
  medium: "bg-warning text-dark",
  low: "bg-secondary",
};

function SeverityPills({ bySeverity }: { bySeverity: Record<string, number> }) {
  const entries = ["high", "medium", "low"]
    .filter((s) => (bySeverity[s] ?? 0) > 0)
    .map((s) => ({ severity: s, count: bySeverity[s] }));

  if (entries.length === 0)
    return <span className="text-body-secondary small">No findings</span>;

  return (
    <span>
      {entries.map(({ severity, count }) => (
        <span
          key={severity}
          className={`badge ${SEVERITY_COLORS[severity] ?? "bg-secondary"} me-1`}
        >
          {count} {severity}
        </span>
      ))}
    </span>
  );
}

function LocalFindingsSection({ findings }: { findings: DatasetInfo[] }) {
  return (
    <div className="mb-4">
      <h1 className="h4 mb-1">Local findings</h1>
      <p className="text-body-secondary mb-3">
        Scan results loaded from disk. Select one to review and triage its
        findings.
      </p>
      <div className="row g-3">
        {findings.map((ds) => (
          <div className="col-md-4" key={ds.slug}>
            <Link
              to={`/${ds.slug}/findings`}
              className="card text-decoration-none h-100 text-body"
              style={{ cursor: "pointer" }}
            >
              <div className="card-body">
                <h6 className="card-title fw-semibold mb-1">
                  {ds.dataset_name}
                </h6>
                {ds.split && (
                  <div className="text-body-secondary small mb-2">
                    [{ds.split}]
                  </div>
                )}
                <div className="small mb-2 text-body-secondary">
                  {ds.total_samples.toLocaleString()} samples ·{" "}
                  {ds.total_findings} findings
                </div>
                <SeverityPills bySeverity={ds.by_severity} />
              </div>
            </Link>
          </div>
        ))}
      </div>
      <hr className="my-4" />
    </div>
  );
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  if (bytes < 1024 * 1024 * 1024)
    return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
  return `${(bytes / 1024 / 1024 / 1024).toFixed(2)} GB`;
}

// ── Manual entry form ───────────────────────────────────────────────────────

function ManualEntryForm({
  onLoad,
}: {
  onLoad: (
    source: string,
    sourceType: "hf" | "inspect_task",
    split: string,
    limit?: number,
    config?: string,
  ) => void;
}) {
  const [source, setSource] = useState("");
  const [sourceType, setSourceType] = useState<"hf" | "inspect_task">("hf");
  const [split, setSplit] = useState("train");
  const [limit, setLimit] = useState("");
  const [config, setConfig] = useState("");

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!source.trim()) return;
    onLoad(
      source.trim(),
      sourceType,
      split || "train",
      limit ? parseInt(limit, 10) : undefined,
      config.trim() || undefined,
    );
  };

  return (
    <form onSubmit={handleSubmit}>
      <div className="row g-2">
        <div className="col-12">
          <label className="form-label fw-semibold small">Dataset / Task</label>
          <input
            type="text"
            className="form-control"
            placeholder={
              sourceType === "hf"
                ? "e.g. cais/hle or flaviagiammarino/vqa-rad"
                : "e.g. inspect_evals/gpqa_diamond"
            }
            value={source}
            onChange={(e) => setSource(e.target.value)}
            autoFocus
          />
        </div>

        <div className="col-sm-4">
          <label className="form-label fw-semibold small">Source type</label>
          <select
            className="form-select form-select-sm"
            value={sourceType}
            onChange={(e) =>
              setSourceType(e.target.value as "hf" | "inspect_task")
            }
          >
            <option value="hf">HuggingFace dataset</option>
            <option value="inspect_task">inspect_ai task</option>
          </select>
        </div>

        {sourceType === "hf" && (
          <div className="col-sm-4">
            <label className="form-label fw-semibold small">Split</label>
            <input
              type="text"
              className="form-control form-control-sm"
              placeholder="train"
              value={split}
              onChange={(e) => setSplit(e.target.value)}
            />
          </div>
        )}

        {sourceType === "hf" && (
          <div className="col-sm-4">
            <label className="form-label fw-semibold small">
              Config{" "}
              <span className="text-body-secondary fw-normal">(optional)</span>
            </label>
            <input
              type="text"
              className="form-control form-control-sm"
              placeholder="required for multi-config datasets"
              value={config}
              onChange={(e) => setConfig(e.target.value)}
            />
          </div>
        )}

        <div className="col-sm-4">
          <label className="form-label fw-semibold small">
            Limit{" "}
            <span className="text-body-secondary fw-normal">(optional)</span>
          </label>
          <input
            type="number"
            className="form-control form-control-sm"
            placeholder="all"
            min={1}
            value={limit}
            onChange={(e) => setLimit(e.target.value)}
          />
        </div>

        <div className="col-12">
          <button
            type="submit"
            className="btn btn-primary"
            disabled={!source.trim()}
          >
            <i className="bi bi-box-arrow-in-right me-1" />
            Load dataset
          </button>
        </div>
      </div>
    </form>
  );
}

// ── Schema preview panel ───────────────────────────────────────────────────

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

function SchemaPreview({
  repoId,
  onClose,
  onOpen,
  split,
  config,
}: {
  repoId: string;
  split: string;
  config?: string;
  onClose: () => void;
  onOpen: () => void;
}) {
  // Loaded schema is keyed by (repoId, config) so it (and the loading flag)
  // can be derived instead of set synchronously in the effect.
  const [loaded, setLoaded] = useState<{
    key: string;
    schema: SchemaField[] | null;
  } | null>(null);

  useEffect(() => {
    let cancelled = false;
    const key = `${repoId}:${config ?? ""}`;
    fetchHfSchema(repoId, config).then((info) => {
      if (!cancelled) setLoaded({ key, schema: info?.schema ?? null });
    });
    return () => {
      cancelled = true;
    };
  }, [repoId, config]);

  const currentKey = `${repoId}:${config ?? ""}`;
  const schema = loaded && loaded.key === currentKey ? loaded.schema : null;
  const loading = loaded === null || loaded.key !== currentKey;

  return (
    <div
      className="card border shadow"
      style={{ minWidth: 260, maxWidth: 320 }}
    >
      <div className="card-header d-flex justify-content-between align-items-center py-2">
        <span className="small fw-semibold text-truncate me-2" title={repoId}>
          {repoId}
        </span>
        <button className="btn-close btn-sm" onClick={onClose} />
      </div>
      <div
        className="card-body py-2 px-3"
        style={{ maxHeight: 280, overflowY: "auto" }}
      >
        {loading && (
          <div className="text-center py-2 text-body-secondary small">
            <span className="spinner-border spinner-border-sm me-1" />
            Loading schema…
          </div>
        )}
        {!loading && schema === null && (
          <div className="text-body-secondary small py-1">
            Schema not available from HF API.
          </div>
        )}
        {!loading && schema && (
          <dl className="mb-0">
            {schema.map((f) => (
              <div
                key={f.name}
                className="d-flex justify-content-between align-items-center mb-1"
              >
                <dt className="small mb-0 fw-normal text-truncate me-2">
                  {f.name}
                </dt>
                <dd className="mb-0 flex-shrink-0">
                  <span
                    className={`badge small ${TYPE_BADGE[f.type] ?? "bg-secondary"}`}
                  >
                    {f.hf_type ?? f.type}
                  </span>
                </dd>
              </div>
            ))}
          </dl>
        )}
      </div>
      <div className="card-footer py-2">
        <button className="btn btn-primary btn-sm w-100" onClick={onOpen}>
          Open [{split}]
        </button>
      </div>
    </div>
  );
}

// ── Cached HF datasets list ───────────────────────────────────────────────

function CachedDatasetsList({
  datasets,
  loading,
  onSelect,
}: {
  datasets: CachedDataset[];
  loading: boolean;
  onSelect: (ds: CachedDataset, split: string, config?: string) => void;
}) {
  const [search, setSearch] = useState("");
  const [selectedSplits, setSelectedSplits] = useState<Record<string, string>>(
    {},
  );
  const [selectedConfigs, setSelectedConfigs] = useState<
    Record<string, string>
  >({});
  const [previewRepo, setPreviewRepo] = useState<string | null>(null);

  if (loading) {
    return (
      <div className="text-center py-4 text-body-secondary small">
        Scanning cache…
      </div>
    );
  }
  if (datasets.length === 0) {
    return (
      <div className="text-center py-4 text-body-secondary small">
        No cached HuggingFace datasets found.
      </div>
    );
  }

  const filtered = datasets.filter((ds) =>
    ds.repo_id.toLowerCase().includes(search.toLowerCase()),
  );

  return (
    <>
      <input
        type="search"
        className="form-control form-control-sm mb-2"
        placeholder={`Filter ${datasets.length} cached datasets…`}
        value={search}
        onChange={(e) => setSearch(e.target.value)}
      />
      <div className="d-flex gap-3" style={{ alignItems: "flex-start" }}>
        <div
          style={{ maxHeight: 320, overflowY: "auto", flex: 1 }}
          className="border rounded"
        >
          <table className="table table-sm table-hover mb-0 small align-middle">
            <thead className="table-light sticky-top">
              <tr>
                <th>Dataset</th>
                <th style={{ width: 110 }}>Size</th>
                <th style={{ width: 120 }}>Config</th>
                <th style={{ width: 120 }}>Split</th>
                <th style={{ width: 80 }}></th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((ds) => {
                // splits/configs are absent until the per-dataset meta
                // fetch resolves (the basic listing is scan-only).
                const metaPending = ds.splits === undefined;
                const splits = ds.splits ?? [];
                const configs = ds.configs ?? [];
                const split =
                  selectedSplits[ds.repo_id] ?? splits[0] ?? "train";
                // undefined when no config is known → load with no name kwarg
                const config =
                  selectedConfigs[ds.repo_id] ?? configs[0] ?? undefined;
                const isSelected = previewRepo === ds.repo_id;
                return (
                  <tr
                    key={ds.repo_id}
                    className={isSelected ? "table-active" : ""}
                  >
                    <td>
                      <button
                        className="btn btn-link btn-sm p-0 text-start fw-semibold"
                        onClick={() =>
                          setPreviewRepo(isSelected ? null : ds.repo_id)
                        }
                        title="Preview schema"
                      >
                        {ds.repo_id}
                      </button>
                    </td>
                    <td className="text-body-secondary">
                      {formatBytes(ds.size_on_disk)}
                    </td>
                    <td>
                      {metaPending ? (
                        <span
                          className="spinner-border spinner-border-sm text-body-tertiary"
                          role="status"
                          aria-label="Loading configs"
                          style={{ width: 12, height: 12, borderWidth: 1 }}
                        />
                      ) : configs.length > 1 ? (
                        <select
                          className="form-select form-select-sm py-0"
                          style={{ fontSize: "0.8rem" }}
                          value={config}
                          onChange={(e) =>
                            setSelectedConfigs((prev) => ({
                              ...prev,
                              [ds.repo_id]: e.target.value,
                            }))
                          }
                        >
                          {configs.map((c) => (
                            <option key={c} value={c}>
                              {c}
                            </option>
                          ))}
                        </select>
                      ) : (
                        <span className="text-body-secondary">
                          {config ?? "—"}
                        </span>
                      )}
                    </td>
                    <td>
                      {metaPending ? (
                        <span
                          className="spinner-border spinner-border-sm text-body-tertiary"
                          role="status"
                          aria-label="Loading splits"
                          style={{ width: 12, height: 12, borderWidth: 1 }}
                        />
                      ) : splits.length > 1 ? (
                        <select
                          className="form-select form-select-sm py-0"
                          style={{ fontSize: "0.8rem" }}
                          value={split}
                          onChange={(e) =>
                            setSelectedSplits((prev) => ({
                              ...prev,
                              [ds.repo_id]: e.target.value,
                            }))
                          }
                        >
                          {splits.map((s) => (
                            <option key={s} value={s}>
                              {s}
                            </option>
                          ))}
                        </select>
                      ) : (
                        <span className="text-body-secondary">{split}</span>
                      )}
                    </td>
                    <td>
                      <button
                        className="btn btn-sm btn-outline-primary py-0"
                        onClick={() => onSelect(ds, split, config)}
                      >
                        Open
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          {filtered.length === 0 && (
            <div className="text-center py-3 text-body-secondary small">
              No results for "{search}"
            </div>
          )}
        </div>

        {/* Schema preview card */}
        {previewRepo &&
          (() => {
            const ds = filtered.find((d) => d.repo_id === previewRepo);
            const split = ds
              ? (selectedSplits[previewRepo] ?? ds.splits?.[0] ?? "train")
              : "train";
            const config = ds
              ? (selectedConfigs[previewRepo] ?? ds.configs?.[0] ?? undefined)
              : undefined;
            return (
              <SchemaPreview
                key={previewRepo}
                repoId={previewRepo}
                split={split}
                config={config}
                onClose={() => setPreviewRepo(null)}
                onOpen={() => {
                  if (ds) onSelect(ds, split, config);
                }}
              />
            );
          })()}
      </div>
    </>
  );
}

// ── Installed tasks list ────────────────────────────────────────────────────

function InstalledTasksList({
  tasks,
  loading,
  onSelect,
}: {
  tasks: InstalledTask[];
  loading: boolean;
  onSelect: (task: InstalledTask) => void;
}) {
  const [search, setSearch] = useState("");

  if (loading) {
    return (
      <div className="text-center py-4 text-body-secondary small">
        Discovering tasks…
      </div>
    );
  }
  if (tasks.length === 0) {
    return (
      <div className="text-center py-4 text-body-secondary small">
        No inspect_ai tasks found. Install inspect_evals or another package.
      </div>
    );
  }

  // Group by package
  const packages: Record<string, InstalledTask[]> = {};
  for (const t of tasks) {
    const pkg = t.package || "other";
    (packages[pkg] = packages[pkg] ?? []).push(t);
  }

  const filtered = tasks.filter((t) =>
    t.name.toLowerCase().includes(search.toLowerCase()),
  );

  // Re-group filtered results
  const filteredPkgs: Record<string, InstalledTask[]> = {};
  for (const t of filtered) {
    const pkg = t.package || "other";
    (filteredPkgs[pkg] = filteredPkgs[pkg] ?? []).push(t);
  }

  return (
    <>
      <input
        type="search"
        className="form-control form-control-sm mb-2"
        placeholder={`Filter ${tasks.length} tasks…`}
        value={search}
        onChange={(e) => setSearch(e.target.value)}
      />
      <div
        style={{ maxHeight: 320, overflowY: "auto" }}
        className="border rounded"
      >
        {Object.entries(filteredPkgs).map(([pkg, pkgTasks]) => (
          <div key={pkg}>
            <div className="px-3 py-1 bg-body-tertiary border-bottom small fw-semibold text-body-secondary">
              {pkg}
            </div>
            <table className="table table-sm table-hover mb-0 small">
              <tbody>
                {pkgTasks.map((t) => (
                  <tr key={t.name}>
                    <td className="ps-3">{t.name}</td>
                    <td style={{ width: 80 }} className="pe-2">
                      <button
                        className="btn btn-sm btn-outline-primary py-0"
                        onClick={() => onSelect(t)}
                      >
                        Open
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ))}
        {filtered.length === 0 && (
          <div className="text-center py-3 text-body-secondary small">
            No results for "{search}"
          </div>
        )}
      </div>
    </>
  );
}

// ── Main home component ─────────────────────────────────────────────────────

export function ExplorerHome() {
  const [activeTab, setActiveTab] = useState<"cached" | "tasks" | "manual">(
    "cached",
  );
  const [cachedDatasets, setCachedDatasets] = useState<CachedDataset[]>([]);
  const [installedTasks, setInstalledTasks] = useState<InstalledTask[]>([]);
  const [localFindings, setLocalFindings] = useState<DatasetInfo[]>([]);
  const [cachedLoading, setCachedLoading] = useState(true);
  const [tasksLoading, setTasksLoading] = useState(true);

  const startExplorerSession = useStore((s) => s.startExplorerSession);
  const explorerLoading = useStore((s) => s.explorerLoading);
  const explorerError = useStore((s) => s.explorerError);
  const navigate = useNavigate();

  useEffect(() => {
    let cancelled = false;
    fetchDatasets()
      .then((ds) => setLocalFindings(ds))
      .catch(() => setLocalFindings([]));
    // Fast local cache scan first, so the list renders immediately; then
    // fill in splits/configs per dataset (server memoises per snapshot).
    fetchCachedDatasetsBasic().then((ds) => {
      if (cancelled) return;
      setCachedDatasets(ds);
      setCachedLoading(false);

      const queue = ds.map((d) => d.repo_id);
      const fillNext = async (): Promise<void> => {
        for (;;) {
          const repoId = queue.shift();
          if (repoId === undefined || cancelled) return;
          const meta = await fetchCachedDatasetMeta(repoId);
          if (cancelled) return;
          // On failure fall back to defaults rather than a spinner forever.
          const resolved = meta ?? { splits: ["train"], configs: [] };
          setCachedDatasets((prev) =>
            prev.map((d) => (d.repo_id === repoId ? { ...d, ...resolved } : d)),
          );
        }
      };
      const workers = Math.min(6, queue.length);
      for (let i = 0; i < workers; i++) void fillNext();
    });
    fetchInstalledTasks().then((ts) => {
      setInstalledTasks(ts);
      setTasksLoading(false);
    });
    return () => {
      cancelled = true;
    };
  }, []);

  const handleLoad = async (
    source: string,
    sourceType: "hf" | "inspect_task",
    split: string,
    limit?: number,
    config?: string,
  ) => {
    const session = await startExplorerSession(
      source,
      sourceType,
      split,
      limit,
      config,
    );
    if (session) {
      navigate(`/explore/${session.session_id}`);
    }
  };

  return (
    <div
      className="d-flex flex-column align-items-center justify-content-start"
      style={{ minHeight: "100vh", background: "var(--bs-body-bg)" }}
    >
      {/* Navbar */}
      <nav className="navbar w-100 bg-body-tertiary border-bottom px-3">
        <span className="navbar-brand fw-bold">inspect-dataset</span>
        <span className="navbar-text small text-body-secondary">
          Dataset Explorer
        </span>
      </nav>

      <div className="w-100 px-3 py-4" style={{ maxWidth: 860 }}>
        {localFindings.length > 0 && (
          <LocalFindingsSection findings={localFindings} />
        )}

        <h1 className="h4 mb-1">Open a dataset</h1>
        <p className="text-body-secondary mb-4">
          Choose from your local cache, installed inspect tasks, or enter a
          HuggingFace slug directly.
        </p>

        {explorerError && (
          <div className="alert alert-danger mb-3">
            <strong>Error loading dataset:</strong>{" "}
            {explorerError.replace(/^Error:\s*/, "")}
          </div>
        )}

        {explorerLoading && (
          <div className="alert alert-info d-flex align-items-center gap-2 mb-3">
            <div className="spinner-border spinner-border-sm" role="status" />
            <span>Loading dataset…</span>
          </div>
        )}

        {/* Tab nav */}
        <ul className="nav nav-tabs mb-3">
          <li className="nav-item">
            <button
              className={`nav-link${activeTab === "cached" ? " active" : ""}`}
              onClick={() => setActiveTab("cached")}
            >
              <i className="bi bi-hdd me-1" />
              Cached HF
              {!cachedLoading && cachedDatasets.length > 0 && (
                <span className="badge bg-secondary ms-1 small">
                  {cachedDatasets.length}
                </span>
              )}
            </button>
          </li>
          <li className="nav-item">
            <button
              className={`nav-link${activeTab === "tasks" ? " active" : ""}`}
              onClick={() => setActiveTab("tasks")}
            >
              <i className="bi bi-puzzle me-1" />
              Inspect tasks
              {!tasksLoading && installedTasks.length > 0 && (
                <span className="badge bg-secondary ms-1 small">
                  {installedTasks.length}
                </span>
              )}
            </button>
          </li>
          <li className="nav-item">
            <button
              className={`nav-link${activeTab === "manual" ? " active" : ""}`}
              onClick={() => setActiveTab("manual")}
            >
              <i className="bi bi-search me-1" />
              Direct entry
            </button>
          </li>
        </ul>

        {/* Tab content */}
        <div className="card border-0 shadow-sm">
          <div className="card-body">
            {activeTab === "cached" && (
              <CachedDatasetsList
                datasets={cachedDatasets}
                loading={cachedLoading}
                onSelect={(ds, split, config) =>
                  handleLoad(ds.repo_id, "hf", split, undefined, config)
                }
              />
            )}
            {activeTab === "tasks" && (
              <InstalledTasksList
                tasks={installedTasks}
                loading={tasksLoading}
                onSelect={(t) => handleLoad(t.name, "inspect_task", "train")}
              />
            )}
            {activeTab === "manual" && <ManualEntryForm onLoad={handleLoad} />}
          </div>
        </div>
      </div>
    </div>
  );
}
