import { useMemo } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { AgGridReact } from "ag-grid-react";
import { useStore } from "../store";
import type { Finding, Sample } from "../types";
import type { ColDef, ICellRendererParams } from "ag-grid-community";
import {
  AllCommunityModule,
  ModuleRegistry,
  themeQuartz,
} from "ag-grid-community";

ModuleRegistry.registerModules([AllCommunityModule]);

interface SampleRow {
  index: number;
  id: string | number | null;
  question: string;
  answer: string;
  findings: Finding[];
}

const SEVERITY_ORDER: Record<string, number> = { high: 0, medium: 1, low: 2 };

function FindingsBadges({ findings }: { findings: Finding[] }) {
  if (findings.length === 0)
    return <span className="text-body-secondary">—</span>;

  const sorted = [...findings].sort(
    (a, b) =>
      (SEVERITY_ORDER[a.severity] ?? 3) - (SEVERITY_ORDER[b.severity] ?? 3),
  );

  const badgeCls: Record<string, string> = {
    high: "bg-danger",
    medium: "bg-warning text-dark",
    low: "bg-secondary",
  };

  return (
    <span>
      {sorted.map((f) => (
        <span
          key={f.id}
          className={`badge ${badgeCls[f.severity] ?? "bg-secondary"} me-1`}
        >
          {f.scanner}
        </span>
      ))}
    </span>
  );
}

function TextCell({ value }: { value: string }) {
  return (
    <span
      title={value}
      style={{
        display: "block",
        overflow: "hidden",
        textOverflow: "ellipsis",
        whiteSpace: "nowrap",
      }}
    >
      {value}
    </span>
  );
}

export function SamplesTab() {
  const findings = useStore((s) => s.findings);
  const samples = useStore((s) => s.samples);
  const summary = useStore((s) => s.summary);
  const setSelectedFinding = useStore((s) => s.setSelectedFinding);
  const navigate = useNavigate();
  const { slug } = useParams<{ slug: string }>();

  const sampleMap = useMemo(() => {
    const m = new Map<number, Sample>();
    for (const s of samples) m.set(s.index, s);
    return m;
  }, [samples]);

  const rows: SampleRow[] = useMemo(() => {
    const totalSamples = summary?.total_samples ?? 0;
    const byIndex = new Map<number, Finding[]>();
    for (const f of findings) {
      const list = byIndex.get(f.sample_index) ?? [];
      list.push(f);
      byIndex.set(f.sample_index, list);
    }
    const result: SampleRow[] = [];
    for (let i = 0; i < totalSamples; i++) {
      const sample = sampleMap.get(i);
      result.push({
        index: i,
        id: sample?.id ?? null,
        question: sample?.question ?? "",
        answer: sample?.answer ?? "",
        findings: byIndex.get(i) ?? [],
      });
    }
    return result;
  }, [findings, summary, sampleMap]);

  const hasSamples = samples.length > 0;

  const columnDefs: ColDef<SampleRow>[] = useMemo(
    () => [
      {
        headerName: "#",
        field: "index",
        width: 70,
        sort: "asc" as const,
      },
      ...(hasSamples
        ? [
            {
              headerName: "Question",
              field: "question" as const,
              flex: 2,
              cellRenderer: (params: ICellRendererParams<SampleRow>) =>
                params.value != null ? (
                  <TextCell value={String(params.value)} />
                ) : null,
            },
            {
              headerName: "Answer",
              field: "answer" as const,
              flex: 1,
              cellRenderer: (params: ICellRendererParams<SampleRow>) =>
                params.value != null ? (
                  <TextCell value={String(params.value)} />
                ) : null,
            },
          ]
        : []),
      {
        headerName: "Findings",
        field: "findings",
        flex: hasSamples ? 0 : 1,
        width: hasSamples ? 220 : undefined,
        cellRenderer: (params: ICellRendererParams<SampleRow>) => {
          const row = params.data;
          if (!row) return null;
          return <FindingsBadges findings={row.findings} />;
        },
        comparator: (a: Finding[], b: Finding[]) => a.length - b.length,
      },
      {
        headerName: "N",
        width: 60,
        valueGetter: (params: { data?: SampleRow }) =>
          params.data?.findings.length ?? 0,
      },
    ],
    [hasSamples],
  );

  const onRowClicked = (event: { data?: SampleRow }) => {
    const row = event.data;
    if (row && row.findings.length > 0) {
      setSelectedFinding(row.findings[0]);
      navigate(`/${slug}/findings`);
    }
  };

  return (
    <div className="flex-grow-1 d-flex flex-column" style={{ minHeight: 0 }}>
      <div style={{ width: "100%", height: "100%", flex: 1, minHeight: 0 }}>
        <AgGridReact<SampleRow>
          theme={themeQuartz}
          rowData={rows}
          columnDefs={columnDefs}
          onRowClicked={onRowClicked}
          rowSelection="single"
          getRowStyle={(params) => {
            if (params.data && params.data.findings.length === 0) {
              return { opacity: "0.5" };
            }
            return undefined;
          }}
        />
      </div>
    </div>
  );
}
