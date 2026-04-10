import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  fetchBootstrapStatus,
  fetchMe,
  postBootstrap,
  postLogin,
  postLogout,
} from "../api/auth-api";
import { activityRecentKey } from "../activity/queries";
import { dashboardStatusKey } from "../dashboard/queries";

export const qk = {
  me: ["auth", "me"] as const,
  bootstrap: ["auth", "bootstrap-status"] as const,
};

export function useMeQuery() {
  return useQuery({
    queryKey: qk.me,
    queryFn: fetchMe,
    retry: false,
  });
}

export function useBootstrapStatusQuery() {
  return useQuery({
    queryKey: qk.bootstrap,
    queryFn: fetchBootstrapStatus,
    retry: 1,
  });
}

export function useLoginMutation() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ username, password }: { username: string; password: string }) =>
      postLogin(username, password),
    onSuccess: (data) => {
      // Anonymous /me is cached as `null` (401). Hydrate before navigation so RequireAuth does not
      // see stale null while isPending is already false (successful null is not "loading").
      qc.setQueryData(qk.me, data.user);
      void qc.invalidateQueries({ queryKey: qk.me });
      void qc.invalidateQueries({ queryKey: qk.bootstrap });
      void qc.invalidateQueries({ queryKey: activityRecentKey });
      void qc.invalidateQueries({ queryKey: dashboardStatusKey });
    },
  });
}

export function useLogoutMutation() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: postLogout,
    onSettled: () => {
      void qc.invalidateQueries({ queryKey: qk.me });
      void qc.invalidateQueries({ queryKey: qk.bootstrap });
      void qc.invalidateQueries({ queryKey: activityRecentKey });
      void qc.invalidateQueries({ queryKey: dashboardStatusKey });
    },
  });
}

export function useBootstrapMutation() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ username, password }: { username: string; password: string }) =>
      postBootstrap(username, password),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: qk.bootstrap });
      void qc.invalidateQueries({ queryKey: activityRecentKey });
      void qc.invalidateQueries({ queryKey: dashboardStatusKey });
    },
  });
}
