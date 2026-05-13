import { useEffect, useState } from "react";
import { api, type Run } from "./api/client";
import RunList from "./components/RunList";
import TraceWaterfall from "./components/TraceWaterfall";
import CostChart from "./components/CostChart";
import LatencyHeatmap from "./components/LatencyHeatmap";
import PromptDiff from "./components/PromptDiff";
import AlertFeed from "./components/AlertFeed";
import RegressionView from "./components/RegressionView";
import Overview from "./components/Overview";

// ── Sidebar icons ─────────────────────────────────────────────────────────────

const svgProps = {
  viewBox: "0 0 24 24",
  fill: "none",
  stroke: "currentColor",
  strokeWidth: 2,
  strokeLinecap: "round" as const,
  strokeLinejoin: "round" as const,
  className: "w-4 h-4 shrink-0",
};

const IcoGrid = () => (
  <svg {...svgProps}>
    <rect x="3" y="3" width="7" height="7" />
    <rect x="14" y="3" width="7" height="7" />
    <rect x="3" y="14" width="7" height="7" />
    <rect x="14" y="14" width="7" height="7" />
  </svg>
);

const IcoList = () => (
  <svg {...svgProps}>
    <line x1="8" y1="6" x2="21" y2="6" />
    <line x1="8" y1="12" x2="21" y2="12" />
    <line x1="8" y1="18" x2="21" y2="18" />
    <line x1="3" y1="6" x2="3.01" y2="6" />
    <line x1="3" y1="12" x2="3.01" y2="12" />
    <line x1="3" y1="18" x2="3.01" y2="18" />
  </svg>
);

const IcoDollar = () => (
  <svg {...svgProps}>
    <line x1="12" y1="1" x2="12" y2="23" />
    <path d="M17 5H9.5a3.5 3.5 0 000 7h5a3.5 3.5 0 010 7H6" />
  </svg>
);

const IcoClock = () => (
  <svg {...svgProps}>
    <circle cx="12" cy="12" r="10" />
    <polyline points="12 6 12 12 16 14" />
  </svg>
);

const IcoColumns = () => (
  <svg {...svgProps}>
    <rect x="3" y="3" width="8" height="18" rx="1" />
    <rect x="13" y="3" width="8" height="18" rx="1" />
  </svg>
);

const IcoBell = () => (
  <svg {...svgProps}>
    <path d="M18 8A6 6 0 006 8c0 7-3 9-3 9h18s-3-2-3-9" />
    <path d="M13.73 21a2 2 0 01-3.46 0" />
  </svg>
);

const IcoTrend = () => (
  <svg {...svgProps}>
    <polyline points="22 7 13.5 15.5 8.5 10.5 2 17" />
    <polyline points="16 7 22 7 22 13" />
  </svg>
);

// ── Nav definition ────────────────────────────────────────────────────────────

const NAV = [
  { id: "overview",   label: "Overview",  icon: <IcoGrid /> },
  { id: "runs",       label: "Runs",      icon: <IcoList /> },
  { id: "cost",       label: "Cost",      icon: <IcoDollar /> },
  { id: "heatmap",    label: "Latency",   icon: <IcoClock /> },
  { id: "diff",       label: "Diff",      icon: <IcoColumns /> },
  { id: "alerts",     label: "Alerts",    icon: <IcoBell /> },
  { id: "regression", label: "Trends",    icon: <IcoTrend /> },
] as const;

type View = typeof NAV[number]["id"];

// ── App ───────────────────────────────────────────────────────────────────────

