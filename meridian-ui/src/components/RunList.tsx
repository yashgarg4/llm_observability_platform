import { useEffect, useState } from "react";
import { api, type Run } from "../api/client";

interface Props {
  onSelect: (run: Run) => void;
  selectedId: string | null;
  serviceFilter?: string;
}

export default function RunList({ onSelect, selectedId, serviceFilter = "" }: Props) {
  const [runs, setRuns]       = useState<Run[]>([]);
  const [total, setTotal]     = useState(0);
  const [page, setPage]       = useState(0);
  const [service, setService] = useState(serviceFilter);
  const [model, setModel]     = useState("");
  const [loading, setLoading] = useState(false);
  const limit = 20;

  // When the sidebar service filter changes, sync local service state and reset page
  useEffect(() => {
    setService(serviceFilter);
    setPage(0);
  }, [serviceFilter]);

  useEffect(() => {
    setLoading(true);
    api.runs
      .list({
        limit,
        offset: page * limit,
        service_name: service || undefined,
        model: model || undefined,
      })
      .then((d) => {
        setRuns(d.items);
        setTotal(d.total);
      })
      .catch(console.error)
      .finally(() => setLoading(false));
  }, [page, service, model]);

  const pages = Math.ceil(total / limit);

  return (
    <div className="flex flex-col gap-3">
      {/* Filters — model only; service comes from sidebar */}
      <div className="flex gap-2">
        <input
          className="flex-1 bg-gray-800 border border-gray-700 rounded px-2 py-1 text-xs placeholder-gray-500 focus:outline-none focus:border-indigo-500"
          placeholder="Filter by model…"
          value={model}
          onChange={(e) => { setModel(e.target.value); setPage(0); }}
        />
        <button
          className="bg-gray-700 hover:bg-gray-600 rounded px-2 py-1 text-xs transition-colors"
          onClick={() => { setModel(""); setPage(0); }}
        >
          Clear
        </button>
      </div>

      {/* Run rows */}
      {loading ? (
        <div className="text-gray-500 text-xs py-4 text-center">Loading…</div>
      ) : runs.length === 0 ? (
        <div className="text-gray-500 text-xs py-4 text-center">
          No runs yet. Run the demo to see traces.
        </div>
      ) : (
        <div className="flex flex-col">
          {runs.map((r) => (
            <div
              key={r.id}
              className={`flex items-center gap-3 px-3 py-2.5 cursor-pointer border-l-2 transition-all ${
                r.id === selectedId
                  ? "border-indigo-500 bg-indigo-900/20"
                  : `border-transparent ${
                      r.status === "ok"
                        ? "hover:border-emerald-600"
                        : "hover:border-red-600"
                    } hover:bg-gray-800/40`
              }`}
              onClick={() => onSelect(r)}
            >
              {/* Status dot */}
              <div
                className={`w-2 h-2 rounded-full shrink-0 mt-0.5 ${
                  r.status === "ok" ? "bg-emerald-400" : "bg-red-400"
                }`}
              />

              {/* Main content */}
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-1.5 mb-0.5">
                  <span className="text-indigo-300 text-xs font-medium truncate">
                    {r.service_name}
                  </span>
                  {r.model && (
                    <span className="text-gray-500 text-[10px] bg-gray-800 rounded px-1 py-0.5 shrink-0">
                      {r.model.split("/").pop()}
                    </span>
                  )}
                </div>
                <div className="flex items-center gap-2 text-[10px] text-gray-500">
                  <span>
                    {new Date(r.start_time * 1000).toLocaleString([], {
                      month: "short",
                      day: "numeric",
                      hour: "2-digit",
                      minute: "2-digit",
                    })}
                  </span>
                  {r.end_time && (
                    <span>· {(r.end_time - r.start_time).toFixed(1)}s</span>
                  )}
                  {r.total_tokens > 0 && (
                    <span>· {r.total_tokens.toLocaleString()} tok</span>
                  )}
                </div>
              </div>

              {/* Cost */}
              <div className="text-right shrink-0">
                {r.total_cost_usd > 0 ? (
                  <span className="text-emerald-400 text-[10px] font-mono">
                    ${r.total_cost_usd.toFixed(5)}
                  </span>
                ) : (
                  <span className="text-gray-700 text-[10px]">—</span>
                )}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Pagination */}
      {pages > 1 && (
        <div className="flex justify-end gap-2 text-xs">
          <button
            disabled={page === 0}
            onClick={() => setPage((p) => p - 1)}
            className="px-2 py-1 bg-gray-700 hover:bg-gray-600 disabled:opacity-40 rounded"
          >
            ← Prev
          </button>
          <span className="py-1 text-gray-400">
            {page + 1} / {pages}
          </span>
          <button
            disabled={page >= pages - 1}
            onClick={() => setPage((p) => p + 1)}
            className="px-2 py-1 bg-gray-700 hover:bg-gray-600 disabled:opacity-40 rounded"
          >
            Next →
          </button>
        </div>
      )}
    </div>
  );
}
