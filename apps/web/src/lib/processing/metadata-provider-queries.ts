import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  fetchProcessingMetadataProvider,
  putProcessingMetadataProvider,
  testProcessingMetadataProvider,
  type ProcessingMetadataProviderWrite,
} from "./metadata-provider-api";

export const processingMetadataProviderKey = [
  "processing",
  "metadata-provider",
] as const;

export function useProcessingMetadataProviderQuery() {
  return useQuery({
    queryKey: processingMetadataProviderKey,
    queryFn: fetchProcessingMetadataProvider,
  });
}

export function useSaveProcessingMetadataProvider() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (data: ProcessingMetadataProviderWrite) =>
      putProcessingMetadataProvider(data),
    onSuccess: (data) =>
      client.setQueryData(processingMetadataProviderKey, data),
  });
}

export function useTestProcessingMetadataProvider() {
  return useMutation({
    mutationFn: (data: ProcessingMetadataProviderWrite) =>
      testProcessingMetadataProvider(data),
  });
}
