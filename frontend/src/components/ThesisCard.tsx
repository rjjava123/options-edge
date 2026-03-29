import Link from "next/link";
import type { Thesis } from "@/lib/api";

const directionColor: Record<string, string> = {
  bullish: "bg-green-100 text-green-700",
  bearish: "bg-red-100 text-red-700",
  neutral: "bg-slate-100 text-slate-600",
};

interface Props {
  thesis: Thesis;
  detailed?: boolean;
}

export default function ThesisCard({ thesis, detailed }: Props) {
  return (
    <div className="bg-white border border-slate-200 rounded-xl p-5 hover:shadow-md transition-shadow">
      <div className="flex items-start justify-between mb-3">
        <div className="flex items-center gap-2">
          <span className="text-2xl font-bold font-mono text-slate-900">{thesis.ticker}</span>
          <span className={`px-2 py-0.5 rounded text-xs font-medium ${directionColor[thesis.direction] ?? "bg-slate-100 text-slate-600"}`}>
            {thesis.direction}
          </span>
        </div>
        <div className="text-right">
          <div className="text-lg font-bold text-slate-900">
            {Math.round(thesis.confidence * 100)}%
          </div>
          <div className="text-xs text-slate-400">confidence</div>
        </div>
      </div>

      <div className="text-sm text-slate-600 mb-3">
        <span className="font-medium">{thesis.spread_type}</span>
        {thesis.expiration_date && (
          <>
            {" · "}
            <span>Exp {thesis.expiration_date}</span>
          </>
        )}
      </div>

      <div className="flex flex-wrap gap-1 mb-3">
        {thesis.setup_classifications?.map((c) => (
          <span key={c} className="px-1.5 py-0.5 bg-purple-50 text-purple-600 rounded text-xs">
            {c}
          </span>
        ))}
      </div>

      {(thesis.entry_price != null || thesis.max_profit != null || thesis.max_loss != null) && (
        <div className="grid grid-cols-3 gap-2 text-sm mb-4">
          <div>
            <div className="text-xs text-slate-400">Entry</div>
            <div className="font-medium">
              {thesis.entry_price != null ? `$${thesis.entry_price.toFixed(2)}` : "—"}
            </div>
          </div>
          <div>
            <div className="text-xs text-slate-400">Max Profit</div>
            <div className="font-medium text-green-600">
              {thesis.max_profit != null ? `$${thesis.max_profit.toFixed(2)}` : "—"}
            </div>
          </div>
          <div>
            <div className="text-xs text-slate-400">Max Loss</div>
            <div className="font-medium text-red-600">
              {thesis.max_loss != null ? `$${thesis.max_loss.toFixed(2)}` : "—"}
            </div>
          </div>
        </div>
      )}

      {detailed && (
        <div className="text-sm text-slate-600 mb-4 line-clamp-4">
          {thesis.reasoning}
        </div>
      )}

      <div className="flex items-center justify-between">
        <span className="text-xs text-slate-400">
          {new Date(thesis.created_at).toLocaleDateString()}
        </span>
        <Link
          href={`/thesis/${thesis.id}`}
          className="text-xs text-blue-600 hover:underline font-medium"
        >
          View detail →
        </Link>
      </div>
    </div>
  );
}
