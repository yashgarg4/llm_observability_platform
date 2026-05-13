import { useEffect, useState } from "react";
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, Legend, ResponsiveContainer,
} from "recharts";
import { api } from "../api/client";

interface ChartRow {
  label: string;
  [nodeName: string]: number | string;
}

interface Props {
  serviceFilter?: string;
}

const COLORS = ["#6366f1", "#10b981", "#f59e0b", "#ef4444", "#8b5cf6", "#06b6d4"];

export default function CostChart({ serviceFilter = "" }: Props) {
  const [rows, setRows]       = useState<ChartRow[]>([]);
  const [nodes, setNodes]     = useState<string[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    api.runs
      .list({ limit: 20, service_name: serviceFilter || undefined })
      .then(async ({ items }) => {
        if (items.length === 0) {
          setRows([]);
          setNodes([]);
          setLoading(false);
          return;
        }

        const costs = await Promise.all(items.map((r) => api.runs.cost(r.id)));

        // Only keep runs that actually have LLM cost data
        const withCost = items
          .map((r, i) => ({ run: r, cost: costs[i] }))
          .filter(({ cost }) => cost.total_cost_usd > 0)
          .slice(-10)   // last 10 with real data, ascending order
          .reverse()
          .reverse();

        if (withCost.length === 0) {
          setRows([]);
          setNodes([]);
          setLoading(false);
          return;
        }

        const allNodes = Array.from(
          new Set(
            withCost.flatMap(({ cost }) => cost.breakdown.map((b) => b.node_name))
          )
        );
        setNodes(allNodes);

        const data: ChartRow[] = withCost.map(({ run, cost }) => {
          const ts = new Date(run.start_time * 1000);
          const label = `${run.service_name.slice(0, 10)} ${ts.toLocaleTimeString([], {
            hour: "2-digit",
            minute: "2-digit",
          })}`;
          const row: ChartRow = { label };
          for (const node of allNodes) {
            const entry = cost.breakdown.find((b) => b.node_name === node);
            // µUSD so small Gemini costs (fractions of a cent) are visible as bars
            row[node] = entry ? parseFloat((entry.cost_usd * 1_000_000).toFixed(3)) : 0;
          }
          return row;
        });

        setRows(data);
        setLoading(false);
      })
      .catch((e) => {
        console.error(e);
        setLoading(false);
      });
  }, [serviceFilter]);

  if (loading) {
    return <div className="text-gray-500 text-xs py-4 text-center">Loading…</div>;
  }
  if (rows.length === 0) {
    return (
      <div className="text-gray-500 text-xs py-4 text-center">
        No cost data yet — run a query first to generate LLM spans.
      </div>
    );
  }

  return (
    <ResponsiveContainer width="100%" height={300}>
      <BarChart data={rows} margin={{ top: 8, right: 16, left: 8, bottom: 72 }}>
        <XAxis
          dataKey="label"
          tick={{ fill: "#9ca3af", fontSize: 10 }}
          angle={-40}
          textAnchor="end"
          interval={0}
        />
        <YAxis
          tick={{ fill: "#9ca3af", fontSize: 10 }}
          width={52}
          tickFormatter={(v: number) => `${v}µ$`}
          label={{
            value: "Cost (µUSD)",
            angle: -90,
            position: "insideLeft",
            fill: "#6b7280",
            fontSize: 11,
          }}
        />
        <Tooltip
          cursor={{ fill: "rgba(255,255,255,0.04)" }}
          contentStyle={{ background: "#1f2937", border: "1px solid #374151", fontSize: 11 }}
          formatter={(v: number, name: string) => [`$${(v / 1_000_000).toFixed(7)}`, name]}
        />
        <Legend wrapperStyle={{ fontSize: 11, color: "#9ca3af", paddingTop: 8 }} />
        {nodes.map((n, i) => (
          <Bar
            key={n}
            dataKey={n}
            stackId="cost"
            fill={COLORS[i % COLORS.length]}
            isAnimationActive={false}
          />
        ))}
      </BarChart>
    </ResponsiveContainer>
  );
}
