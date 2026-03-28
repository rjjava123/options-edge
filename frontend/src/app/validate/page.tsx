"use client";

import { useState } from "react";
import { validationApi, type Thesis } from "@/lib/api";
import ThesisCard from "@/components/ThesisCard";
import TechnicalSummary from "@/components/TechnicalSummary";

export default function ValidatePage() {
  const [ticker, setTicker] = useState("");
  const [loading, setLoading] = useState(false);
  const [thesis, setThesis] = useState<Thesis | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function analyze() {
    const t = ticker.trim().toUpperCase();
    if (!t) return;
    setLoading(true);
    setError(null);
    setThesis(null);
    try {
      const result = await validationApi.analyze(t);
      setThesis(result);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Analysis failed");
    } finally {
      setLoading(false);
    }
  }

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
      </div>

      {loading && (
        <div className="bg-white border border-slate-200 rounded-xl p-8 text-center">
          <div className="animate-pulse text-slate-500">
            Running full LangGraph analysis for {ticker}...
          </div>
          <p className="text-xs text-slate-400 mt-2">
            This may take 30–60 seconds. Data gathering → Classification → Branch analysis → Synthesis
          </p>
        </div>
      )}

      {error && (
        <div className="bg-red-50 border border-red-200 rounded-lg p-4 text-red-700 text-sm">
          {error}
        </div>
      )}

      {thesis && !loading && (
        <div className="space-y-6">
          <ThesisCard thesis={thesis} detailed />

          {thesis.state_snapshot?.technical_analysis && (
            <TechnicalSummary analysis={thesis.state_snapshot.technical_analysis} />
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
