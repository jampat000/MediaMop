import { Navigate, Outlet } from "react-router-dom";
import { PageLoading } from "../components/shared/page-loading";
import { useMeQuery } from "../lib/auth/queries";

/** Authenticated shell only — no role-based nav yet (Phase 7). */
export function RequireAuth() {
  const me = useMeQuery();
  if (me.isPending) {
    return <PageLoading />;
  }
  // After sign-in, /me may still be cached `null` from the anonymous 401 while a refetch runs.
  if (!me.data && me.isFetching) {
    return <PageLoading />;
  }
  if (!me.data) {
    return <Navigate to="/login" replace />;
  }
  return <Outlet />;
}
