import { fetchCsrfToken } from "../api/auth-api";
import { apiFetch, readJson, requireOk } from "../api/client";

/** A device the Direct Play badge can answer for. */
export interface DirectPlayDevice {
  id: string;
  name: string;
  /** A URL followed by "(checked YYYY-MM-DD)". */
  source: string;
  note: string;
  selected: boolean;
}

export interface DirectPlayDevices {
  devices: DirectPlayDevice[];
  /** True when the list comes from the operator's own direct-play-devices.json. */
  customised: boolean;
}

export const directPlayDevicesPath = () =>
  "/api/v1/processing/direct-play/devices";

export async function fetchDirectPlayDevices(): Promise<DirectPlayDevices> {
  const path = directPlayDevicesPath();
  const r = await apiFetch(path);
  await requireOk(path, r, "Could not load the Direct Play devices");
  return readJson<DirectPlayDevices>(r);
}

export async function putDirectPlayDevices(
  selected: string[],
): Promise<DirectPlayDevices> {
  const csrf_token = await fetchCsrfToken();
  const path = directPlayDevicesPath();
  const r = await apiFetch(path, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ csrf_token, selected }),
  });
  await requireOk(path, r, "Could not save your Direct Play devices");
  return readJson<DirectPlayDevices>(r);
}
