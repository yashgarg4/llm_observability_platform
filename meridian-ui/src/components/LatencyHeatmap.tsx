import { useEffect, useState } from "react";
import { api, type Run, type Span } from "../api/client";

interface Props { runs: Run[] }

interface Cell {
  runLabel: string;
  node: string;
  latency: number;
}

function latencyColor(ms: number, max: number): string {
  if (max === 0) return "#1f2937";
  const ratio = Math.min(ms / max, 1);
  if (ratio < 0.33) return "#064e3b";
  if (ratio < 0.66) return "#78350f";
  return "#7f1d1d";
}

function flattenSpans(spans: Span[]): Span[] {
  return spans.flatMap((s) => [s, ...flattenSpans(s.children)]);
}

export default function LatencyHeatmap({ runs }: Props) {
  const [cells, setCells]   = useState<Cell[]>([]);
  const [nodeNames, setNodeNames] = useState<string[]>([]);
  const [runLabels, setRunLabels] = useState<string[]>([]);

  useEffect(() => {
    if (runs.length === 0) return;
    const recent = runs.slice(0, 8).reverse();

    Promise.all(recent.map((r) => api.runs.spans(r.id))).then((spanTrees) => {
      const allNodes = new Set<string>();
      const newCells: Cell[] = [];

      spanTrees.forEach((tree, i) => {
        const flat = flattenSpans(tree);
        const label = `${recent[i].service_name.slice(0, 10)} ${new Date(recent[i].start_time * 1000).toLocaleTimeString()}`;
        flat.forEach((s) => {
          if (s.name !== "langgraph.node") return;
          const node = String(s.attributes["node.name"] ?? s.name);
          allNodes.add(node);
          newCells.push({ runLabel: label, node, latency: s.latency_ms });
        });
      });

      setNodeNames(Array.from(allNodes));
      setRunLabels(recent.map((r) => `${r.service_name.slice(0, 10)} ${new Date(r.start_time * 1000).toLocaleTimeString()}`));
      setCells(newCells);
    }).catch(console.error);
  }, [runs]);

  if (cells.length === 0) {
    return <div className="text-gray-500 text-xs py-4 text-center">No latency data yet.</div>;
  }

  const maxLatency = Math.max(...cells.map((c) => c.latency), 1);
  const byKey = new Map(cells.map((c) => [`${c.runLabel}|${c.node}`, c.latency]));

  return (
    <div className="overflow-x-auto">
      <table className="text-xs border-separate border-spacing-0.5">
        <thead>
          <tr>
            <th className="text-left px-2 py-1 text-gray-400 w-36">Run</th>
            {nodeNames.map((n) => (
              <th key={n} className="text-center px-2 py-1 text-gray-400 whitespace-nowrap">{n}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {runLabels.map((label) => (
            <tr key={label}>
              <td className="px-2 py-1 text-gray-400 text-xs truncate max-w-[144px]">{label}</td>
              {nodeNames.map((n) => {
                const lat = byKey.get(`${label}|${n}`);
                return (
                  <td
                    key={n}
                    className="text-center px-2 py-1 rounded font-mono"
                    style={{ background: lat != null ? latencyColor(lat, maxLatency) : "#111827" }}
                    title={lat != null ? `${lat.toFixed(1)} ms` : "—"}
                  >
                    {lat != null ? (
                      <span className="text-gray-200">{lat.toFixed(0)}</span>
                    ) : (
                      <span className="text-gray-700">—</span>
                    )}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
      <div className="mt-2 flex items-center gap-2 text-xs text-gray-500">
        <span className="inline-block w-3 h-3 rounded" style={{ background: "#064e3b" }} /> fast
        <span className="inline-block w-3 h-3 rounded" style={{ background: "#78350f" }} /> medium
        <span className="inline-block w-3 h-3 rounded" style={{ background: "#7f1d1d" }} /> slow
        <span className="ml-2 text-gray-600">(values in ms)</span>
      </div>
    </div>
  );
}
