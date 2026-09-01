import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  fetchRefinerMetadataProvider,
  putRefinerMetadataProvider,
  testRefinerMetadataProvider,
  type RefinerMetadataProviderWrite,
} from "./metadata-provider-api";

export const refinerMetadataProviderKey = [
  "refiner",
  "metadata-provider",
] as const;

export function useRefinerMetadataProviderQuery() {
  return useQuery({
    queryKey: refinerMetadataProviderKey,
    queryFn: fetchRefinerMetadataProvider,
  });
}

export function useSaveRefinerMetadataProvider() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (data: RefinerMetadataProviderWrite) =>
      putRefinerMetadataProvider(data),
    onSuccess: (data) => client.setQueryData(refinerMetadataProviderKey, data),
  });
}

export function useTestRefinerMetadataProvider() {
  return useMutation({
    mutationFn: (data: RefinerMetadataProviderWrite) =>
      testRefinerMetadataProvider(data),
  });
}
