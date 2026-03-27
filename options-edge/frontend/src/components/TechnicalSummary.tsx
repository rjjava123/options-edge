interface TechnicalAnalysis {
  rsi?: number;
  trend?: string;
  patterns?: string[];
  support_levels?: number[];
  resistance_levels?: number[];
  macd_signal?: string;
  vwap?: number;
  ema_20?: number;
  ema_50?: number;
}

interface Props {
  analysis: TechnicalAnalysis;
}

function rsiColor(rsi: number) {
  if (rsi >= 70) return "text-red-600";
  if (rsi <= 30) return "text-green-600";
  return "text-slate-700";
}

export default function TechnicalSummary({ analysis }: Props) {
  return (
    <div className="bg-white border border-slate-200 rounded-xl p-6">
      <h2 className="font-semibold text-slate-800 mb-4">Technical Summary</h2>

      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 text-sm mb-4">
        {analysis.rsi !== undefined && (
          <div>
            <div className="text-xs text-slate-400">RSI</div>
            <div className={`font-semibold text-lg ${rsiColor(analysis.rsi)}`}>
              {analysis.rsi.toFixed(1)}
            </div>
          </div>
        )}
        {analysis.trend && (
          <div>
            <div className="text-xs text-slate-400">Trend</div>
            <div className="font-medium capitalize">{analysis.trend}</div>
          </div>
        )}
        {analysis.macd_signal && (
          <div>
            <div className="text-xs text-slate-400">MACD</div>
            <div className="font-medium capitalize">{analysis.macd_signal}</div>
          </div>
        )}
        {analysis.vwap !== undefined && (
          <div>
            <div className="text-xs text-slate-400">VWAP</div>
            <div className="font-medium">${analysis.vwap.toFixed(2)}</div>
          </div>
        )}
        {analysis.ema_20 !== undefined && (
          <div>
            <div className="text-xs text-slate-400">EMA 20</div>
            <div className="font-medium">${analysis.ema_20.toFixed(2)}</div>
          </div>
        )}
        {analysis.ema_50 !== undefined && (
          <div>
            <div className="text-xs text-slate-400">EMA 50</div>
            <div className="font-medium">${analysis.ema_50.toFixed(2)}</div>
          </div>
        )}
      </div>

      {analysis.patterns && analysis.patterns.length > 0 && (
        <div className="mb-3">
          <div className="text-xs text-slate-400 mb-1">Detected Patterns</div>
          <div className="flex flex-wrap gap-2">
            {analysis.patterns.map((p) => (
              <span key={p} className="px-2 py-0.5 bg-indigo-50 text-indigo-700 rounded text-xs">
                {p}
              </span>
            ))}
          </div>
        </div>
      )}

      <div className="flex gap-8 text-sm">
        {analysis.support_levels && analysis.support_levels.length > 0 && (
          <div>
            <div className="text-xs text-slate-400 mb-1">Support</div>
            <div className="flex gap-2">
              {analysis.support_levels.map((l) => (
                <span key={l} className="text-green-600 font-medium">${l.toFixed(2)}</span>
              ))}
            </div>
          </div>
        )}
        {analysis.resistance_levels && analysis.resistance_levels.length > 0 && (
          <div>
            <div className="text-xs text-slate-400 mb-1">Resistance</div>
            <div className="flex gap-2">
              {analysis.resistance_levels.map((l) => (
                <span key={l} className="text-red-600 font-medium">${l.toFixed(2)}</span>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
