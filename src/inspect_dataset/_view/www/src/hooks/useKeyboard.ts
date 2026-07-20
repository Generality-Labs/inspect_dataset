import { useEffect } from "react";
import { useSearchParams } from "react-router-dom";
import { useStore, getFilteredFindings } from "../store";

export function useKeyboard() {
  const triageFinding = useStore((s) => s.triageFinding);
  const selectedFinding = useStore((s) => s.selectedFinding);
  const setSelectedFinding = useStore((s) => s.setSelectedFinding);
  const findings = useStore((s) => s.findings);
  const [searchParams] = useSearchParams();

  useEffect(() => {
    function handler(e: KeyboardEvent) {
      const tag = (e.target as HTMLElement).tagName;
      if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return;

      if (!selectedFinding) return;

      const filtered = getFilteredFindings(
        findings,
        searchParams.get("scanner"),
        searchParams.get("severity"),
        searchParams.get("triage"),
      );

      switch (e.key) {
        case "c":
          triageFinding(
            selectedFinding.id,
            selectedFinding.triage_status === "confirmed"
              ? "pending"
              : "confirmed",
          );
          break;
        case "d":
          triageFinding(
            selectedFinding.id,
            selectedFinding.triage_status === "dismissed"
              ? "pending"
              : "dismissed",
          );
          break;
        case "n": {
          const idx = filtered.findIndex((f) => f.id === selectedFinding.id);
          const next = Math.min(idx + 1, filtered.length - 1);
          if (next !== idx) setSelectedFinding(filtered[next]);
          break;
        }
        case "p": {
          const idx = filtered.findIndex((f) => f.id === selectedFinding.id);
          const prev = Math.max(idx - 1, 0);
          if (prev !== idx) setSelectedFinding(filtered[prev]);
          break;
        }
      }
    }

    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [
    selectedFinding,
    findings,
    searchParams,
    triageFinding,
    setSelectedFinding,
  ]);
}
