import { useEffect, useState } from "react";
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid,
  Tooltip, Legend, ResponsiveContainer,
} from "recharts";
import { api, type RegressionPoint } from "../api/client";

interface Props {
  serviceFilter?: string;
}

export default function RegressionView({ serviceFilter = "" }: Props) {
  const [allServices, setAllServices] = useState<string[]>([]);
  const [points, setPoints]           = useState<RegressionPoint[]>([]);
  const [service, setService]         = useState(serviceFilter);
  const [bucket, setBucket]           = useState<"day" | "hour">("day");

  // Sync local selector when the global sidebar filter changes
  useEffect(() => {
    setService(serviceFilter);
  }, [serviceFilter]);

  useEffect(() => {
    api.regression.get({ limit: 200 })
      .then((data) => {
        const svcs = [...new Set(data.map((p) => p.service_name))].sort();
        setAllServices(svcs);
      })
      .catch(console.error);
  }, []);

  useEffect(() => {
    api.regression
      .get({ service_name: service || undefined, bucket, limit: 30 })
      .then((data) => setPoints([...data].reverse()))
      .catch(console.error);
  }, [service, bucket]);

  return (
    <div className="flex flex-col gap-5">
      <div className="flex items-center gap-3">
        <select
          value={service}
          onChange={(e) => setService(e.target.value)}
          className="bg-gray-800 border border-gray-700 text-gray-300 text-xs rounded px-2 py-1"
        >
          <option value="">All services</option>
          {allServices.map((s) => (
            <option key={s} value={s}>{s}</option>
          ))}
        </select>
        <select
          value={bucket}
          onChange={(e) => setBucket(e.target.value as "day" | "hour")}
          className="bg-gray-800 border border-gray-700 text-gray-300 text-xs rounded px-2 py-1"
        >
          <option value="day">Per day</option>
          <option value="hour">Per hour</option>
        </select>
      </div>

      {points.length === 0 ? (
        <div className="text-gray-500 text-xs py-8 text-center">No regression data yet — run some queries first.</div>
      ) : points.length === 1 ? (
        <div className="text-amber-500/70 text-xs py-2 px-3 rounded bg-amber-900/20 border border-amber-800/30 mb-2">
          Only 1 time bucket so far — trend lines need data from multiple {bucket === "hour" ? "hours" : "days"} to appear. Switch to &quot;Per hour&quot; if all runs are from today.
        </div>
      ) : null}
      {points.length > 0 && (
        <>
          <div>
            <div className="text-gray-400 text-xs mb-2">Avg latency (ms) &amp; avg cost (USD)</div>
            <ResponsiveContainer width="100%" height={220}>
              <LineChart data={points} margin={{ top: 4, right: 48, left: 0, bottom: 4 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
                <XAxis dataKey="bucket" tick={{ fill: "#9ca3af", fontSize: 10 }} />
                <YAxis
                  yAxisId="lat"
                  tick={{ fill: "#9ca3af", fontSize: 10 }}
                  unit="ms"
                  width={56}
                />
                <YAxis
                  yAxisId="cost"
                  orientation="right"
                  tick={{ fill: "#9ca3af", fontSize: 10 }}
                  tickFormatter={(v: number) =>
                    v === 0 ? "$0" : v < 0.001 ? `${(v * 1_000_000).toFixed(0)}µ$` : `$${v.toFixed(4)}`
                  }
                  width={64}
                />
                <Tooltip
                  contentStyle={{ background: "#1f2937", border: "1px solid #374151", fontSize: 11 }}
                  formatter={(value: number, name: string): [string, string] => {
                    if (name === "avg_latency_ms") return [`${value.toFixed(0)} ms`, "Avg latency"];
                    if (name === "avg_cost_usd")   return [value < 0.001 ? `${(value * 1_000_000).toFixed(2)}µ$` : `$${value.toFixed(6)}`, "Avg cost"];
                    return [String(value), name];
                  }}
                />
                <Legend wrapperStyle={{ fontSize: 11, color: "#9ca3af" }} />
                <Line
                  yAxisId="lat" type="monotone" dataKey="avg_latency_ms"
                  stroke="#6366f1" strokeWidth={2} dot={{ r: 3 }} activeDot={{ r: 5 }}
                  connectNulls name="avg_latency_ms"
                />
                <Line
                  yAxisId="cost" type="monotone" dataKey="avg_cost_usd"
                  stroke="#10b981" strokeWidth={2} dot={{ r: 3 }} activeDot={{ r: 5 }}
                  connectNulls name="avg_cost_usd"
                />
              </LineChart>
            </ResponsiveContainer>
          </div>

          <div>
            <div className="text-gray-400 text-xs mb-2">Run count &amp; error rate</div>
            <ResponsiveContainer width="100%" height={160}>
              <LineChart data={points} margin={{ top: 4, right: 48, left: 0, bottom: 4 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
                <XAxis dataKey="bucket" tick={{ fill: "#9ca3af", fontSize: 10 }} />
                <YAxis
                  yAxisId="count"
                  tick={{ fill: "#9ca3af", fontSize: 10 }}
                  allowDecimals={false}
                  width={32}
                />
                <YAxis
                  yAxisId="err"
                  orientation="right"
                  tick={{ fill: "#9ca3af", fontSize: 10 }}
                  tickFormatter={(v: number) => `${(v * 100).toFixed(0)}%`}
                  width={40}
                />
                <Tooltip
                  contentStyle={{ background: "#1f2937", border: "1px solid #374151", fontSize: 11 }}
                  formatter={(value: number, name: string): [string, string] => {
                    if (name === "run_count")  return [String(value), "Runs"];
                    if (name === "error_rate") return [`${(value * 100).toFixed(1)}%`, "Error rate"];
                    return [String(value), name];
                  }}
                />
                <Legend wrapperStyle={{ fontSize: 11, color: "#9ca3af" }} />
                <Line
                  yAxisId="count" type="monotone" dataKey="run_count"
                  stroke="#f59e0b" strokeWidth={2} dot={{ r: 3 }} activeDot={{ r: 5 }}
                  connectNulls name="run_count"
                />
                <Line
                  yAxisId="err" type="monotone" dataKey="error_rate"
                  stroke="#ef4444" strokeWidth={2} dot={{ r: 3 }} activeDot={{ r: 5 }}
                  connectNulls name="error_rate"
                />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </>
      )}
    </div>
  );
}
