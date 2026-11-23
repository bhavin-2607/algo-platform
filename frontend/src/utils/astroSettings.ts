export interface AstroTimingSettings {
  includePreviousWeek: boolean;
  includeNextWeek: boolean;
}

const STORAGE_KEY = "algo_platform_astro_settings";

export const DEFAULT_ASTRO_SETTINGS: AstroTimingSettings = {
  includePreviousWeek: true,
  includeNextWeek: true,
};

export function getAstroSettings(): AstroTimingSettings {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return DEFAULT_ASTRO_SETTINGS;
    const parsed = JSON.parse(raw);
    return {
      includePreviousWeek: parsed.includePreviousWeek !== false,
      includeNextWeek: parsed.includeNextWeek !== false,
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
