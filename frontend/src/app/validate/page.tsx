"use client";

import { useCallback, useRef, useState } from "react";
import { validationApi, type Thesis } from "@/lib/api";
import ThesisCard from "@/components/ThesisCard";
import TechnicalSummary from "@/components/TechnicalSummary";

interface ProgressStep {
  node: string;
  status: "running" | "complete" | "error";
  summary?: Record<string, unknown>;
  error?: string;
}

const NODE_LABELS: Record<string, string> = {
  fetch_market_data: "Fetching market data",
  fetch_options_chain: "Fetching options chain",
  fetch_news_context: "Fetching news context",
  detect_technical_patterns: "Detecting technical patterns",
  detect_unusual_activity: "Detecting unusual activity",
  classify_context: "Classifying setup",
  analyze_catalyst: "Analyzing catalyst thesis",
  analyze_technical: "Analyzing technical thesis",
  analyze_mean_reversion: "Analyzing mean reversion",
  analyze_flow_driven: "Analyzing flow-driven thesis",
  analyze_range_bound: "Analyzing range-bound thesis",
  check_trap_detection: "Checking trap detection",
  synthesize_thesis: "Synthesizing thesis",
  save_thesis: "Saving thesis",
};

export default function ValidatePage() {
  const [ticker, setTicker] = useState("");
  const [loading, setLoading] = useState(false);
  const [steps, setSteps] = useState<ProgressStep[]>([]);
  const [thesis, setThesis] = useState<Thesis | null>(null);
  const [error, setError] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  const analyze = useCallback(async () => {
    const t = ticker.trim().toUpperCase();
    if (!t) return;

    // Abort any previous in-flight analysis
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;

    setLoading(true);
    setError(null);
    setThesis(null);
    setSteps([]);

    try {
      await validationApi.analyzeStream(
        t,
        (eventType, data) => {
          switch (eventType) {
            case "node_start":
              setSteps((prev) => [
                ...prev,
                { node: (data as { node: string }).node, status: "running" },
              ]);
              break;

            case "node_complete":
              setSteps((prev) =>
                prev.map((s) =>
                  s.node === (data as { node: string }).node
                    ? { ...s, status: "complete" as const, summary: data as Record<string, unknown> }
                    : s
                )
              );
              break;

            case "node_error":
              setSteps((prev) =>
                prev.map((s) =>
                  s.node === (data as { node: string }).node
                    ? { ...s, status: "error" as const, error: (data as { error: string }).error }
                    : s
                )
              );
              break;

            case "thesis":
              setThesis(data as unknown as Thesis);
              break;

            case "error":
              setError((data as { message: string }).message);
              break;

            case "complete":
              // Stream finished
              break;
          }
        },
        controller.signal,
      );
    } catch (e: unknown) {
      if ((e as Error).name !== "AbortError") {
        setError(e instanceof Error ? e.message : "Analysis failed");
      }
    } finally {
      setLoading(false);
    }
  }, [ticker]);

  return (
    <div className="max-w-4xl">
      <h1 className="text-2xl font-bold text-slate-900 mb-6">Thesis Generator</h1>

      <div className="flex gap-3 mb-8">
        <input
          type="text"
          placeholder="Enter ticker (e.g. AAPL)"
          value={ticker}
          onChange={(e) => setTicker(e.target.value.toUpperCase())}
          onKeyDown={(e) => e.key === "Enter" && analyze()}
          className="border border-slate-300 rounded-lg px-4 py-2 text-sm w-48 font-mono uppercase focus:outline-none focus:ring-2 focus:ring-blue-500"
          maxLength={10}
        />
        <button
          onClick={analyze}
          disabled={loading || !ticker.trim()}
          className="px-6 py-2 bg-blue-600 text-white rounded-lg text-sm font-medium hover:bg-blue-700 disabled:opacity-50 transition-colors"
        >
          {loading ? "Analyzing..." : "Analyze"}
        </button>
        {loading && (
          <button
            onClick={() => abortRef.current?.abort()}
            className="px-4 py-2 bg-red-100 text-red-700 rounded-lg text-sm font-medium hover:bg-red-200 transition-colors"
          >
            Cancel
          </button>
        )}
      </div>

      {/* Live progress steps */}
      {steps.length > 0 && (
        <div className="bg-white border border-slate-200 rounded-xl p-6 mb-6">
          <h2 className="text-sm font-semibold text-slate-700 mb-3">Pipeline Progress</h2>
          <div className="space-y-2">
            {steps.map((step) => (
              <div key={step.node} className="flex items-center gap-3 text-sm">
                <span className="w-5 text-center">
                  {step.status === "running" && (
                    <span className="inline-block w-3 h-3 border-2 border-blue-500 border-t-transparent rounded-full animate-spin" />
                  )}
                  {step.status === "complete" && (
                    <span className="text-green-600">&#10003;</span>
                  )}
                  {step.status === "error" && (
                    <span className="text-red-600">&#10007;</span>
                  )}
                </span>
                <span
                  className={
                    step.status === "running"
                      ? "text-blue-700 font-medium"
                      : step.status === "error"
                      ? "text-red-600"
                      : "text-slate-500"
                  }
                >
                  {NODE_LABELS[step.node] ?? step.node}
                </span>
                {step.status === "complete" && step.summary?.price && (
                  <span className="text-xs text-slate-400 ml-auto">
                    ${Number(step.summary.price).toFixed(2)}
                  </span>
                )}
                {step.status === "complete" && step.summary?.contracts_count && (
                  <span className="text-xs text-slate-400 ml-auto">
                    {step.summary.contracts_count} contracts
                  </span>
                )}
                {step.status === "complete" && step.summary?.classifications && (
                  <span className="text-xs text-slate-400 ml-auto">
                    {(step.summary.classifications as string[]).join(", ")}
                  </span>
                )}
                {step.status === "error" && step.error && (
                  <span className="text-xs text-red-400 ml-auto truncate max-w-xs">
                    {step.error}
                  </span>
                )}
              </div>
            ))}
          </div>
          {loading && (
            <p className="text-xs text-slate-400 mt-3">
              Data gathering → Classification → Branch analysis → Synthesis
            </p>
          )}
        </div>
      )}

      {error && (
        <div className="bg-red-50 border border-red-200 rounded-lg p-4 text-red-700 text-sm mb-6">
          {error}
        </div>
      )}

      {thesis && !loading && (
        <div className="space-y-6">
          <ThesisCard thesis={thesis} detailed />

          {(thesis as Thesis & { state_snapshot?: Record<string, unknown> }).state_snapshot
            ?.technical_analysis && (
            <TechnicalSummary
              analysis={
                (thesis as Thesis & { state_snapshot?: Record<string, unknown> }).state_snapshot!
                  .technical_analysis as Record<string, unknown>
              }
            />
          )}

          <div className="bg-white border border-slate-200 rounded-xl p-6">
            <h2 className="font-semibold text-slate-800 mb-3">Full Reasoning</h2>
            <pre className="text-sm text-slate-600 whitespace-pre-wrap leading-relaxed">
              {thesis.reasoning}
            </pre>
          </div>

          <div className="flex gap-3">
            <a
              href={`/thesis/${thesis.id}`}
              className="px-4 py-2 bg-slate-100 text-slate-700 rounded-lg text-sm font-medium hover:bg-slate-200 transition-colors"
            >
              View Full Detail
            </a>
          </div>
        </div>
      )}
    </div>
  );
}
