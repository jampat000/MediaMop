import { createBrowserRouter, Navigate, RouterProvider } from "react-router-dom";
import { AppShell } from "../layouts/app-shell";
import { DashboardPlaceholder } from "../pages/dashboard/dashboard-placeholder";
import { LoginPage } from "../pages/auth/login-page";
import { RootEntry } from "../pages/root-entry";
import { SettingsPlaceholder } from "../pages/settings/settings-placeholder";
import { SetupPage } from "../pages/setup/setup-page";
import { RequireAuth } from "./require-auth";

const router = createBrowserRouter([
  { path: "/", element: <RootEntry /> },
  { path: "/login", element: <LoginPage /> },
  { path: "/setup", element: <SetupPage /> },
  {
    path: "/app",
    element: <RequireAuth />,
    children: [
      {
        element: <AppShell />,
        children: [
          { index: true, element: <DashboardPlaceholder /> },
          { path: "settings", element: <SettingsPlaceholder /> },
        ],
      },
    ],
  },
  { path: "*", element: <Navigate to="/" replace /> },
]);

export function AppRouter() {
  return <RouterProvider router={router} />;
}
