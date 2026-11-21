import { getResolvedWsBaseUrl } from "@/utils/device";

/** Socket host for market feed and notifications */
export function wsBase(): string {
  return getResolvedWsBaseUrl();
}
