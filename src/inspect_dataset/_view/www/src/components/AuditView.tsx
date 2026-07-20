import React, { useEffect, useMemo, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { Finding, SampleDetail } from "../types";

const markdownComponents = {
  table: (props: React.ComponentProps<"table">) => (
    <table className="table table-sm table-bordered w-auto" {...props} />
  ),
};

interface AuditViewProps {
  detail: SampleDetail;
  findings: Finding[];
  onClose: () => void;
}

/** Full-screen three-pane audit: page image | rendered gold | raw source.
 *
 * Finding lines are file-based (sidecar frontmatter included); the raw pane
 * maps them into the markdown body via the sample's line_offset.
 */
export function AuditView({ detail, findings, onClose }: AuditViewProps) {
  const [source, setSource] = useState<string>("gold");

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const pageImage =
    detail.images.find((img) => img.field === "page") ?? detail.images[0];
  const offset = detail.line_offset ?? 0;
  const highlighted = useMemo(() => {
    const lines = new Set<number>();
    for (const f of findings) {
      if (f.line != null) lines.add(f.line - offset);
    }
    return lines;
  }, [findings, offset]);

  const sourceText =
    source === "gold"
      ? detail.answer
      : (detail.tool_outputs?.find((t) => t.name === source)?.text ?? "");

  return (
    <div
      className="position-fixed top-0 start-0 w-100 h-100 d-flex flex-column bg-body"
      style={{ zIndex: 1050 }}
    >
      <div className="d-flex justify-content-between align-items-center border-bottom px-3 py-2">
        <h6 className="mb-0">
          Audit — sample {detail.id ?? detail.index}
          <span className="text-body-secondary ms-2 small">
            {findings.length} finding{findings.length !== 1 ? "s" : ""}
          </span>
        </h6>
        <button
          className="btn btn-sm btn-outline-secondary"
          onClick={onClose}
          title="Close (Esc)"
        >
          <i className="bi bi-x-lg me-1" />
          Close
        </button>
      </div>

      <div className="flex-grow-1 d-flex overflow-hidden">
        {/* Page image */}
        <div
          className="border-end p-2 overflow-auto"
          style={{ flex: 1, minWidth: 0 }}
        >
          <div className="text-uppercase text-body-secondary small mb-2">
            Page
          </div>
          {pageImage ? (
            <img src={pageImage.data_url} alt="page" className="img-fluid" />
          ) : (
            <div className="text-body-secondary small">No page image.</div>
          )}
        </div>

        {/* Rendered gold */}
        <div
          className="border-end p-3 overflow-auto"
          style={{ flex: 1, minWidth: 0 }}
        >
          <div className="text-uppercase text-body-secondary small mb-2">
            Rendered gold
          </div>
          <div className="audit-markdown small">
            <ReactMarkdown
              remarkPlugins={[remarkGfm]}
              components={markdownComponents}
            >
              {detail.answer}
            </ReactMarkdown>
          </div>
        </div>

        {/* Raw source with finding-line highlights */}
        <div
          className="p-2 overflow-auto d-flex flex-column"
          style={{ flex: 1, minWidth: 0 }}
        >
          <div className="d-flex justify-content-between align-items-center mb-2">
            <div className="text-uppercase text-body-secondary small">
              Source
            </div>
            {detail.tool_outputs && detail.tool_outputs.length > 0 && (
              <select
                className="form-select form-select-sm w-auto"
                value={source}
                onChange={(e) => setSource(e.target.value)}
              >
                <option value="gold">gold markdown</option>
                {detail.tool_outputs.map((t) => (
                  <option key={t.name} value={t.name}>
                    {t.name}
                  </option>
                ))}
              </select>
            )}
          </div>
          <pre className="small mb-0 flex-grow-1" style={{ whiteSpace: "pre" }}>
            {sourceText.split("\n").map((line, i) => {
              const isHit = source === "gold" && highlighted.has(i + 1);
              return (
                <div
                  key={i}
                  className={isHit ? "bg-warning-subtle" : undefined}
                  style={{ display: "flex" }}
                >
                  <span
                    className="text-body-tertiary me-2 user-select-none text-end"
                    style={{ minWidth: "3ch" }}
                  >
                    {i + 1}
                  </span>
                  <span>{line || " "}</span>
                </div>
              );
            })}
          </pre>
        </div>
      </div>
    </div>
  );
}
