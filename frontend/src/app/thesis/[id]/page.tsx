"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { thesesApi, type Thesis } from "@/lib/api";
import PnLChart from "@/components/PnLChart";
import ScoreForm from "@/components/ScoreForm";
import TechnicalSummary from "@/components/TechnicalSummary";

export default function ThesisDetailPage() {
  const { id } = useParams<{ id: string }>();
  const [thesis, setThesis] = useState<Thesis | null>(null);
  const [loading, setLoading] = useState(true);
  const [trapWarnings, setTrapWarnings] = useState<string[]>([]);
  const [checkingTrap, setCheckingTrap] = useState(false);

  async function load() {
    setLoading(true);
    try {
      const data = await thesesApi.get(id);
      setThesis(data);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { load(); }, [id]);

  async function checkTrap() {
    setCheckingTrap(true);
    try {
      const result = await thesesApi.checkTrapDetection(id);
      setTrapWarnings(result.warnings);
    } finally {
      setCheckingTrap(false);
    }
  }

  async function toggleActive() {
    if (!thesis) return;
    await thesesApi.toggleActive(id, !thesis.is_active);
    await load();
  }

  if (loading) return <div className="text-center py-20 text-slate-400">Loading...</div>;
  if (!thesis) return <div className="text-center py-20 text-slate-400">Thesis not found.</div>;

  const snapshots = thesis.daily_snapshots ?? [];

  return (
    <div className="max-w-4xl space-y-6">
      {/* Header */}
      <div className="bg-white border border-slate-200 rounded-xl p-6">
        <div className="flex items-start justify-between">
          <div>
            <div className="flex items-center gap-3 mb-2">
              <h1 className="text-3xl font-bold font-mono text-slate-900">{thesis.ticker}</h1>
              <span className="px-2 py-1 bg-blue-100 text-blue-700 rounded text-sm capitalize">
                {thesis.direction}
              </span>
              <span className="px-2 py-1 bg-slate-100 text-slate-600 rounded text-sm">
                {thesis.spread_type}
              </span>
            </div>
            <div className="text-slate-500 text-sm">
              Generated {new Date(thesis.created_at).toLocaleString()} &middot; {thesis.flow_type}
            </div>
            <div className="flex flex-wrap gap-2 mt-2">
              {thesis.setup_classifications?.map((c) => (
                <span key={c} className="px-2 py-0.5 bg-purple-100 text-purple-700 rounded text-xs">
                  {c}
                </span>
              ))}
            </div>
          </div>
          <div className="text-right">
            <div className="text-2xl font-bold text-slate-900">
              {Math.round(thesis.confidence * 100)}%
            </div>
            <div className="text-xs text-slate-400">confidence</div>
          </div>
        </div>

        {/* Trade details */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 mt-6 pt-6 border-t border-slate-100">
          {[
            { label: "Short Strike", value: `$${thesis.short_strike}` },
            { label: "Long Strike", value: `$${thesis.long_strike}` },
            { label: "Expiration", value: thesis.expiration_date },
            { label: "Entry Price", value: `$${thesis.entry_price.toFixed(2)}` },
            { label: "Max Profit", value: `$${thesis.max_profit.toFixed(2)}` },
            { label: "Max Loss", value: `$${thesis.max_loss.toFixed(2)}` },
            { label: "Profit Target", value: `${Math.round(thesis.profit_target * 100)}%` },
            { label: "Stop Loss", value: `$${thesis.stop_loss.toFixed(2)}` },
          ].map(({ label, value }) => (
            <div key={label}>
              <div className="text-xs text-slate-400 mb-0.5">{label}</div>
              <div className="font-semibold text-slate-800">{value}</div>
            </div>
          ))}
        </div>

        <div className="flex gap-3 mt-6">
          <button
            onClick={toggleActive}
            className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
              thesis.is_active
                ? "bg-red-50 text-red-700 hover:bg-red-100"
                : "bg-green-50 text-green-700 hover:bg-green-100"
            }`}
          >
            {thesis.is_active ? "Unmark Active" : "Mark Active"}
          </button>
          <button
            onClick={checkTrap}
            disabled={checkingTrap}
            className="px-4 py-2 bg-yellow-50 text-yellow-700 rounded-lg text-sm font-medium hover:bg-yellow-100 disabled:opacity-50 transition-colors"
          >
            {checkingTrap ? "Checking..." : "Check for Similar Past Patterns"}
          </button>
        </div>

        {trapWarnings.length > 0 && (
          <div className="mt-4 bg-yellow-50 border border-yellow-200 rounded-lg p-4">
            <h3 className="font-semibold text-yellow-800 mb-2">Trap Warnings</h3>
            <ul className="list-disc list-inside space-y-1">
              {trapWarnings.map((w, i) => (
                <li key={i} className="text-sm text-yellow-700">{w}</li>
              ))}
            </ul>
          </div>
        )}
      </div>

      {/* P&L Chart */}
      {snapshots.length > 0 && (
        <div className="bg-white border border-slate-200 rounded-xl p-6">
          <h2 className="font-semibold text-slate-800 mb-4">P&L History</h2>
          <PnLChart snapshots={snapshots} />
        </div>
      )}

      {/* Reasoning */}
      <div className="bg-white border border-slate-200 rounded-xl p-6">
        <h2 className="font-semibold text-slate-800 mb-3">Reasoning</h2>
        <pre className="text-sm text-slate-600 whitespace-pre-wrap leading-relaxed">
          {thesis.reasoning}
        </pre>
      </div>

      {/* Technical summary */}
      {thesis.state_snapshot?.technical_analysis && (
        <TechnicalSummary analysis={thesis.state_snapshot.technical_analysis} />
      )}

      {/* System Score */}
      {thesis.system_score && (
        <div className="bg-white border border-slate-200 rounded-xl p-6">
          <h2 className="font-semibold text-slate-800 mb-4">System Score</h2>
          <div className="grid grid-cols-2 sm:grid-cols-3 gap-4 text-sm">
            <div>
              <div className="text-xs text-slate-400">Profitable at Close</div>
              <div className={thesis.system_score.profitable_at_close_date ? "text-green-600 font-semibold" : "text-red-600 font-semibold"}>
                {thesis.system_score.profitable_at_close_date ? "Yes" : "No"}
              </div>
            </div>
            <div>
              <div className="text-xs text-slate-400">Hit Profit Target</div>
              <div className={thesis.system_score.hit_profit_target ? "text-green-600 font-semibold" : "text-slate-600"}>
                {thesis.system_score.hit_profit_target ? "Yes" : "No"}
              </div>
            </div>
            <div>
              <div className="text-xs text-slate-400">Days to Target</div>
              <div>{thesis.system_score.days_to_profit_target ?? "—"}</div>
            </div>
            <div>
              <div className="text-xs text-slate-400">Max Favorable</div>
              <div className="text-green-600">${thesis.system_score.max_favorable_excursion.toFixed(2)}</div>
            </div>
            <div>
              <div className="text-xs text-slate-400">Max Adverse</div>
              <div className="text-red-600">${thesis.system_score.max_adverse_excursion.toFixed(2)}</div>
            </div>
            <div>
              <div className="text-xs text-slate-400">Final P&L</div>
              <div className={thesis.system_score.final_pnl >= 0 ? "text-green-600 font-semibold" : "text-red-600 font-semibold"}>
                ${thesis.system_score.final_pnl.toFixed(2)}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* User Score Form */}
      <ScoreForm
        thesisId={id}
        existingScore={thesis.user_score ?? null}
        onSaved={load}
      />
    </div>
  );
}
