"use client";

import Link from "next/link";
import type { WatchlistItem, NewsContext } from "@/lib/api";

interface Props {
  item: WatchlistItem;
  news?: NewsContext;
  loadingNews: boolean;
  onRemove: () => void;
  onRefreshNews: () => void;
}

export default function WatchlistTicker({ item, news, loadingNews, onRemove, onRefreshNews }: Props) {
  return (
    <div className="bg-white border border-slate-200 rounded-xl p-5">
      <div className="flex items-start justify-between mb-3">
        <div className="flex items-center gap-3">
          <span className="text-xl font-bold font-mono text-slate-900">{item.ticker}</span>
          {item.notes && (
            <span className="text-sm text-slate-400 italic">{item.notes}</span>
          )}
        </div>
        <div className="flex gap-2">
          <button
            onClick={onRefreshNews}
            disabled={loadingNews}
            className="px-3 py-1 bg-slate-100 text-slate-600 rounded-lg text-xs hover:bg-slate-200 disabled:opacity-50 transition-colors"
          >
            {loadingNews ? "Loading..." : "Refresh News"}
          </button>
          <Link
            href={`/validate?ticker=${item.ticker}`}
            className="px-3 py-1 bg-blue-50 text-blue-700 rounded-lg text-xs hover:bg-blue-100 transition-colors"
          >
            Run Analysis
          </Link>
          <button
            onClick={onRemove}
            className="px-3 py-1 bg-red-50 text-red-600 rounded-lg text-xs hover:bg-red-100 transition-colors"
          >
            Remove
          </button>
        </div>
      </div>

      {news && (
        <div className="mt-3 space-y-3">
          {news.narrative && (
            <div className="bg-blue-50 border border-blue-100 rounded-lg p-3 text-sm text-slate-700 leading-relaxed">
              <span className="font-semibold text-blue-700 text-xs uppercase tracking-wide block mb-1">
                AI Summary
              </span>
              {news.narrative}
            </div>
          )}

          {news.headlines && news.headlines.length > 0 && (
            <div>
              <div className="text-xs font-medium text-slate-400 uppercase tracking-wide mb-2">
                Recent Headlines
              </div>
              <ul className="space-y-1.5">
                {news.headlines.slice(0, 5).map((h, i) => (
                  <li key={i} className="flex items-start gap-2 text-sm">
                    <span className="text-slate-300 mt-0.5">•</span>
                    <div>
                      <a
                        href={h.url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-slate-700 hover:text-blue-600 hover:underline"
                      >
                        {h.title}
                      </a>
                      <span className="text-xs text-slate-400 ml-2">
                        {new Date(h.published).toLocaleDateString()}
                      </span>
                    </div>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}

      {!news && !loadingNews && (
        <div className="text-xs text-slate-400 mt-2">
          Click Refresh News to load headlines and AI summary.
        </div>
      )}
    </div>
  );
}
