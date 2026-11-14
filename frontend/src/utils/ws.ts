/** Socket host for this page. Quotes travel through the same host as the site, including port 5173. */
export function wsBase(): string {
  const configured = import.meta.env.VITE_WS_URL as string | undefined;
  if (configured) return configured.replace(/^http/, "ws");
  if (typeof window !== "undefined") {
    const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
    return `${proto}//${window.location.host}`;
  }
  return "ws://localhost:8000";
}
