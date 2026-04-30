import { Navigate, Outlet, useLocation } from "react-router-dom";
import { PageLoading } from "../components/shared/page-loading";
import { useSuiteSettingsQuery } from "../lib/suite/queries";

export function RequireSetupWizard() {
  const location = useLocation();
  const settingsQ = useSuiteSettingsQuery();

  if (settingsQ.isPending) {
    return <PageLoading label="Loading setup" />;
  }
  if (settingsQ.isError || !settingsQ.data) {
    return <Outlet />;
  }

  const wizardState = (settingsQ.data.setup_wizard_state || "pending")
    .trim()
    .toLowerCase();
  if (wizardState === "pending" && location.pathname !== "/app/setup-wizard") {
    return <Navigate to="/app/setup-wizard" replace />;
  }

  return <Outlet />;
}
