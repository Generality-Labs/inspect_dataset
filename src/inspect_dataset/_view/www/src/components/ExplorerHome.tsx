import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useStore } from "../store";
import {
  fetchCachedDatasets,
  fetchHfSchema,
  fetchInstalledTasks,
} from "../api";
import type { CachedDataset, InstalledTask, SchemaField } from "../types";

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
  ) => void;
}) {
  const [source, setSource] = useState("");
  const [sourceType, setSourceType] = useState<"hf" | "inspect_task">("hf");
  const [split, setSplit] = useState("train");
  const [limit, setLimit] = useState("");

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!source.trim()) return;
    onLoad(
      source.trim(),
      sourceType,
      split || "train",
      limit ? parseInt(limit, 10) : undefined,
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
}: {
  repoId: string;
  split: string;
  onClose: () => void;
  onOpen: () => void;
}) {
  // Loaded schema is keyed by repoId so it (and the loading flag) can be
  // derived instead of set synchronously in the effect.
  const [loaded, setLoaded] = useState<{
    repoId: string;
    schema: SchemaField[] | null;
  } | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetchHfSchema(repoId).then((info) => {
      if (!cancelled) setLoaded({ repoId, schema: info?.schema ?? null });
    });
    return () => {
      cancelled = true;
    };
  }, [repoId]);

  const schema = loaded && loaded.repoId === repoId ? loaded.schema : null;
  const loading = loaded === null || loaded.repoId !== repoId;

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
  onSelect: (ds: CachedDataset, split: string) => void;
}) {
  const [search, setSearch] = useState("");
  const [selectedSplits, setSelectedSplits] = useState<Record<string, string>>(
    {},
  );
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
                <th style={{ width: 120 }}>Split</th>
                <th style={{ width: 80 }}></th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((ds) => {
                const split =
                  selectedSplits[ds.repo_id] ?? ds.splits[0] ?? "train";
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
                      {ds.splits.length > 1 ? (
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
                          {ds.splits.map((s) => (
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
                        onClick={() => onSelect(ds, split)}
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
              ? (selectedSplits[previewRepo] ?? ds.splits[0] ?? "train")
              : "train";
            return (
              <SchemaPreview
                key={previewRepo}
                repoId={previewRepo}
                split={split}
                onClose={() => setPreviewRepo(null)}
                onOpen={() => {
                  if (ds) onSelect(ds, split);
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
  const [cachedLoading, setCachedLoading] = useState(true);
  const [tasksLoading, setTasksLoading] = useState(true);

  const startExplorerSession = useStore((s) => s.startExplorerSession);
  const explorerLoading = useStore((s) => s.explorerLoading);
  const explorerError = useStore((s) => s.explorerError);
  const navigate = useNavigate();

  useEffect(() => {
    fetchCachedDatasets().then((ds) => {
      setCachedDatasets(ds);
      setCachedLoading(false);
    });
    fetchInstalledTasks().then((ts) => {
      setInstalledTasks(ts);
      setTasksLoading(false);
    });
  }, []);

  const handleLoad = async (
    source: string,
    sourceType: "hf" | "inspect_task",
    split: string,
    limit?: number,
  ) => {
    const session = await startExplorerSession(
      source,
      sourceType,
      split,
      limit,
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
                onSelect={(ds, split) => handleLoad(ds.repo_id, "hf", split)}
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
