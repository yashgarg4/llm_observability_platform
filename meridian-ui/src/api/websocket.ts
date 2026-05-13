import { useEffect, useRef, useState } from "react";
import type { Alert } from "./client";

export function useAlerts(maxItems = 50): Alert[] {
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const wsRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    const protocol = window.location.protocol === "https:" ? "wss" : "ws";
    const ws = new WebSocket(`${protocol}://${window.location.host}/ws/alerts`);
    wsRef.current = ws;

    ws.onmessage = (ev) => {
      try {
        const alert = JSON.parse(ev.data as string) as Alert;
        setAlerts((prev) => [alert, ...prev].slice(0, maxItems));
      } catch {
        // ignore malformed messages
      }
    };

    return () => {
      ws.close();
    };
  }, [maxItems]);

  return alerts;
}
