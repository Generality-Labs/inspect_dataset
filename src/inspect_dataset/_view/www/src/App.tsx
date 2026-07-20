import { useEffect, useState } from "react";
import { Navigate, Outlet, Route, Routes, useParams } from "react-router-dom";
import { useStore } from "./store";
import { useKeyboard } from "./hooks/useKeyboard";
import { Header } from "./components/Header";
import { ScannerSidebar } from "./components/ScannerSidebar";
import { FindingsList } from "./components/FindingsList";
import { FindingDetail } from "./components/FindingDetail";
import { SamplesTab } from "./components/SamplesTab";
import { DatasetPicker } from "./components/DatasetPicker";
import { ExplorerHome } from "./components/ExplorerHome";
import { ExplorerView } from "./components/ExplorerView";
import { exportUrl } from "./api";
import type { DatasetInfo } from "./types";
import { fetchDatasets } from "./api";

// ── Loading / error screens ────────────────────────────────────────────────

function LoadingScreen() {
  return (
    <div className="d-flex align-items-center justify-content-center vh-100">
      <div className="spinner-border text-primary" role="status">
        <span className="visually-hidden">Loading…</span>
      </div>
    </div>
  );
}

function ErrorScreen({ message }: { message: string }) {
  return (
    <div className="d-flex align-items-center justify-content-center vh-100">
      <div className="alert alert-danger">{message}</div>
    </div>
  );
}

// ── Root redirect — fetch datasets or show explorer home ──────────────────

function DatasetRedirect() {
  const loadDatasets = useStore((s) => s.loadDatasets);
  const [datasets, setDatasets] = useState<DatasetInfo[] | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    fetchDatasets()
      .then((ds) => {
        loadDatasets(); // populate store for switcher
        setDatasets(ds);
      })
      .catch((e) => setErr(String(e)));
  }, [loadDatasets]);

  if (err) return <ErrorScreen message={err} />;
  if (datasets === null) return <LoadingScreen />;

  // No pre-loaded findings → go straight to explorer home
  if (datasets.length === 0) return <ExplorerHome />;

  // One dataset pre-loaded → jump directly to findings view
  if (datasets.length === 1)
    return <Navigate to={`/${datasets[0].slug}/findings`} replace />;

  return <DatasetPicker datasets={datasets} />;
}

// ── Per-dataset layout — loads data when slug changes ─────────────────────

function DatasetLayout() {
  const { slug } = useParams<{ slug: string }>();
  const loadDataset = useStore((s) => s.loadDataset);
  const loadDatasets = useStore((s) => s.loadDatasets);
  const currentSlug = useStore((s) => s.currentSlug);
  const datasets = useStore((s) => s.datasets);
  const loading = useStore((s) => s.loading);
  const error = useStore((s) => s.error);

  useKeyboard();

  // Load dataset list (for switcher) and dataset data when slug changes
  useEffect(() => {
    if (datasets.length === 0) loadDatasets();
  }, [datasets.length, loadDatasets]);

  useEffect(() => {
    if (slug && slug !== currentSlug) {
      loadDataset(slug);
    }
  }, [slug, currentSlug, loadDataset]);

  if (loading) return <LoadingScreen />;
  if (error) return <ErrorScreen message={error} />;

  return (
    <div className="d-flex flex-column vh-100">
      <Header />

      <div className="d-flex flex-grow-1" style={{ minHeight: 0 }}>
        <Outlet />
      </div>

      <footer className="border-top bg-body-tertiary px-3 py-1 d-flex justify-content-between align-items-center small text-body-secondary">
        <span>
          Keyboard: <kbd>c</kbd> confirm · <kbd>d</kbd> dismiss · <kbd>n</kbd>/
          <kbd>p</kbd> next/prev
        </span>
        <a
          href={exportUrl(slug ?? "")}
          className="btn btn-sm btn-outline-secondary"
          download
        >
          Export clean_ids.txt
        </a>
      </footer>
    </div>
  );
}

// ── Findings page ──────────────────────────────────────────────────────────

function FindingsPage() {
  return (
    <>
      <ScannerSidebar />
      <FindingsList />
      <FindingDetail />
    </>
  );
}

// ── Root ───────────────────────────────────────────────────────────────────

function App() {
  return (
    <Routes>
      <Route path="/" element={<DatasetRedirect />} />
      {/* Explorer routes */}
      <Route path="/explore" element={<ExplorerHome />} />
      <Route path="/explore/:sessionId" element={<ExplorerView />} />
      {/* Findings routes */}
      <Route path="/:slug" element={<DatasetLayout />}>
        <Route index element={<Navigate to="findings" replace />} />
        <Route path="findings" element={<FindingsPage />} />
        <Route path="samples" element={<SamplesTab />} />
      </Route>
    </Routes>
  );
}

export default App;
