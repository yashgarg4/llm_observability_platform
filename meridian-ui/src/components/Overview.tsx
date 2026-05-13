import { useEffect, useState } from "react";
import { api, type Run, type Alert } from "../api/client";

interface Props {
  onNavigate: (view: string) => void;
  serviceFilter?: string;
}

function KpiCard({ label, value, color }: { label: string; value: string | number; color: string }) {
  return (
    <div className="bg-gray-800/50 rounded-xl p-4 border border-gray-700/50">
      <div className="text-gray-500 text-xs uppercase tracking-wider mb-2">{label}</div>
      <div className={`text-2xl font-bold font-mono ${color}`}>{value}</div>
    </div>
  );
}

export default function Overview({ onNavigate, serviceFilter = "" }: Props) {
  const [runs, setRuns]       = useState<Run[]>([]);
  const [totalRuns, setTotalRuns] = useState(0);
  const [alerts, setAlerts]   = useState<Alert[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    Promise.all([
      api.runs.list({ limit: 50, service_name: serviceFilter || undefined }),
      api.alerts.list({ limit: 100 }),
    ])
      .then(([runsData, alertsData]) => {
        setRuns(runsData.items);
        setTotalRuns(runsData.total);
        setAlerts(alertsData);
      })
      .catch(console.error)
      .finally(() => setLoading(false));
  }, [serviceFilter]);

  const totalCost = runs.reduce((sum, r) => sum + (r.total_cost_usd ?? 0), 0);

  const latencies = runs
    .filter((r) => r.end_time != null)
    .map((r) => (r.end_time! - r.start_time) * 1000);
  const avgLatency =
    latencies.length > 0
      ? latencies.reduce((s, v) => s + v, 0) / latencies.length
      : 0;

  const alertCount = alerts.length;
  const recentRuns = runs.slice(0, 5);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-40 text-gray-500 text-sm">
        Loading…
      </div>
    );
  }

  return (
    <div>
      {/* KPI cards */}
      <div className="grid grid-cols-2 xl:grid-cols-4 gap-4 mb-6">
        <KpiCard label="Total Runs"   value={totalRuns}  color="text-indigo-400" />
        <KpiCard label="Total Cost"   value={`$${totalCost.toFixed(5)}`} color="text-emerald-400" />
        <KpiCard
          label="Avg Latency"
          value={
            avgLatency > 1000
              ? `${(avgLatency / 1000).toFixed(1)}s`
              : `${avgLatency.toFixed(0)}ms`
          }
          color="text-amber-400"
        />
        <KpiCard
          label="Alerts Fired"
          value={alertCount}
          color={alertCount > 0 ? "text-red-400" : "text-gray-400"}
        />
      </div>

      {/* Recent runs */}
      <div className="bg-gray-800/30 rounded-xl border border-gray-700/50 overflow-hidden">
        <div className="px-4 py-2.5 border-b border-gray-700/50 text-xs font-semibold text-gray-400 uppercase tracking-wider">
          Recent Runs
        </div>

        {/* Column headers */}
        <div className="flex items-center gap-3 px-4 py-1.5 border-b border-gray-700/30 bg-gray-800/40">
          <div className="w-1.5 shrink-0" />
          <div className="flex-1 text-[10px] font-semibold text-gray-500 uppercase tracking-wider">Service / Model</div>
          <div className="text-[10px] font-semibold text-gray-500 uppercase tracking-wider shrink-0 w-12 text-right">Duration</div>
          <div className="text-[10px] font-semibold text-gray-500 uppercase tracking-wider shrink-0 w-16 text-right">Cost</div>
          <div className="text-[10px] font-semibold text-gray-500 uppercase tracking-wider shrink-0 w-10 text-right">Time</div>
        </div>

        {recentRuns.length === 0 ? (
          <div className="px-4 py-6 text-gray-600 text-xs text-center">
            No runs yet — run a query to see traces here.
          </div>
        ) : (
          recentRuns.map((r) => (
            <div
              key={r.id}
              className="flex items-center gap-3 px-4 py-2.5 border-b border-gray-800/50 last:border-0 hover:bg-gray-800/40 transition-colors"
            >
              {/* Status dot */}
              <div
                className={`w-1.5 h-1.5 rounded-full shrink-0 ${
                  r.status === "ok" ? "bg-emerald-400" : "bg-red-400"
                }`}
              />

              {/* Service + model */}
              <div className="flex-1 min-w-0">
                <span className="text-indigo-300 text-xs font-medium">{r.service_name}</span>
                <span className="text-gray-600 text-xs mx-1.5">·</span>
                <span className="text-gray-500 text-xs">{r.model?.split("/").pop() ?? "—"}</span>
              </div>

              {/* Duration */}
              <div className="text-gray-400 text-xs shrink-0 w-12 text-right">
                {r.end_time ? `${(r.end_time - r.start_time).toFixed(1)}s` : "—"}
              </div>

              {/* Cost */}
              <div className="text-xs shrink-0 w-16 text-right font-mono">
                {r.total_cost_usd > 0
                  ? <span className="text-emerald-400">${r.total_cost_usd.toFixed(5)}</span>
                  : <span className="text-gray-700">—</span>
                }
              </div>

              {/* Time */}
              <div className="text-gray-600 text-xs shrink-0 w-10 text-right">
                {new Date(r.start_time * 1000).toLocaleTimeString([], {
                  hour: "2-digit",
                  minute: "2-digit",
                })}
              </div>
            </div>
          ))
        )}

        {/* View all link */}
        <div className="px-4 py-2 border-t border-gray-700/50 flex justify-end">
          <button
            onClick={() => onNavigate("runs")}
            className="text-indigo-400 hover:text-indigo-300 text-xs transition-colors"
          >
            View all →
          </button>
        </div>
      </div>
    </div>
  );
}
