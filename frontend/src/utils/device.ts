/**
 * Device and environment detection utilities.
 */

export function isNativeMobile(): boolean {
  if (typeof window === "undefined") return false;
  return Boolean(
    (window as any).Capacitor !== undefined ||
    window.location.protocol === "capacitor:" ||
    window.location.protocol === "file:" ||
    (window.location.hostname === "localhost" && !window.location.port)
  );
}

export function isMobileViewport(): boolean {
  if (typeof window === "undefined") return false;
  return window.innerWidth < 768;
}

export function getResolvedApiBaseUrl(): string {
  if (import.meta.env.VITE_API_URL) {
    return import.meta.env.VITE_API_URL;
  }
  if (isNativeMobile()) {
    return "https://pyregex.dpdns.org/api";
  }
  return "/api";
}

export function getResolvedWsBaseUrl(): string {
  const configured = import.meta.env.VITE_WS_URL as string | undefined;
  if (configured) return configured.replace(/^http/, "ws");
  if (isNativeMobile()) {
    return "wss://pyregex.dpdns.org";
  }
  if (typeof window !== "undefined") {
    const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
    return `${proto}//${window.location.host}`;
  }
  return "wss://pyregex.dpdns.org";
}
