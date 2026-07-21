import { create } from "zustand";
import type {
  DatasetInfo,
  ExplorerSession,
  Finding,
  Sample,
  SchemaInfo,
  Summary,
  TriageStatus,
} from "./types";
import {
  fetchDatasets,
  fetchExplorerSchema,
  fetchFindings,
  fetchSamples,
  fetchSummary,
  loadExplorerSession,
  postTriage,
} from "./api";

interface AppState {
  // Dataset list (loaded once on startup)
  datasets: DatasetInfo[];

  // Currently viewed dataset (findings mode)
  currentSlug: string | null;
  summary: Summary | null;
  findings: Finding[];
  samples: Sample[];
  loading: boolean;
  error: string | null;

  // UI state
  selectedFinding: Finding | null;

  // Explorer session state
  explorerSession: ExplorerSession | null;
  explorerSchema: SchemaInfo | null;
  explorerLoading: boolean;
  explorerError: string | null;

  // Actions
  setSelectedFinding: (finding: Finding | null) => void;
  loadDatasets: () => Promise<void>;
  loadDataset: (slug: string) => Promise<void>;
  triageFinding: (findingId: number, status: TriageStatus) => Promise<void>;
  startExplorerSession: (
    source: string,
    sourceType: "hf" | "inspect_task",
    split: string,
    limit?: number,
    config?: string,
  ) => Promise<ExplorerSession | null>;
  clearExplorerSession: () => void;
}

export const useStore = create<AppState>((set, get) => ({
  datasets: [],
  currentSlug: null,
  summary: null,
  findings: [],
  samples: [],
  loading: false,
  error: null,

  selectedFinding: null,

  explorerSession: null,
  explorerSchema: null,
  explorerLoading: false,
  explorerError: null,

  setSelectedFinding: (finding) => set({ selectedFinding: finding }),

  startExplorerSession: async (source, sourceType, split, limit, config) => {
    set({
      explorerLoading: true,
      explorerError: null,
      explorerSession: null,
      explorerSchema: null,
    });
    try {
      const session = await loadExplorerSession(
        source,
        sourceType,
        split,
        limit,
        config,
      );
      const schema = await fetchExplorerSchema(session.session_id);
      set({
        explorerSession: session,
        explorerSchema: schema,
        explorerLoading: false,
      });
      return session;
    } catch (e) {
      set({ explorerError: String(e), explorerLoading: false });
      return null;
    }
  },

  clearExplorerSession: () =>
    set({ explorerSession: null, explorerSchema: null, explorerError: null }),

  loadDatasets: async () => {
    try {
      const datasets = await fetchDatasets();
      set({ datasets });
    } catch (e) {
      set({ error: String(e) });
    }
  },

  loadDataset: async (slug: string) => {
    set({
      loading: true,
      error: null,
      currentSlug: slug,
      selectedFinding: null,
    });
    try {
      const [summary, findings, samples] = await Promise.all([
        fetchSummary(slug),
        fetchFindings(slug),
        fetchSamples(slug),
      ]);
      set({ summary, findings, samples, loading: false });
    } catch (e) {
      set({ error: String(e), loading: false });
    }
  },

  triageFinding: async (findingId, status) => {
    const slug = get().currentSlug;
    if (!slug) return;
    await postTriage(slug, findingId, status);
    set((state) => ({
      findings: state.findings.map((f) =>
        f.id === findingId ? { ...f, triage_status: status } : f,
      ),
      selectedFinding:
        state.selectedFinding?.id === findingId
          ? { ...state.selectedFinding, triage_status: status }
          : state.selectedFinding,
    }));
  },
}));

/** Apply scanner/severity/triage filters to a findings list. */
export function getFilteredFindings(
  findings: Finding[],
  scanner: string | null,
  severity: string | null,
  triage: string | null,
): Finding[] {
  let result = findings;
  if (scanner) result = result.filter((f) => f.scanner === scanner);
  if (severity) result = result.filter((f) => f.severity === severity);
  if (triage) result = result.filter((f) => f.triage_status === triage);
  return result;
}

/** Scanner name → finding count (from full findings list). */
export function getScannerCounts(findings: Finding[]): Record<string, number> {
  const counts: Record<string, number> = {};
  for (const f of findings) {
    counts[f.scanner] = (counts[f.scanner] || 0) + 1;
  }
  return counts;
}
