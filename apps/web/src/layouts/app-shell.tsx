import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { useState } from "react";
import { BrandHeaderLink } from "../components/brand/brand-header-link";
import {
  NavIconActivity,
  NavIconChevronLeft,
  NavIconChevronRight,
  NavIconDashboard,
  NavIconRefiner,
  NavIconSettings,
  NavIconPruner,
  NavIconSignOut,
} from "../components/shell/nav-icons";
import { PauseControl } from "../components/shell/pause-control";
import { useLogoutMutation } from "../lib/auth/queries";
import { useDashboardStatusQuery } from "../lib/dashboard/queries";
import { useSuiteSettingsQuery } from "../lib/suite/queries";
import {
  persistAppTheme,
  readStoredAppTheme,
  type AppTheme,
} from "../lib/ui/app-theme";

function sidebarNavClass({ isActive }: { isActive: boolean }) {
  return isActive ? "mm-sidebar-link active" : "mm-sidebar-link";
}

export function AppShell() {
  const navigate = useNavigate();
  const logout = useLogoutMutation();
  const suite = useSuiteSettingsQuery();
  const dashboard = useDashboardStatusQuery();
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [theme, setTheme] = useState<AppTheme>(() => readStoredAppTheme());
  const productTitle =
    (suite.data?.product_display_name ?? "MediaMop").trim() || "MediaMop";
  const appVersion = dashboard.data?.system.api_version;
  const nextTheme: AppTheme = theme === "dark" ? "light" : "dark";
  const handleSignOut = () => {
    logout.mutate(undefined, {
      onSettled: () => {
        void navigate("/login", { replace: true });
      },
    });
    void navigate("/login", { replace: true });
  };

  return (
    <div className="mm-app-layout" data-testid="shell-ready">
      <aside
        id="mm-primary-sidebar"
        className={`mm-sidebar${sidebarOpen ? " mm-sidebar--open" : ""}${sidebarCollapsed ? " mm-sidebar--collapsed" : ""}`}
        aria-label="Product"
      >
        <BrandHeaderLink to="/" productTitle={productTitle} />
        <button
          type="button"
          className="mm-sidebar-collapse"
          data-testid="sidebar-collapse"
          aria-label={
            sidebarCollapsed ? "Expand navigation" : "Collapse navigation"
          }
          aria-expanded={!sidebarCollapsed}
          onClick={() => setSidebarCollapsed((value) => !value)}
        >
          <span className="mm-sidebar-collapse__icon" aria-hidden="true">
            {sidebarCollapsed ? (
              <NavIconChevronRight />
            ) : (
              <NavIconChevronLeft />
            )}
          </span>
          <span className="mm-sidebar-collapse__label">
            {sidebarCollapsed ? "Expand" : "Collapse"}
          </span>
        </button>
        <nav className="mm-sidebar-nav" aria-label="Primary">
          <p className="mm-sidebar-section-label">Overview</p>
          <NavLink
            to="/"
            end
            className={sidebarNavClass}
            title="Dashboard"
            onClick={() => setSidebarOpen(false)}
          >
            <span className="mm-sidebar-link-icon" aria-hidden="true">
              <NavIconDashboard />
            </span>
            <span className="mm-sidebar-link-label">Dashboard</span>
          </NavLink>
          <NavLink
            to="/activity"
            className={sidebarNavClass}
            title="Activity"
            onClick={() => setSidebarOpen(false)}
          >
            <span className="mm-sidebar-link-icon" aria-hidden="true">
              <NavIconActivity />
            </span>
            <span className="mm-sidebar-link-label">Activity</span>
          </NavLink>

          <p className="mm-sidebar-section-label">Modules</p>
          <NavLink
            to="/refiner"
            className={sidebarNavClass}
            title="Refiner"
            onClick={() => setSidebarOpen(false)}
          >
            <span className="mm-sidebar-link-icon" aria-hidden="true">
              <NavIconRefiner />
            </span>
            <span className="mm-sidebar-link-label">Refiner</span>
          </NavLink>
          <NavLink
            to="/pruner"
            className={sidebarNavClass}
            title="Pruner"
            onClick={() => setSidebarOpen(false)}
          >
            <span className="mm-sidebar-link-icon" aria-hidden="true">
              <NavIconPruner />
            </span>
            <span className="mm-sidebar-link-label">Pruner</span>
          </NavLink>

          <p className="mm-sidebar-section-label">System</p>
          <NavLink
            to="/settings"
            className={sidebarNavClass}
            title="Settings"
            onClick={() => setSidebarOpen(false)}
          >
            <span className="mm-sidebar-link-icon" aria-hidden="true">
              <NavIconSettings />
            </span>
            <span className="mm-sidebar-link-label">Settings</span>
          </NavLink>
        </nav>
        <div className="mm-sidebar-footer">
          <div className="mm-sidebar-footer-panel">
            <div className="mm-sidebar-meta">{productTitle}</div>
            <div
              className="mm-sidebar-version"
              title="Installed MediaMop version reported by the running server"
            >
              {appVersion ? `Version ${appVersion}` : "Version checking..."}
            </div>
            <button
              type="button"
              data-testid="sign-out"
              className="mm-sidebar-signout"
              disabled={logout.isPending}
              onClick={handleSignOut}
              title={sidebarCollapsed ? "Sign out" : undefined}
            >
              <span className="mm-sidebar-signout__icon" aria-hidden="true">
                <NavIconSignOut />
              </span>
              <span className="mm-sidebar-signout__label">
                {logout.isPending ? "Signing out…" : "Sign out"}
              </span>
            </button>
          </div>
        </div>
      </aside>
      {sidebarOpen ? (
        <button
          type="button"
          className="mm-sidebar-backdrop"
          aria-label="Close navigation"
          onClick={() => setSidebarOpen(false)}
        />
      ) : null}
      <main className="mm-main" id="mm-main-content" tabIndex={-1}>
        <div className="mm-main-inner">
          <div className="mm-shell-toolbar" aria-label="Display controls">
            <button
              type="button"
              className="mm-shell-menu-toggle"
              data-testid="shell-nav-toggle"
              aria-controls="mm-primary-sidebar"
              aria-expanded={sidebarOpen}
              onClick={() => setSidebarOpen((value) => !value)}
            >
              <span aria-hidden="true">☰</span>
              <span>Menu</span>
            </button>
            <PauseControl />
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
              <span className="mm-theme-toggle__label">
                {theme === "dark" ? "Dark" : "Light"}
              </span>
            </button>
          </div>
          <Outlet />
        </div>
      </main>
    </div>
  );
}
