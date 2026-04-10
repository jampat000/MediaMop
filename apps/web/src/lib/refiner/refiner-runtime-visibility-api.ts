import { apiFetch, readJson } from "../api/client";
import type { RefinerRuntimeVisibilityOut } from "./types";

export const refinerRuntimeVisibilityPath = () => "/api/v1/refiner/runtime/visibility";

export async function fetchRefinerRuntimeVisibility(): Promise<RefinerRuntimeVisibilityOut> {
  const r = await apiFetch(refinerRuntimeVisibilityPath());
  if (!r.ok) {
    throw new Error(`Could not load Refiner settings (${r.status})`);
  }
  return readJson<RefinerRuntimeVisibilityOut>(r);
}
