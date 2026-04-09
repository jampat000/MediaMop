import { Navigate } from "react-router-dom";
import { AuthBrandStack } from "../components/brand/auth-brand-stack";
import { ApiEntryError } from "../components/shared/api-entry-error";
import { PageLoading } from "../components/shared/page-loading";
import { resolveEntryDecision } from "../lib/auth/routes";
import { useBootstrapStatusQuery, useMeQuery } from "../lib/auth/queries";

export function RootEntry() {
  const me = useMeQuery();
  const boot = useBootstrapStatusQuery();

  if (me.isPending || boot.isPending) {
    return <PageLoading />;
  }
  if (me.data) {
    return <Navigate to="/app" replace />;
  }
  if (me.isError || boot.isError) {
    const err = boot.error ?? me.error;
    return (
      <main className="mm-auth-body" id="mm-main-content" tabIndex={-1}>
        <div className="mm-auth-frame">
          <AuthBrandStack />
          <div className="mm-auth-card">
            <ApiEntryError error={err} />
          </div>
        </div>
      </main>
    );
  }

  const decision = resolveEntryDecision({
    meLoading: false,
    bootstrapLoading: false,
    user: null,
    bootstrapAllowed: boot.data?.bootstrap_allowed,
  });
  if (decision.kind === "wait") {
    return <PageLoading />;
  }
  return <Navigate to={decision.to} replace />;
}
