export interface CityLocation {
  name: string;
  lat: number;
  lon: number;
}

export const PRESET_CITIES: CityLocation[] = [
  { name: "Ahmedabad", lat: 23.0225, lon: 72.5714 },
  { name: "Mumbai (NSE)", lat: 19.0760, lon: 72.8777 },
  { name: "New Delhi", lat: 28.6139, lon: 77.2090 },
  { name: "Bengaluru", lat: 12.9716, lon: 77.5946 },
  { name: "Kolkata", lat: 22.5726, lon: 88.3639 },
];

export interface AstroTimingSettings {
  includePreviousWeek: boolean;
  includeNextWeek: boolean;
  city: string;
  latitude: number;
  longitude: number;
}

const STORAGE_KEY = "algo_platform_astro_settings";

export const DEFAULT_ASTRO_SETTINGS: AstroTimingSettings = {
  includePreviousWeek: true,
  includeNextWeek: true,
  city: "Ahmedabad",
  latitude: 23.0225,
  longitude: 72.5714,
};

export function getAstroSettings(): AstroTimingSettings {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return DEFAULT_ASTRO_SETTINGS;
    const parsed = JSON.parse(raw);
    return {
      includePreviousWeek: parsed.includePreviousWeek !== false,
      includeNextWeek: parsed.includeNextWeek !== false,
      city: parsed.city || "Ahmedabad",
      latitude: typeof parsed.latitude === "number" ? parsed.latitude : 23.0225,
      longitude: typeof parsed.longitude === "number" ? parsed.longitude : 72.5714,
    };
  } catch {
    return DEFAULT_ASTRO_SETTINGS;
  }
}

export function saveAstroSettings(settings: AstroTimingSettings): void {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(settings));
    window.dispatchEvent(new CustomEvent("astro_settings_updated", { detail: settings }));
  } catch {
    // ignore local storage errors
  }
}
