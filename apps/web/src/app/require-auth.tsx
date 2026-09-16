import { Navigate, Outlet } from "react-router-dom";
import { PageLoading } from "../components/shared/page-loading";
import { useMeQuery } from "../lib/auth/queries";
import { sessionWasNotKept } from "../lib/auth/session-kept";

/** Authenticated shell only — no role-based nav yet (Phase 7). */
export function RequireAuth() {
  const me = useMeQuery();
  if (me.isPending) {
    return <PageLoading />;
  }
  if (!me.data) {
    // A sign-in that succeeded seconds ago and is already unauthenticated means the browser
    // rejected the session cookie. Redirecting silently makes that indistinguishable from a
    // wrong password, so carry the reason across (#453).
    const to = sessionWasNotKept()
      ? "/login?problem=session-not-kept"
      : "/login";
    return <Navigate to={to} replace />;
  }
  return <Outlet />;
}
