import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  fetchBootstrapStatus,
  fetchCurrentSession,
  postChangePassword,
  fetchMe,
  postBootstrap,
  postLogin,
  postLogout,
} from "../api/auth-api";
import { activityRecentKey } from "../activity/queries";
import { dashboardStatusKey } from "../dashboard/queries";

export const qk = {
  me: ["auth", "me"] as const,
  session: ["auth", "session"] as const,
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

export function useCurrentSessionQuery() {
  return useQuery({
    queryKey: qk.session,
    queryFn: fetchCurrentSession,
    retry: false,
  });
}

export function useLoginMutation() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      username,
      password,
      trustedDevice,
    }: {
      username: string;
      password: string;
      trustedDevice: boolean;
    }) => postLogin(username, password, trustedDevice),
    onSuccess: (data) => {
      // Anonymous /me is cached as `null` (401). Hydrate from the login response — do not invalidate
      // /me here: an immediate refetch can run before the session cookie is visible to fetch(), get
      // 401, and overwrite this cache back to null (E2E/CI flake).
      qc.setQueryData(qk.me, data.user);
      void qc.invalidateQueries({ queryKey: qk.bootstrap });
      void qc.invalidateQueries({ queryKey: qk.session });
      void qc.invalidateQueries({ queryKey: activityRecentKey });
      void qc.invalidateQueries({ queryKey: dashboardStatusKey });
    },
  });
}

export function useLogoutMutation() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: postLogout,
    onMutate: async () => {
      await qc.cancelQueries({ queryKey: qk.me });
      await qc.cancelQueries({ queryKey: qk.session });
      qc.setQueryData(qk.me, null);
      qc.setQueryData(qk.session, null);
    },
    onSettled: () => {
      void qc.invalidateQueries({ queryKey: qk.me });
      void qc.invalidateQueries({ queryKey: qk.session });
      void qc.invalidateQueries({ queryKey: qk.bootstrap });
      void qc.invalidateQueries({ queryKey: activityRecentKey });
      void qc.invalidateQueries({ queryKey: dashboardStatusKey });
    },
  });
}

export function useBootstrapMutation() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      username,
      password,
    }: {
      username: string;
      password: string;
    }) => postBootstrap(username, password),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: qk.bootstrap });
      void qc.invalidateQueries({ queryKey: activityRecentKey });
      void qc.invalidateQueries({ queryKey: dashboardStatusKey });
    },
  });
}

export function useChangePasswordMutation() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      currentPassword,
      newPassword,
    }: {
      currentPassword: string;
      newPassword: string;
    }) => postChangePassword(currentPassword, newPassword),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: qk.me });
      void qc.invalidateQueries({ queryKey: qk.session });
      void qc.invalidateQueries({ queryKey: activityRecentKey });
      void qc.invalidateQueries({ queryKey: dashboardStatusKey });
    },
  });
}
