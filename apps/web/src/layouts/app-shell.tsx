import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { BrandHeaderLink } from "../components/brand/brand-header-link";
import { NavIconDashboard, NavIconSettings } from "../components/shell/nav-icons";
import { WEB_APP_VERSION } from "../lib/app-meta";
import { useLogoutMutation } from "../lib/auth/queries";

export function AppShell() {
  const navigate = useNavigate();
  const logout = useLogoutMutation();

  return (
    <div className="mb-app-layout">
      <aside className="mb-sidebar" aria-label="Product">
        <BrandHeaderLink to="/app" />
        <nav className="mb-sidebar-nav" aria-label="Primary">
          <NavLink
            to="/app"
            end
            className={({ isActive }) => (isActive ? "mb-sidebar-link active" : "mb-sidebar-link")}
          >
            <span className="mb-sidebar-link-icon" aria-hidden="true">
              <NavIconDashboard />
            </span>
            <span className="mb-sidebar-link-label">Dashboard</span>
          </NavLink>
          <div className="mb-sidebar-divider" aria-hidden="true" />
          <NavLink
            to="/app/settings"
            className={({ isActive }) => (isActive ? "mb-sidebar-link active" : "mb-sidebar-link")}
          >
            <span className="mb-sidebar-link-icon" aria-hidden="true">
              <NavIconSettings />
            </span>
            <span className="mb-sidebar-link-label">Settings</span>
          </NavLink>
        </nav>
        <div className="mb-sidebar-footer">
          <div className="mb-sidebar-footer-panel">
            <div className="mb-sidebar-meta">MediaMop</div>
            <div className="mb-sidebar-version" title="Web shell version (package.json)">
              Web {WEB_APP_VERSION}
            </div>
            <button
              type="button"
              data-testid="sign-out"
              className="mb-sidebar-signout"
              disabled={logout.isPending}
              onClick={() => {
                void logout.mutateAsync().then(() => navigate("/login", { replace: true }));
              }}
            >
              {logout.isPending ? "Signing out…" : "Sign out"}
            </button>
          </div>
        </div>
      </aside>
      <main className="mb-main" id="mb-main-content" tabIndex={-1}>
        <div className="mb-main-inner">
          <Outlet />
        </div>
      </main>
    </div>
  );
}
