import { useEffect, useState } from "react";
import { api, type Run, type Span } from "../api/client";

interface Props { runs: Run[] }

type DiffLine = { type: "same" | "add" | "remove"; text: string };

function flattenSpans(spans: Span[]): Span[] {
  return spans.flatMap((s) => [s, ...flattenSpans(s.children)]);
}

function extractPrompt(spans: Span[]): string {
  const llm = flattenSpans(spans).find((s) => s.name === "llm.call");
  if (!llm) return "";
  const keys = ["llm.prompt", "input", "prompt", "llm.input"];
  for (const k of keys) {
    if (llm.attributes[k]) return String(llm.attributes[k]);
  }
  return JSON.stringify(llm.attributes, null, 2);
}

function diffLines(a: string, b: string): DiffLine[] {
  const la = a.split("\n");
  const lb = b.split("\n");
  const result: DiffLine[] = [];
  const maxLen = Math.max(la.length, lb.length);
  for (let i = 0; i < maxLen; i++) {
    const lineA = la[i] ?? "";
    const lineB = lb[i] ?? "";
    if (lineA === lineB) {
      result.push({ type: "same", text: lineA });
    } else {
      if (lineA) result.push({ type: "remove", text: lineA });
      if (lineB) result.push({ type: "add",    text: lineB });
    }
  }
  return result;
}

const lineStyle: Record<DiffLine["type"], string> = {
  same:   "text-gray-400",
  add:    "bg-emerald-900/40 text-emerald-300",
  remove: "bg-red-900/40 text-red-300 line-through",
};

export default function PromptDiff({ runs }: Props) {
  const [runA, setRunA]   = useState<string>("");
  const [runB, setRunB]   = useState<string>("");
  const [diff, setDiff]   = useState<DiffLine[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!runA || !runB || runA === runB) { setDiff([]); return; }
    setLoading(true);
    Promise.all([api.runs.spans(runA), api.runs.spans(runB)])
      .then(([sa, sb]) => {
        const pa = extractPrompt(sa);
        const pb = extractPrompt(sb);
        setDiff(diffLines(pa, pb));
      })
      .catch(console.error)
      .finally(() => setLoading(false));
  }, [runA, runB]);

  return (
    <div className="flex flex-col gap-3">
      <div className="flex gap-2">
        <select
          className="flex-1 bg-gray-800 border border-gray-700 rounded px-2 py-1 text-xs focus:outline-none focus:border-indigo-500"
          value={runA}
          onChange={(e) => setRunA(e.target.value)}
        >
          <option value="">— Run A —</option>
          {runs.map((r) => (
            <option key={r.id} value={r.id}>
              {r.service_name} · {new Date(r.start_time * 1000).toLocaleTimeString()}
            </option>
          ))}
        </select>
        <select
          className="flex-1 bg-gray-800 border border-gray-700 rounded px-2 py-1 text-xs focus:outline-none focus:border-indigo-500"
          value={runB}
          onChange={(e) => setRunB(e.target.value)}
        >
          <option value="">— Run B —</option>
          {runs.map((r) => (
            <option key={r.id} value={r.id}>
              {r.service_name} · {new Date(r.start_time * 1000).toLocaleTimeString()}
            </option>
          ))}
        </select>
      </div>

      {loading && <div className="text-gray-500 text-xs">Computing diff…</div>}

      {diff.length === 0 && !loading && (
        <div className="text-gray-500 text-xs py-4 text-center">
          {runA && runB ? "No prompt attributes found in spans." : "Select two runs to compare prompts."}
        </div>
      )}

      {diff.length > 0 && (
        <div className="overflow-y-auto max-h-96 rounded bg-gray-900 border border-gray-700 p-2">
          {diff.map((line, i) => (
            <div key={i} className={`font-mono text-xs px-2 py-0.5 rounded ${lineStyle[line.type]}`}>
              <span className="select-none mr-2 text-gray-600">
                {line.type === "add" ? "+" : line.type === "remove" ? "−" : " "}
              </span>
              {line.text || " "}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
