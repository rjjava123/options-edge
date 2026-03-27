"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { thesesApi, type Thesis } from "@/lib/api";

const STATUSES = ["open", "closed_target", "closed_stop", "closed_expiry", "closed_manual"];

function badge(status: string) {
  const map: Record<string, string> = {
    open: "bg-blue-100 text-blue-700",
    closed_target: "bg-green-100 text-green-700",
    closed_stop: "bg-red-100 text-red-700",
    closed_expiry: "bg-slate-100 text-slate-600",
    closed_manual: "bg-yellow-100 text-yellow-700",
  };
  return map[status] ?? "bg-slate-100 text-slate-600";
}

export default function HistoryPage() {
  const [theses, setTheses] = useState<Thesis[]>([]);
  const [loading, setLoading] = useState(true);
  const [statusFilter, setStatusFilter] = useState("");
  const [tickerFilter, setTickerFilter] = useState("");
  const [activeFilter, setActiveFilter] = useState<"" | "true" | "false">("");

  async function load() {
    setLoading(true);
    try {
      const data = await thesesApi.list({
        status: statusFilter || undefined,
        ticker: tickerFilter || undefined,
        is_active: activeFilter === "" ? undefined : activeFilter === "true",
        limit: 100,
      });
      setTheses(data);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { load(); }, [statusFilter, tickerFilter, activeFilter]);

  return (
    <div>
      <h1 className="text-2xl font-bold text-slate-900 mb-6">Thesis History & Scoring</h1>

      {/* Filters */}
      <div className="flex flex-wrap gap-4 mb-6 bg-white p-4 rounded-lg border border-slate-200">
        <div>
          <label className="block text-xs font-medium text-slate-500 mb-1">Ticker</label>
          <input
            type="text"
            value={tickerFilter}
            onChange={(e) => setTickerFilter(e.target.value.toUpperCase())}
            placeholder="e.g. AAPL"
            className="border border-slate-300 rounded px-2 py-1 text-sm w-24 font-mono"
          />
        </div>
        <div>
          <label className="block text-xs font-medium text-slate-500 mb-1">Status</label>
          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            className="border border-slate-300 rounded px-2 py-1 text-sm"
          >
            <option value="">All</option>
            {STATUSES.map((s) => <option key={s} value={s}>{s}</option>)}
          </select>
        </div>
        <div>
          <label className="block text-xs font-medium text-slate-500 mb-1">Active</label>
          <select
            value={activeFilter}
            onChange={(e) => setActiveFilter(e.target.value as "" | "true" | "false")}
            className="border border-slate-300 rounded px-2 py-1 text-sm"
          >
            <option value="">All</option>
            <option value="true">Active</option>
            <option value="false">Not Active</option>
          </select>
        </div>
      </div>

      {loading ? (
        <div className="text-center py-16 text-slate-400">Loading...</div>
      ) : theses.length === 0 ? (
        <div className="text-center py-16 text-slate-400">No theses match your filters.</div>
      ) : (
        <div className="overflow-x-auto bg-white rounded-xl border border-slate-200">
          <table className="w-full text-sm">
            <thead className="bg-slate-50 border-b border-slate-200">
              <tr>
                {["Ticker", "Direction", "Spread", "Confidence", "Status", "Active", "Created", ""].map((h) => (
                  <th key={h} className="px-4 py-3 text-left text-xs font-semibold text-slate-500 uppercase tracking-wide">
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {theses.map((t) => (
                <tr key={t.id} className="hover:bg-slate-50 transition-colors">
                  <td className="px-4 py-3 font-mono font-semibold text-slate-900">{t.ticker}</td>
                  <td className="px-4 py-3 capitalize text-slate-700">{t.direction}</td>
                  <td className="px-4 py-3 text-slate-600">{t.spread_type}</td>
                  <td className="px-4 py-3">
                    <span className="text-slate-700">{Math.round(t.confidence * 100)}%</span>
                  </td>
                  <td className="px-4 py-3">
                    <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${badge(t.status)}`}>
                      {t.status}
                    </span>
                  </td>
                  <td className="px-4 py-3">
                    {t.is_active ? (
                      <span className="text-green-600 font-medium">Yes</span>
                    ) : (
                      <span className="text-slate-400">No</span>
                    )}
                  </td>
                  <td className="px-4 py-3 text-slate-500">
                    {new Date(t.created_at).toLocaleDateString()}
                  </td>
                  <td className="px-4 py-3">
                    <Link href={`/thesis/${t.id}`} className="text-blue-600 hover:underline text-xs">
                      View →
                    </Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
