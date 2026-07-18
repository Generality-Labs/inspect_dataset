import { useSearchParams } from "react-router-dom";
import clsx from "clsx";
import { useStore, getFilteredFindings } from "../store";
import type { Finding } from "../types";

const SEVERITY_BADGE: Record<string, string> = {
  high: "bg-danger",
  medium: "bg-warning text-dark",
  low: "bg-secondary",
};

const TRIAGE_ICON: Record<string, string> = {
  confirmed: "bi-check-circle-fill text-danger",
  dismissed: "bi-x-circle-fill text-success",
  pending: "",
};

export function FindingsList() {
  const findings = useStore((s) => s.findings);
  const selectedFinding = useStore((s) => s.selectedFinding);
  const setSelectedFinding = useStore((s) => s.setSelectedFinding);
  const [searchParams] = useSearchParams();

  const filtered = getFilteredFindings(
    findings,
    searchParams.get("scanner"),
    searchParams.get("severity"),
    searchParams.get("triage"),
  );

  if (filtered.length === 0) {
    return (
      <div className="d-flex align-items-center justify-content-center flex-grow-1 text-body-secondary">
        No findings match the current filters.
      </div>
    );
  }

  return (
    <div className="flex-grow-1" style={{ overflowY: "auto", minWidth: 0 }}>
      {filtered.map((f) => (
        <FindingRow
          key={f.id}
          finding={f}
          selected={selectedFinding?.id === f.id}
          onClick={() => setSelectedFinding(f)}
        />
      ))}
    </div>
  );
}

function FindingRow({
  finding,
  selected,
  onClick,
}: {
  finding: Finding;
  selected: boolean;
  onClick: () => void;
}) {
  const triageIcon = TRIAGE_ICON[finding.triage_status];

  return (
    <button
      className={clsx(
        "list-group-item list-group-item-action border-start-0 border-end-0 rounded-0 py-2 px-3",
        selected && "active",
      )}
      onClick={onClick}
      data-finding-id={finding.id}
    >
      <div className="d-flex align-items-start gap-2">
        <span className={clsx("badge mt-1", SEVERITY_BADGE[finding.severity])}>
          {finding.severity.toUpperCase()}
        </span>
        <div className="flex-grow-1 min-width-0">
          <div className="d-flex justify-content-between">
            <span className="fw-semibold text-truncate">{finding.scanner}</span>
            <small className="text-body-secondary ms-2 flex-shrink-0">
              #{finding.sample_index}
              {triageIcon && <i className={clsx("bi ms-1", triageIcon)} />}
            </small>
          </div>
          <div
            className={clsx(
              "small text-truncate",
              selected ? "text-white-50" : "text-body-secondary",
            )}
          >
            {finding.explanation}
          </div>
        </div>
      </div>
    </button>
  );
}
