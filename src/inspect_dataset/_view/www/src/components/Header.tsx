import { Link, NavLink, useNavigate, useParams } from "react-router-dom";
import { useStore } from "../store";

export function Header() {
  const summary = useStore((s) => s.summary);
  const findings = useStore((s) => s.findings);
  const datasets = useStore((s) => s.datasets);
  const { slug } = useParams<{ slug: string }>();
  const navigate = useNavigate();

  const confirmed = findings.filter(
    (f) => f.triage_status === "confirmed",
  ).length;
  const dismissed = findings.filter(
    (f) => f.triage_status === "dismissed",
  ).length;

  return (
    <nav className="navbar navbar-expand bg-body-tertiary border-bottom px-3">
      <Link
        to="/"
        className="navbar-brand fw-bold text-decoration-none"
        title="Back to home"
      >
        inspect-dataset
      </Link>

      {/* Dataset name or switcher */}
      {datasets.length > 1 ? (
        <select
          className="form-select form-select-sm me-auto"
          style={{ width: "auto", maxWidth: 300 }}
          value={slug ?? ""}
          onChange={(e) => navigate(`/${e.target.value}/findings`)}
          aria-label="Switch dataset"
        >
          {datasets.map((ds) => (
            <option key={ds.slug} value={ds.slug}>
              {ds.dataset_name}
              {ds.split ? ` [${ds.split}]` : ""}
            </option>
          ))}
        </select>
      ) : (
        summary && (
          <span className="navbar-text me-auto">
            <span className="fw-semibold">{summary.dataset_name}</span>
            {summary.split && (
              <span className="text-body-secondary ms-1">
                [{summary.split}]
              </span>
            )}
            <span className="text-body-secondary ms-2">
              {summary.total_samples.toLocaleString()} samples
            </span>
          </span>
        )
      )}

      <ul className="nav nav-pills me-3">
        <li className="nav-item">
          <Link to="/" className="nav-link" title="Back to all datasets">
            <i className="bi bi-house me-1" />
            Home
          </Link>
        </li>
        <li className="nav-item">
          <NavLink
            to={`/${slug}/findings`}
            className={({ isActive }) => `nav-link${isActive ? " active" : ""}`}
          >
            Findings
            <span className="badge bg-secondary ms-1">{findings.length}</span>
          </NavLink>
        </li>
        <li className="nav-item">
          <NavLink
            to={`/${slug}/samples`}
            className={({ isActive }) => `nav-link${isActive ? " active" : ""}`}
          >
            Samples
          </NavLink>
        </li>
      </ul>

      <span className="navbar-text small text-body-secondary">
        {confirmed} confirmed · {dismissed} dismissed
      </span>
    </nav>
  );
}
