"use client";

import { useEffect, useState } from "react";
import { discoveryApi, type Thesis } from "@/lib/api";
import ThesisCard from "@/components/ThesisCard";

const CLASSIFICATIONS = ["catalyst", "technical", "mean_reversion", "flow_driven", "range_bound"];
const SPREAD_TYPES = ["bull_put", "bear_call", "iron_condor", "bull_call_debit", "bear_put_debit"];

export default function DiscoveryPage() {
  const [theses, setTheses] = useState<Thesis[]>([]);
  const [filtered, setFiltered] = useState<Thesis[]>([]);
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState(false);
  const [status, setStatus] = useState<{ last_run: string | null; candidates_found: number | null }>({
    last_run: null,
    candidates_found: null,
  });
  const [classFilter, setClassFilter] = useState("");
  const [spreadFilter, setSpreadFilter] = useState("");
  const [minConf, setMinConf] = useState(0);

  async function load() {
    setLoading(true);
    try {
      const [s, t] = await Promise.all([
        discoveryApi.getStatus(),
        discoveryApi.getLatestTheses(),
      ]);
      setStatus(s);
      setTheses(t);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { load(); }, []);

  useEffect(() => {
    let result = theses;
    if (classFilter) result = result.filter((t) => t.setup_classifications?.includes(classFilter));
    if (spreadFilter) result = result.filter((t) => t.spread_type === spreadFilter);
    if (minConf > 0) result = result.filter((t) => t.confidence >= minConf / 100);
    setFiltered(result);
  }, [theses, classFilter, spreadFilter, minConf]);

  async function runNow() {
    setRunning(true);
    try {
      await discoveryApi.runNow();
      setTimeout(load, 3000);
    } finally {
      setRunning(false);
    }
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Discovery Dashboard</h1>
          {status.last_run && (
            <p className="text-sm text-slate-500 mt-1">
              Last scan: {new Date(status.last_run).toLocaleString()} &mdash;{" "}
              {status.candidates_found} candidates found
            </p>
          )}
        </div>
        <button
          onClick={runNow}
          disabled={running}
          className="px-4 py-2 bg-blue-600 text-white rounded-lg text-sm font-medium hover:bg-blue-700 disabled:opacity-50 transition-colors"
        >
          {running ? "Running..." : "Run Now"}
        </button>
      </div>

      {/* Filters */}
      <div className="flex flex-wrap gap-4 mb-6 bg-white p-4 rounded-lg border border-slate-200">
        <div>
          <label className="block text-xs font-medium text-slate-500 mb-1">Classification</label>
          <select
            value={classFilter}
            onChange={(e) => setClassFilter(e.target.value)}
            className="border border-slate-300 rounded px-2 py-1 text-sm"
          >
            <option value="">All</option>
            {CLASSIFICATIONS.map((c) => <option key={c} value={c}>{c}</option>)}
          </select>
        </div>
        <div>
          <label className="block text-xs font-medium text-slate-500 mb-1">Spread Type</label>
          <select
            value={spreadFilter}
            onChange={(e) => setSpreadFilter(e.target.value)}
            className="border border-slate-300 rounded px-2 py-1 text-sm"
          >
            <option value="">All</option>
            {SPREAD_TYPES.map((s) => <option key={s} value={s}>{s}</option>)}
          </select>
        </div>
        <div>
          <label className="block text-xs font-medium text-slate-500 mb-1">
            Min Confidence: {minConf}%
          </label>
          <input
            type="range"
            min={0}
            max={100}
            step={5}
            value={minConf}
            onChange={(e) => setMinConf(Number(e.target.value))}
            className="w-32"
          />
        </div>
      </div>

      {loading ? (
        <div className="text-center py-20 text-slate-400">Loading...</div>
      ) : filtered.length === 0 ? (
        <div className="text-center py-20 text-slate-400">
          No theses found. Run a discovery scan to get started.
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
          {filtered.map((t) => <ThesisCard key={t.id} thesis={t} />)}
        </div>
      )}
    </div>
  );
}
