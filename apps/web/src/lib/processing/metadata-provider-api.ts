import { fetchCsrfToken } from "../api/auth-api";
import { apiFetch, readJson, requireOk } from "../api/client";

export interface ProcessingMetadataProvider {
  provider: string;
  base_url: string;
  key_configured: boolean;
  known_providers: string[];
}

export interface ProcessingMetadataProviderWrite {
  provider: "" | "tmdb";
  base_url: string;
  api_key?: string;
}

export interface ProcessingMetadataProviderTest {
  status: "matched" | "no_match" | "not_configured" | "unreachable";
  detail: string;
}

const path = "/api/v1/processing/metadata-provider";

export async function fetchProcessingMetadataProvider(): Promise<ProcessingMetadataProvider> {
  const response = await apiFetch(path);
  await requireOk(path, response, "Could not load the metadata provider");
  return readJson<ProcessingMetadataProvider>(response);
}

export async function putProcessingMetadataProvider(
  data: ProcessingMetadataProviderWrite,
): Promise<ProcessingMetadataProvider> {
  const csrf_token = await fetchCsrfToken();
  const response = await apiFetch(path, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ...data, csrf_token }),
  });
  await requireOk(path, response, "Could not save the metadata provider");
  return readJson<ProcessingMetadataProvider>(response);
}

export async function testProcessingMetadataProvider(
  data: ProcessingMetadataProviderWrite,
): Promise<ProcessingMetadataProviderTest> {
  const csrf_token = await fetchCsrfToken();
  const testPath = `${path}/test`;
  const response = await apiFetch(testPath, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ...data, csrf_token }),
  });
  await requireOk(testPath, response, "Could not test the metadata provider");
  return readJson<ProcessingMetadataProviderTest>(response);
}
