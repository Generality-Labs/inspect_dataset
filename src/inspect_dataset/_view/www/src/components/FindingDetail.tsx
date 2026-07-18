import React, { useEffect, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { AuditView } from "./AuditView";
import { useParams, useSearchParams } from "react-router-dom";
import { useStore, getFilteredFindings } from "../store";
import { fetchSampleDetail } from "../api";
import type { SampleDetail, TriageStatus } from "../types";

const markdownComponents = {
  table: (props: React.ComponentProps<"table">) => (
    <table className="table table-sm table-bordered w-auto" {...props} />
  ),
};

export function FindingDetail() {
  const finding = useStore((s) => s.selectedFinding);
  const triageFinding = useStore((s) => s.triageFinding);
  const findings = useStore((s) => s.findings);
  const setSelectedFinding = useStore((s) => s.setSelectedFinding);
  const [searchParams] = useSearchParams();
  const { slug } = useParams<{ slug: string }>();
  const [showAudit, setShowAudit] = useState(false);

  // Loaded detail is keyed by (slug, sample_index) so the current sample's
  // detail and loading flag can be derived instead of set in the effect.
  const [loaded, setLoaded] = useState<{
    key: string;
    detail: SampleDetail | null;
  } | null>(null);

  useEffect(() => {
    if (finding == null || !slug) return;
    let cancelled = false;
    const key = `${slug}:${finding.sample_index}`;
    fetchSampleDetail(slug, finding.sample_index).then((d) => {
      if (!cancelled) setLoaded({ key, detail: d });
    });
    return () => {
      cancelled = true;
    };
  }, [finding?.sample_index, slug]);

  const currentKey =
    finding != null && slug ? `${slug}:${finding.sample_index}` : null;
  const sampleDetail =
    loaded && loaded.key === currentKey ? loaded.detail : null;
  const sampleLoading =
    currentKey != null && (loaded == null || loaded.key !== currentKey);

  if (!finding) {
    return (
      <div
        className="d-flex align-items-center justify-content-center text-body-secondary"
        style={{ width: 380, minWidth: 380 }}
      >
        Select a finding to view details.
      </div>
    );
  }

  const handleTriage = (status: TriageStatus) => {
    triageFinding(
      finding.id,
      finding.triage_status === status ? "pending" : status,
    );
  };

  const filtered = getFilteredFindings(
    findings,
    searchParams.get("scanner"),
    searchParams.get("severity"),
    searchParams.get("triage"),
  );
  const idx = filtered.findIndex((f) => f.id === finding.id);

  const navigateFinding = (direction: "prev" | "next") => {
    const next =
      direction === "next"
        ? Math.min(idx + 1, filtered.length - 1)
        : Math.max(idx - 1, 0);
    if (next !== idx) setSelectedFinding(filtered[next]);
  };

  const sampleFindings = findings.filter(
    (f) => f.sample_index === finding.sample_index,
  );

  const allImages = [
    ...(sampleDetail?.images ?? []).map((img) => ({
      src: img.data_url,
      label: img.field,
    })),
    ...(sampleDetail?.files ?? []).map((f) => ({
      src: f.data_url,
      label: f.name,
    })),
  ];

  return (
    <div
      className="border-start d-flex flex-column"
      style={{ width: 380, minWidth: 380, overflowY: "auto" }}
    >
      {showAudit && sampleDetail && (
        <AuditView
          detail={sampleDetail}
          findings={sampleFindings}
          onClose={() => setShowAudit(false)}
        />
      )}
      {/* Finding header */}
      <div className="p-3 border-bottom">
        <div className="d-flex justify-content-between align-items-start mb-2">
          <div>
            <span className="badge bg-primary me-1">{finding.scanner}</span>
            <SeverityBadge severity={finding.severity} />
          </div>
          <span className="text-body-secondary small">
            Sample #{finding.sample_index}
          </span>
        </div>
        <p className="mb-0">{finding.explanation}</p>
      </div>

      {/* Finding metadata */}
      {finding.metadata && Object.keys(finding.metadata).length > 0 && (
        <div className="p-3 border-bottom">
          <h6 className="text-uppercase text-body-secondary small mb-2">
            Details
          </h6>
          <dl className="mb-0 small">
            {Object.entries(finding.metadata).map(([key, value]) => (
              <div key={key} className="mb-1">
                <dt className="d-inline text-body-secondary">{key}: </dt>
                <dd className="d-inline">
                  {typeof value === "object"
                    ? JSON.stringify(value)
                    : String(value)}
                </dd>
              </div>
            ))}
          </dl>
        </div>
      )}

      {/* Sample content */}
      <div className="p-3 border-bottom">
        <h6 className="text-uppercase text-body-secondary small mb-2">
          Sample
        </h6>
        {sampleLoading ? (
          <div className="text-body-secondary small">Loading…</div>
        ) : sampleDetail ? (
          <>
            <div className="mb-2 small">
              <span className="text-body-secondary fw-semibold">Q: </span>
              {sampleDetail.question}
            </div>
            <div className="mb-2 small">
              <span className="text-body-secondary fw-semibold">A: </span>
              {sampleDetail.answer.includes("\n") ? (
                <div className="border rounded p-2 mt-1 audit-markdown">
                  <ReactMarkdown
                    remarkPlugins={[remarkGfm]}
                    components={markdownComponents}
                  >
                    {sampleDetail.answer}
                  </ReactMarkdown>
                </div>
              ) : (
                <span className="font-monospace">{sampleDetail.answer}</span>
              )}
            </div>
            {(allImages.length > 0 || sampleDetail.answer.includes("\n")) && (
              <button
                className="btn btn-sm btn-outline-primary mb-2"
                onClick={() => setShowAudit(true)}
              >
                <i className="bi bi-layout-three-columns me-1" />
                Audit view
              </button>
            )}
            {allImages.map((img) => (
              <img
                key={img.label}
                src={img.src}
                alt={img.label}
                className="img-fluid rounded mb-1 d-block"
                style={{ maxHeight: 240 }}
              />
            ))}
          </>
        ) : (
          <div className="text-body-secondary small">No sample data.</div>
        )}
      </div>

      {/* Triage */}
      <div className="p-3 border-bottom">
        <h6 className="text-uppercase text-body-secondary small mb-2">
          Triage
        </h6>
        <div className="btn-group w-100">
          <button
            className={`btn btn-sm ${
              finding.triage_status === "confirmed"
                ? "btn-danger"
                : "btn-outline-danger"
            }`}
            onClick={() => handleTriage("confirmed")}
            title="Confirm this finding (c)"
          >
            <i className="bi bi-check-circle me-1" />
            Confirm
          </button>
          <button
            className={`btn btn-sm ${
              finding.triage_status === "dismissed"
                ? "btn-success"
                : "btn-outline-success"
            }`}
            onClick={() => handleTriage("dismissed")}
            title="Dismiss this finding (d)"
          >
            <i className="bi bi-x-circle me-1" />
            Dismiss
          </button>
        </div>
      </div>

      {/* Navigation */}
      <div className="p-3 d-flex justify-content-between">
        <button
          className="btn btn-sm btn-outline-secondary"
          onClick={() => navigateFinding("prev")}
          title="Previous finding (p)"
          disabled={idx <= 0}
        >
          <i className="bi bi-chevron-left me-1" />
          Prev
        </button>
        <button
          className="btn btn-sm btn-outline-secondary"
          onClick={() => navigateFinding("next")}
          title="Next finding (n)"
          disabled={idx >= filtered.length - 1}
        >
          Next
          <i className="bi bi-chevron-right ms-1" />
        </button>
      </div>
    </div>
  );
}

function SeverityBadge({ severity }: { severity: string }) {
  const cls: Record<string, string> = {
    high: "bg-danger",
    medium: "bg-warning text-dark",
    low: "bg-secondary",
  };
  return (
    <span className={`badge ${cls[severity] ?? "bg-secondary"}`}>
      {severity.toUpperCase()}
    </span>
  );
}
