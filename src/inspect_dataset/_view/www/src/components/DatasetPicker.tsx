import { Link } from "react-router-dom";
import type { DatasetInfo } from "../types";

const SEVERITY_COLORS: Record<string, string> = {
  high: "bg-danger",
  medium: "bg-warning text-dark",
  low: "bg-secondary",
};

function SeverityPills({ bySeverity }: { bySeverity: Record<string, number> }) {
  const order = ["high", "medium", "low"];
  const entries = order
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

export function DatasetPicker({ datasets }: { datasets: DatasetInfo[] }) {
  return (
    <div className="d-flex flex-column vh-100">
      <nav className="navbar bg-body-tertiary border-bottom px-3">
        <span className="navbar-brand fw-bold">inspect-dataset</span>
      </nav>

      <div className="container-fluid p-4" style={{ maxWidth: 900 }}>
        <h5 className="mb-4 text-body-secondary">
          Select a dataset to explore
        </h5>
        <div className="row g-3">
          {datasets.map((ds) => (
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
      </div>
    </div>
  );
}
