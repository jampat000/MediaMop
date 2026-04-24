import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  fetchSubberJobs,
  fetchSubberLibraryMovies,
  fetchSubberLibraryTv,
  fetchSubberOverview,
  fetchSubberProviders,
  fetchSubberSettings,
  postSubberProviderTest,
  postSubberLibrarySyncMovies,
  postSubberLibrarySyncTv,
  postSubberRadarrRootFolders,
  postSubberSearchAllMissingMovies,
  postSubberSearchAllMissingTv,
  postSubberSearchNow,
  postSubberSonarrRootFolders,
  postSubberTestOpensubtitles,
  postSubberTestRadarr,
  postSubberTestSonarr,
  putSubberProvider,
  putSubberSettings,
  type SubberProviderPutIn,
  type SubberSettingsPutIn,
} from "./subber-api";

export function useSubberSettingsQuery() {
  return useQuery({
    queryKey: ["subber", "settings"],
    queryFn: fetchSubberSettings,
    staleTime: 15_000,
  });
}

export function useSubberProvidersQuery() {
  return useQuery({
    queryKey: ["subber", "providers"],
    queryFn: fetchSubberProviders,
    staleTime: 15_000,
  });
}

export function useSubberOverviewQuery() {
  return useQuery({
    queryKey: ["subber", "overview"],
    queryFn: fetchSubberOverview,
    staleTime: 15_000,
  });
}

export function useSubberLibraryTvQuery(filters: {
  status?: string;
  search?: string;
  language?: string;
  limit?: number;
  offset?: number;
}) {
  return useQuery({
    queryKey: ["subber", "library", "tv", filters],
    queryFn: () => fetchSubberLibraryTv(filters),
    staleTime: 10_000,
  });
}

export function useSubberLibraryMoviesQuery(filters: {
  status?: string;
  search?: string;
  language?: string;
  limit?: number;
  offset?: number;
}) {
  return useQuery({
    queryKey: ["subber", "library", "movies", filters],
    queryFn: () => fetchSubberLibraryMovies(filters),
    staleTime: 10_000,
  });
}

export function useSubberJobsQuery(limit = 100) {
  return useQuery({
    queryKey: ["subber", "jobs", limit],
    queryFn: () => fetchSubberJobs(limit),
    staleTime: 10_000,
  });
}

export function usePutSubberSettingsMutation() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: SubberSettingsPutIn) => putSubberSettings(body),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["subber", "settings"] });
      void qc.invalidateQueries({ queryKey: ["subber", "overview"] });
    },
  });
}

export function usePutSubberProviderMutation() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ providerKey, body }: { providerKey: string; body: SubberProviderPutIn }) => putSubberProvider(providerKey, body),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["subber", "providers"] });
    },
  });
}

export function useSubberTestProviderMutation() {
  return useMutation({
    mutationFn: (providerKey: string) => postSubberProviderTest(providerKey),
  });
}

export function useSubberSearchNowMutation() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (stateId: number) => postSubberSearchNow(stateId),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["subber", "library"] });
      void qc.invalidateQueries({ queryKey: ["subber", "jobs"] });
      void qc.invalidateQueries({ queryKey: ["subber", "overview"] });
    },
  });
}

export function useSubberSearchAllMissingTvMutation() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: postSubberSearchAllMissingTv,
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["subber"] });
    },
  });
}

export function useSubberSearchAllMissingMoviesMutation() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: postSubberSearchAllMissingMovies,
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["subber"] });
    },
  });
}

export function useSubberLibrarySyncTvMutation() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: postSubberLibrarySyncTv,
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["subber", "jobs"] });
      void qc.invalidateQueries({ queryKey: ["subber", "library"] });
    },
  });
}

export function useSubberLibrarySyncMoviesMutation() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: postSubberLibrarySyncMovies,
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["subber", "jobs"] });
      void qc.invalidateQueries({ queryKey: ["subber", "library"] });
    },
  });
}

export function useSubberTestOpensubtitlesMutation() {
  return useMutation({ mutationFn: postSubberTestOpensubtitles });
}

export function useSubberTestSonarrMutation() {
  return useMutation({ mutationFn: postSubberTestSonarr });
}

export function useSubberTestRadarrMutation() {
  return useMutation({ mutationFn: postSubberTestRadarr });
}

export function useSubberSonarrRootFoldersMutation() {
  return useMutation({ mutationFn: postSubberSonarrRootFolders });
}

export function useSubberRadarrRootFoldersMutation() {
  return useMutation({ mutationFn: postSubberRadarrRootFolders });
}
