import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { BrandHeaderLink } from "../components/brand/brand-header-link";
import { NavIconDashboard, NavIconSettings } from "../components/shell/nav-icons";
import { WEB_APP_VERSION } from "../lib/app-meta";
import { useLogoutMutation } from "../lib/auth/queries";

export function AppShell() {
  const navigate = useNavigate();
  const logout = useLogoutMutation();

  return (
    <div className="mm-app-layout">
      <aside className="mm-sidebar" aria-label="Product">
        <BrandHeaderLink to="/app" />
        <nav className="mm-sidebar-nav" aria-label="Primary">
          <NavLink
            to="/app"
            end
            className={({ isActive }) => (isActive ? "mm-sidebar-link active" : "mm-sidebar-link")}
          >
            <span className="mm-sidebar-link-icon" aria-hidden="true">
              <NavIconDashboard />
            </span>
            <span className="mm-sidebar-link-label">Dashboard</span>
          </NavLink>
          <div className="mm-sidebar-divider" aria-hidden="true" />
          <NavLink
            to="/app/settings"
            className={({ isActive }) => (isActive ? "mm-sidebar-link active" : "mm-sidebar-link")}
          >
            <span className="mm-sidebar-link-icon" aria-hidden="true">
              <NavIconSettings />
            </span>
            <span className="mm-sidebar-link-label">Settings</span>
          </NavLink>
        </nav>
        <div className="mm-sidebar-footer">
          <div className="mm-sidebar-footer-panel">
            <div className="mm-sidebar-meta">MediaMop</div>
            <div className="mm-sidebar-version" title="Web shell version (package.json)">
              Web {WEB_APP_VERSION}
            </div>
            <button
              type="button"
              data-testid="sign-out"
              className="mm-sidebar-signout"
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
      <main className="mm-main" id="mm-main-content" tabIndex={-1}>
        <div className="mm-main-inner">
          <Outlet />
        </div>
      </main>
    </div>
  );
}
