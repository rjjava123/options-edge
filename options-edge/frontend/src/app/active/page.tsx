"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { activeTradesApi, type Thesis } from "@/lib/api";

function pnlColor(pnl: number) {
  if (pnl > 0) return "text-green-600";
  if (pnl < 0) return "text-red-600";
  return "text-slate-600";
}

export default function ActiveTradesPage() {
  const [trades, setTrades] = useState<Thesis[]>([]);
  const [loading, setLoading] = useState(true);

  async function load() {
    setLoading(true);
    try {
      const data = await activeTradesApi.list();
      setTrades(data);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { load(); }, []);

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-bold text-slate-900">Active Trades</h1>
        <button
          onClick={load}
          className="px-3 py-1.5 bg-slate-100 text-slate-700 rounded-lg text-sm hover:bg-slate-200 transition-colors"
        >
          Refresh
        </button>
      </div>

      {loading ? (
        <div className="text-center py-16 text-slate-400">Loading...</div>
      ) : trades.length === 0 ? (
        <div className="text-center py-16 text-slate-400">
          No active trades. Mark a thesis as Active from the History or detail page.
        </div>
      ) : (
        <div className="space-y-4">
          {trades.map((t) => {
            const latest = t.daily_snapshots?.[t.daily_snapshots.length - 1];
            const expDays = t.expiration_date
              ? Math.ceil(
                  (new Date(t.expiration_date).getTime() - Date.now()) / (1000 * 60 * 60 * 24)
                )
              : null;

            return (
              <div key={t.id} className="bg-white border border-slate-200 rounded-xl p-5">
                <div className="flex items-start justify-between">
                  <div>
                    <div className="flex items-center gap-3">
                      <span className="text-xl font-bold font-mono text-slate-900">{t.ticker}</span>
                      <span className="text-sm text-slate-500 capitalize">{t.direction}</span>
                      <span className="text-sm text-slate-500">{t.spread_type}</span>
                    </div>
                    <div className="flex gap-6 mt-2 text-sm">
                      <span className="text-slate-500">
                        Exp: <span className="font-medium text-slate-700">{t.expiration_date}</span>
                        {expDays !== null && (
                          <span className={expDays <= 5 ? "text-red-600 ml-1 font-medium" : "text-slate-400 ml-1"}>
                            ({expDays}d)
                          </span>
                        )}
                      </span>
                      <span className="text-slate-500">
                        Entry: <span className="font-medium">${t.entry_price.toFixed(2)}</span>
                      </span>
                      <span className="text-slate-500">
                        Target: <span className="font-medium">{Math.round(t.profit_target * 100)}%</span>
                      </span>
                    </div>
                  </div>

                  {latest && (
                    <div className="text-right">
                      <div className={`text-2xl font-bold ${pnlColor(latest.pnl_dollars)}`}>
                        {latest.pnl_dollars >= 0 ? "+" : ""}${latest.pnl_dollars.toFixed(0)}
                      </div>
                      <div className={`text-sm ${pnlColor(latest.pnl_percent)}`}>
                        {latest.pnl_percent >= 0 ? "+" : ""}{(latest.pnl_percent * 100).toFixed(1)}%
                      </div>
                      <div className="text-xs text-slate-400 mt-0.5">
                        as of {latest.snapshot_date}
                      </div>
                    </div>
                  )}
                </div>

                <div className="mt-4 flex gap-3">
                  <Link
                    href={`/thesis/${t.id}`}
                    className="px-3 py-1.5 bg-blue-50 text-blue-700 rounded-lg text-xs font-medium hover:bg-blue-100 transition-colors"
                  >
                    View Detail →
                  </Link>
                  {latest?.exit_condition_met && (
                    <span className="px-3 py-1.5 bg-yellow-100 text-yellow-700 rounded-lg text-xs font-medium">
                      Exit: {latest.exit_condition_met}
                    </span>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
