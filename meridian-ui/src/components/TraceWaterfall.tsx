import { useEffect, useState } from "react";
import { api, type Span } from "../api/client";

interface Props { runId: string }

interface FlatSpan extends Omit<Span, "children"> {
  depth: number;
  children: FlatSpan[];
}

function flatten(spans: Span[], depth = 0): FlatSpan[] {
  return spans.flatMap((s) => [
    { ...s, depth, children: [] },
    ...flatten(s.children, depth + 1),
  ]);
}

function spanColor(name: string): string {
  if (name === "llm.call")      return "bg-green-500";
  if (name === "langgraph.node") return "bg-purple-500";
  return "bg-gray-500";
}

interface TooltipState {
  span: FlatSpan;
  x: number;
  y: number;
}

export default function TraceWaterfall({ runId }: Props) {
  const [spans, setSpans] = useState<FlatSpan[]>([]);
  const [tooltip, setTooltip] = useState<TooltipState | null>(null);

  useEffect(() => {
    api.runs.spans(runId).then((tree) => setSpans(flatten(tree))).catch(console.error);
  }, [runId]);

  if (spans.length === 0) {
    return <div className="text-gray-500 text-xs py-4 text-center">No spans.</div>;
  }

  const tMin = Math.min(...spans.map((s) => s.start_time));
  const tMax = Math.max(...spans.map((s) => s.end_time));
  const range = tMax - tMin || 1;

  return (
    <div className="overflow-x-auto">
      {tooltip && (
        <div
          className="fixed z-50 bg-gray-800 border border-gray-600 rounded p-2 text-xs max-w-xs shadow-xl pointer-events-none"
          style={{ left: tooltip.x + 14, top: tooltip.y + 14 }}
        >
          <div className="font-bold text-white mb-1">{tooltip.span.name}</div>
          {!!tooltip.span.attributes["node.name"] && (
            <div className="text-gray-300">node: {String(tooltip.span.attributes["node.name"])}</div>
          )}
          {!!tooltip.span.attributes["llm.model"] && (
            <div className="text-gray-300">model: {String(tooltip.span.attributes["llm.model"])}</div>
          )}
          <div className="text-yellow-300">latency: {tooltip.span.latency_ms.toFixed(2)} ms</div>
          {tooltip.span.attributes["llm.input_tokens"] != null && (
            <div className="text-blue-300">
              tokens: {String(tooltip.span.attributes["llm.input_tokens"])} in / {String(tooltip.span.attributes["llm.output_tokens"])} out
            </div>
          )}
          {tooltip.span.attributes["llm.cost_usd"] != null && (
            <div className="text-emerald-300">cost: ${Number(tooltip.span.attributes["llm.cost_usd"]).toFixed(6)}</div>
          )}
          {tooltip.span.error && <div className="text-red-400 mt-1">error: {tooltip.span.error}</div>}
        </div>
      )}

      <div className="flex flex-col gap-0.5 min-w-[600px]">
        {spans.map((s) => {
          const left  = ((s.start_time - tMin) / range) * 100;
          const width = Math.max(((s.end_time - s.start_time) / range) * 100, 0.5);

          return (
            <div key={s.id} className="flex items-center gap-2 h-6">
              {/* Label */}
              <div
                className="shrink-0 text-right text-gray-400 truncate"
                style={{ width: 160, paddingLeft: s.depth * 12, textAlign: "left" }}
              >
                <span className="text-gray-300">{s.name}</span>
                {!!s.attributes["node.name"] && (
                  <span className="text-gray-500 ml-1">({String(s.attributes["node.name"])})</span>
                )}
              </div>
              {/* Bar track */}
              <div className="relative flex-1 h-4 bg-gray-800 rounded">
                <div
                  className={`absolute top-0 h-full rounded cursor-pointer opacity-80 hover:opacity-100 transition-opacity ${spanColor(s.name)}`}
                  style={{ left: `${left}%`, width: `${width}%`, minWidth: 3 }}
                  onMouseEnter={(e) => setTooltip({ span: s, x: e.clientX, y: e.clientY })}
                  onMouseMove={(e) => setTooltip((t) => t ? { ...t, x: e.clientX, y: e.clientY } : null)}
                  onMouseLeave={() => setTooltip(null)}
                />
              </div>
              {/* Latency */}
              <div className="shrink-0 text-right text-gray-400 w-16 text-xs">
                {s.latency_ms.toFixed(1)} ms
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
