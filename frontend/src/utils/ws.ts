/** Socket host for this page. Docker uses the same host as the site. Vite dev stays on the API port. */
export function wsBase(): string {
  const configured = import.meta.env.VITE_WS_URL as string | undefined;
  if (configured) return configured.replace(/^http/, "ws");
  if (typeof window !== "undefined" && window.location.port === "5173") {
    return "ws://localhost:8000";
  }
  if (typeof window !== "undefined") {
    const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
    return `${proto}//${window.location.host}`;
  }
  return "ws://localhost:8000";
}
