import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { useState } from "react";
import { BrandHeaderLink } from "../components/brand/brand-header-link";
import { NavIconActivity, NavIconDashboard, NavIconRefiner, NavIconSettings, NavIconSubber, NavIconPruner } from "../components/shell/nav-icons";
import { useLogoutMutation } from "../lib/auth/queries";
import { useDashboardStatusQuery } from "../lib/dashboard/queries";
import { useSuiteSettingsQuery } from "../lib/suite/queries";
import { persistAppTheme, readStoredAppTheme, type AppTheme } from "../lib/ui/app-theme";

function sidebarNavClass({ isActive }: { isActive: boolean }) {
  return isActive ? "mm-sidebar-link active" : "mm-sidebar-link";
}

export function AppShell() {
  const navigate = useNavigate();
  const logout = useLogoutMutation();
  const suite = useSuiteSettingsQuery();
  const dashboard = useDashboardStatusQuery();
  const [theme, setTheme] = useState<AppTheme>(() => readStoredAppTheme());
  const productTitle = (suite.data?.product_display_name ?? "MediaMop").trim() || "MediaMop";
  const appVersion = dashboard.data?.system.api_version;
  const nextTheme: AppTheme = theme === "dark" ? "light" : "dark";
  const handleSignOut = () => {
    logout.mutate(undefined, {
      onSettled: () => {
        navigate("/login", { replace: true });
      },
    });
    navigate("/login", { replace: true });
  };

  return (
    <div className="mm-app-layout" data-testid="shell-ready">
      <aside className="mm-sidebar" aria-label="Product">
        <BrandHeaderLink to="/app" productTitle={productTitle} />
        <nav className="mm-sidebar-nav" aria-label="Primary">
          <p className="mm-sidebar-section-label">Overview</p>
          <NavLink to="/app" end className={sidebarNavClass}>
            <span className="mm-sidebar-link-icon" aria-hidden="true">
              <NavIconDashboard />
            </span>
            <span className="mm-sidebar-link-label">Dashboard</span>
          </NavLink>
          <NavLink to="/app/activity" className={sidebarNavClass}>
            <span className="mm-sidebar-link-icon" aria-hidden="true">
              <NavIconActivity />
            </span>
            <span className="mm-sidebar-link-label">Activity</span>
          </NavLink>

          <p className="mm-sidebar-section-label">Modules</p>
          <NavLink to="/app/refiner" className={sidebarNavClass}>
            <span className="mm-sidebar-link-icon" aria-hidden="true">
              <NavIconRefiner />
            </span>
            <span className="mm-sidebar-link-label">Refiner</span>
          </NavLink>
          <NavLink to="/app/pruner" className={sidebarNavClass}>
            <span className="mm-sidebar-link-icon" aria-hidden="true">
              <NavIconPruner />
            </span>
            <span className="mm-sidebar-link-label">Pruner</span>
          </NavLink>
          <NavLink to="/app/subber" className={sidebarNavClass}>
            <span className="mm-sidebar-link-icon" aria-hidden="true">
              <NavIconSubber />
            </span>
            <span className="mm-sidebar-link-label">Subber</span>
          </NavLink>

          <p className="mm-sidebar-section-label">System</p>
          <NavLink to="/app/settings" className={sidebarNavClass}>
            <span className="mm-sidebar-link-icon" aria-hidden="true">
              <NavIconSettings />
            </span>
            <span className="mm-sidebar-link-label">Settings</span>
          </NavLink>
        </nav>
        <div className="mm-sidebar-footer">
          <div className="mm-sidebar-footer-panel">
            <div className="mm-sidebar-meta">{productTitle}</div>
            <div className="mm-sidebar-version" title="Installed MediaMop version reported by the running server">
              {appVersion ? `Version ${appVersion}` : "Version checking..."}
            </div>
            <button
              type="button"
              data-testid="sign-out"
              className="mm-sidebar-signout"
              disabled={logout.isPending}
              onClick={handleSignOut}
            >
              {logout.isPending ? "Signing out…" : "Sign out"}
            </button>
          </div>
        </div>
      </aside>
      <main className="mm-main" id="mm-main-content" tabIndex={-1}>
        <div className="mm-main-inner">
          <div className="mm-shell-toolbar" aria-label="Display controls">
            <button
              type="button"
              className="mm-theme-toggle"
              data-testid="theme-toggle"
              aria-label={`Switch to ${nextTheme} mode`}
              title={`Switch to ${nextTheme} mode`}
              onClick={() => {
                setTheme(nextTheme);
                persistAppTheme(nextTheme);
              }}
            >
              <span className="mm-theme-toggle__dot" aria-hidden="true" />
              <span className="mm-theme-toggle__label">{theme === "dark" ? "Dark" : "Light"}</span>
            </button>
          </div>
          <Outlet />
        </div>
      </main>
    </div>
  );
}
