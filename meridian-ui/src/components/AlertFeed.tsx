import { useEffect, useState } from "react";
import { api, type Alert } from "../api/client";
import { useAlerts } from "../api/websocket";

const SEVERITY_STYLE: Record<string, string> = {
  error:   "bg-red-900/60 text-red-300 border border-red-700",
  warning: "bg-amber-900/60 text-amber-300 border border-amber-700",
  info:    "bg-blue-900/60 text-blue-300 border border-blue-700",
};

function fmt(ts: number): string {
  return new Date(ts * 1000).toLocaleTimeString();
}

export default function AlertFeed() {
  const wsAlerts = useAlerts(50);
  const [historic, setHistoric] = useState<Alert[]>([]);
  const [hasNew, setHasNew]     = useState(false);

  useEffect(() => {
    api.alerts.list({ limit: 50 }).then(setHistoric).catch(console.error);
  }, []);

  useEffect(() => {
    if (wsAlerts.length > 0) setHasNew(true);
    const t = setTimeout(() => setHasNew(false), 3000);
    return () => clearTimeout(t);
  }, [wsAlerts]);

  const all: Alert[] = [
    ...wsAlerts,
    ...historic.filter((h) => !wsAlerts.some((w) => w.id === h.id)),
  ].slice(0, 50);

  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-center gap-2">
        <span className="text-gray-300 text-sm font-semibold">Alert Feed</span>
        {hasNew && (
          <span className="relative flex h-2.5 w-2.5">
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-red-400 opacity-75" />
            <span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-red-500" />
          </span>
        )}
        <span className="text-gray-500 text-xs ml-auto">{all.length} alert{all.length !== 1 ? "s" : ""}</span>
      </div>

      {all.length === 0 && (
        <div className="text-gray-500 text-xs py-4 text-center">No alerts. System healthy.</div>
      )}

      <div className="flex flex-col gap-1.5 overflow-y-auto max-h-[480px]">
        {all.map((a) => (
          <div key={a.id} className={`rounded p-2 text-xs ${SEVERITY_STYLE[a.severity] ?? SEVERITY_STYLE.info}`}>
            <div className="flex items-center justify-between gap-2 mb-0.5">
              <span className="font-semibold uppercase tracking-wide text-[10px]">{a.rule_name}</span>
              <span className="text-gray-400 shrink-0">{fmt(a.fired_at)}</span>
            </div>
            <div className="text-gray-200">{a.message}</div>
            <div className="text-gray-500 mt-0.5 truncate">run: {a.run_id.slice(0, 16)}…</div>
          </div>
        ))}
      </div>
    </div>
  );
}
