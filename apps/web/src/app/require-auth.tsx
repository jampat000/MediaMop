import { Navigate, Outlet } from "react-router-dom";
import { PageLoading } from "../components/shared/page-loading";
import { useMeQuery } from "../lib/auth/queries";

/** Authenticated shell only — no role-based nav yet (Phase 7). */
export function RequireAuth() {
  const me = useMeQuery();
  if (me.isPending) {
    return <PageLoading />;
  }
  if (!me.data) {
    return <Navigate to="/login" replace />;
  }
  return <Outlet />;
}
