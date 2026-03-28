interface OptionContract {
  strike: number;
  expiration: string;
  call_bid?: number;
  call_ask?: number;
  call_iv?: number;
  call_delta?: number;
  call_oi?: number;
  put_bid?: number;
  put_ask?: number;
  put_iv?: number;
  put_delta?: number;
  put_oi?: number;
}

interface Props {
  contracts: OptionContract[];
  underlyingPrice?: number;
}

export default function OptionsChainView({ contracts, underlyingPrice }: Props) {
  if (!contracts || contracts.length === 0) return null;

  return (
    <div className="bg-white border border-slate-200 rounded-xl p-6 overflow-x-auto">
      <h2 className="font-semibold text-slate-800 mb-4">Options Chain</h2>
      <table className="w-full text-xs">
        <thead>
          <tr className="bg-slate-50">
            <th colSpan={5} className="px-3 py-2 text-center text-slate-500 font-medium border-r">
              CALLS
            </th>
            <th className="px-3 py-2 text-center font-bold text-slate-900">Strike</th>
            <th colSpan={5} className="px-3 py-2 text-center text-slate-500 font-medium border-l">
              PUTS
            </th>
          </tr>
          <tr className="bg-slate-50 text-slate-400">
            <th className="px-2 py-1 text-right">OI</th>
            <th className="px-2 py-1 text-right">IV</th>
            <th className="px-2 py-1 text-right">Delta</th>
            <th className="px-2 py-1 text-right">Bid</th>
            <th className="px-2 py-1 text-right border-r">Ask</th>
            <th className="px-3 py-1 text-center font-semibold text-slate-700">—</th>
            <th className="px-2 py-1 text-right border-l">Bid</th>
            <th className="px-2 py-1 text-right">Ask</th>
            <th className="px-2 py-1 text-right">Delta</th>
            <th className="px-2 py-1 text-right">IV</th>
            <th className="px-2 py-1 text-right">OI</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-50">
          {contracts.map((c) => {
            const atm = underlyingPrice !== undefined && Math.abs(c.strike - underlyingPrice) < 1;
            return (
              <tr
                key={`${c.strike}-${c.expiration}`}
                className={atm ? "bg-blue-50 font-semibold" : "hover:bg-slate-50"}
              >
                <td className="px-2 py-1.5 text-right">{c.call_oi?.toLocaleString() ?? "—"}</td>
                <td className="px-2 py-1.5 text-right">{c.call_iv !== undefined ? `${(c.call_iv * 100).toFixed(0)}%` : "—"}</td>
                <td className="px-2 py-1.5 text-right">{c.call_delta?.toFixed(2) ?? "—"}</td>
                <td className="px-2 py-1.5 text-right">{c.call_bid?.toFixed(2) ?? "—"}</td>
                <td className="px-2 py-1.5 text-right border-r">{c.call_ask?.toFixed(2) ?? "—"}</td>
                <td className="px-3 py-1.5 text-center font-bold text-slate-800">${c.strike}</td>
                <td className="px-2 py-1.5 text-right border-l">{c.put_bid?.toFixed(2) ?? "—"}</td>
                <td className="px-2 py-1.5 text-right">{c.put_ask?.toFixed(2) ?? "—"}</td>
                <td className="px-2 py-1.5 text-right">{c.put_delta?.toFixed(2) ?? "—"}</td>
                <td className="px-2 py-1.5 text-right">{c.put_iv !== undefined ? `${(c.put_iv * 100).toFixed(0)}%` : "—"}</td>
                <td className="px-2 py-1.5 text-right">{c.put_oi?.toLocaleString() ?? "—"}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