export default function App() {
  const [view, setView]               = useState<View>("overview");
  const [selected, setSelected]       = useState<Run | null>(null);
  const [allRuns, setAllRuns]         = useState<Run[]>([]);
  const [globalService, setGlobalService] = useState("");
  const [services, setServices]       = useState<string[]>([]);

  // Fetch service list for the sidebar dropdown
  useEffect(() => {
    api.runs.list({ limit: 100 }).then((d) => {
      const unique = Array.from(new Set(d.items.map((r) => r.service_name))).sort();
      setServices(unique);
    }).catch(console.error);
  }, []);

  // Fetch top-20 runs for heatmap / diff; refetch when globalService changes
  useEffect(() => {
    api.runs
      .list({ limit: 20, service_name: globalService || undefined })
      .then((d) => setAllRuns(d.items))
      .catch(console.error);
  }, [globalService]);

  return (
    <div className="flex h-screen overflow-hidden bg-gray-950 text-gray-100">
      {/* Sidebar */}
      <aside className="w-52 shrink-0 bg-gray-900 border-r border-gray-800 flex flex-col">
        {/* Branding */}
        <div className="px-4 pt-5 pb-4 border-b border-gray-800">
          <div className="text-indigo-400 font-bold text-lg tracking-wide">Tracely</div>
          <div className="text-gray-600 text-xs mt-0.5">LLM Observability</div>
        </div>

        {/* Nav */}
        <nav className="flex-1 flex flex-col gap-0.5 p-2 overflow-y-auto">
          {NAV.map((n) => (
            <button
              key={n.id}
              onClick={() => setView(n.id)}
              className={`flex items-center gap-2.5 px-3 py-2 rounded text-sm transition-all text-left w-full ${
                view === n.id
                  ? "border-l-[3px] border-indigo-500 bg-indigo-900/30 text-indigo-300 pl-[9px]"
                  : "border-l-[3px] border-transparent text-gray-400 hover:bg-gray-800/50 hover:text-gray-200"
              }`}
            >
              {n.icon}
              {n.label}
            </button>
          ))}
        </nav>

        {/* Global service filter */}
        <div className="p-3 border-t border-gray-800">
          <div className="text-gray-500 text-xs mb-1.5 font-medium uppercase tracking-wider">Service</div>
          <select
            value={globalService}
            onChange={(e) => setGlobalService(e.target.value)}
            className="w-full bg-gray-800 border border-gray-700 text-gray-300 text-xs rounded px-2 py-1.5 focus:outline-none focus:border-indigo-500"
          >
            <option value="">All services</option>
            {services.map((s) => (
              <option key={s} value={s}>{s}</option>
            ))}
          </select>
        </div>
      </aside>

      {/* Main */}
      <main className="flex-1 flex overflow-hidden">
        {view === "runs" ? (
          <>
            {/* Run list panel */}
            <section className="w-[42%] border-r border-gray-800 flex flex-col overflow-hidden">
              <div className="px-4 py-3 border-b border-gray-800 flex items-center gap-2">
                <IcoList />
                <span className="text-gray-200 text-sm font-semibold">Runs</span>
              </div>
              <div className="flex-1 overflow-y-auto p-3">
                <RunList
                  onSelect={(run) => setSelected(run)}
                  selectedId={selected?.id ?? null}
                  serviceFilter={globalService}
                />
              </div>
            </section>

            {/* Detail panel */}
            <section className="flex-1 flex flex-col overflow-hidden">
              <div className="px-4 py-3 border-b border-gray-800">
                <div className="text-gray-400 text-xs">
                  {selected ? (
                    <>
                      <span className="text-indigo-300">{selected.service_name}</span>
                      {" · "}
                      {selected.id.slice(0, 16)}…
                      {" · "}
                      <span className="text-gray-500">{selected.model ?? "no model"}</span>
                    </>
                  ) : (
                    <span className="text-gray-600">Select a run to inspect its trace</span>
                  )}
                </div>
              </div>
              <div className="flex-1 overflow-y-auto p-4">
                {selected ? (
                  <TraceWaterfall runId={selected.id} />
                ) : (
                  <div className="flex flex-col items-center justify-center h-full gap-3 text-gray-600">
                    <IcoList />
                    <span className="text-sm">No run selected</span>
                  </div>
                )}
              </div>
            </section>
          </>
        ) : (
          <section className="flex-1 flex flex-col overflow-hidden">
            {/* Content header */}
            <div className="px-5 py-3.5 border-b border-gray-800 flex items-center gap-2.5">
              {NAV.find((n) => n.id === view)?.icon}
              <span className="text-gray-200 text-sm font-semibold">
                {NAV.find((n) => n.id === view)?.label}
              </span>
            </div>

            {/* Content body */}
            <div className="flex-1 overflow-y-auto p-5">
              {view === "overview"   && <Overview onNavigate={setView} serviceFilter={globalService} />}
              {view === "cost"       && <CostChart serviceFilter={globalService} />}
              {view === "heatmap"    && <LatencyHeatmap runs={allRuns} />}
              {view === "diff"       && <PromptDiff runs={allRuns} />}
              {view === "alerts"     && <AlertFeed />}
              {view === "regression" && <RegressionView serviceFilter={globalService} />}
            </div>
          </section>
        )}
      </main>
    </div>
  );
}
