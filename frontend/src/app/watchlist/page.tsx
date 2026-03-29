"use client";

import { useEffect, useState } from "react";
import { watchlistApi, type WatchlistItem, type NewsContext } from "@/lib/api";
import WatchlistTicker from "@/components/WatchlistTicker";

export default function WatchlistPage() {
  const [items, setItems] = useState<WatchlistItem[]>([]);
  const [ticker, setTicker] = useState("");
  const [notes, setNotes] = useState("");
  const [loading, setLoading] = useState(true);
  const [news, setNews] = useState<Record<string, NewsContext>>({});
  const [loadingNews, setLoadingNews] = useState<Record<string, boolean>>({});

  async function load() {
    setLoading(true);
    try {
      const data = await watchlistApi.list();
      setItems(data);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { load(); }, []);

  async function addTicker() {
    const t = ticker.trim().toUpperCase();
    if (!t) return;
    await watchlistApi.add(t, notes || undefined);
    setTicker("");
    setNotes("");
    await load();
  }

  async function remove(item: WatchlistItem) {
    await watchlistApi.remove(item.ticker);
    setItems((prev) => prev.filter((i) => i.id !== item.id));
  }

  async function fetchNews(ticker: string) {
    setLoadingNews((prev) => ({ ...prev, [ticker]: true }));
    try {
      const data = await watchlistApi.refreshNews(ticker);
      setNews((prev) => ({ ...prev, [ticker]: data }));
    } finally {
      setLoadingNews((prev) => ({ ...prev, [ticker]: false }));
    }
  }

  async function refreshAll() {
    for (const item of items) {
      await fetchNews(item.ticker);
    }
  }

  return (
    <div className="max-w-4xl">
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-bold text-slate-900">Watchlist & News</h1>
        <button
          onClick={refreshAll}
          className="px-3 py-1.5 bg-slate-100 text-slate-700 rounded-lg text-sm hover:bg-slate-200 transition-colors"
        >
          Refresh All
        </button>
      </div>

      {/* Add ticker */}
      <div className="flex gap-3 mb-8 bg-white border border-slate-200 rounded-xl p-4">
        <input
          type="text"
          placeholder="Ticker (e.g. TSLA)"
          value={ticker}
          onChange={(e) => setTicker(e.target.value.toUpperCase())}
          className="border border-slate-300 rounded px-3 py-1.5 text-sm w-32 font-mono uppercase"
          maxLength={10}
        />
        <input
          type="text"
          placeholder="Notes (optional)"
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
          className="border border-slate-300 rounded px-3 py-1.5 text-sm flex-1"
        />
        <button
          onClick={addTicker}
          disabled={!ticker.trim()}
          className="px-4 py-1.5 bg-blue-600 text-white rounded-lg text-sm font-medium hover:bg-blue-700 disabled:opacity-50 transition-colors"
        >
          Add
        </button>
      </div>

      {loading ? (
        <div className="text-center py-16 text-slate-400">Loading...</div>
      ) : items.length === 0 ? (
        <div className="text-center py-16 text-slate-400">No tickers yet. Add one above.</div>
      ) : (
        <div className="space-y-4">
          {items.map((item) => (
            <WatchlistTicker
              key={item.id}
              item={item}
              news={news[item.ticker]}
              loadingNews={loadingNews[item.ticker] ?? false}
              onRemove={() => remove(item)}
              onRefreshNews={() => fetchNews(item.ticker)}
            />
          ))}
        </div>
      )}
    </div>
  );
}
