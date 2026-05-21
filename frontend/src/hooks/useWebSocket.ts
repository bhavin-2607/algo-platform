import { useEffect, useRef, useState, useCallback } from "react";
import { useAuthStore } from "@/store/auth";

type Status = "connecting" | "connected" | "disconnected";

export function useWebSocket<T = unknown>(path: string) {
  const [messages, setMessages] = useState<T[]>([]);
  const [status, setStatus] = useState<Status>("disconnected");
  const wsRef = useRef<WebSocket | null>(null);
  const token = useAuthStore((s) => s.accessToken);

  useEffect(() => {
    if (!token) return;

    const wsBase = import.meta.env.VITE_WS_URL ?? "ws://localhost:8000";
    const url = `${wsBase}/api/ws/${path}?token=${token}`;

    setStatus("connecting");
    const ws = new WebSocket(url);
    wsRef.current = ws;

    ws.onopen = () => setStatus("connected");
    ws.onclose = () => setStatus("disconnected");
    ws.onerror = () => setStatus("disconnected");
    ws.onmessage = (e) => {
      try {
        const parsed: T = JSON.parse(e.data);
        setMessages((prev) => [...prev.slice(-499), parsed]);
      } catch {
        // ignore malformed frames
      }
    };

    return () => {
      ws.close();
      wsRef.current = null;
    };
  }, [path, token]);

  const send = useCallback((data: unknown) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(data));
    }
  }, []);

  const clear = useCallback(() => setMessages([]), []);

  return { messages, status, send, clear };
}
