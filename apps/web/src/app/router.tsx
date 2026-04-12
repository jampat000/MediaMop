import { createBrowserRouter, Navigate, RouterProvider } from "react-router-dom";
import { AppShell } from "../layouts/app-shell";
import { ActivityPage } from "../pages/activity/activity-page";
import { DashboardPage } from "../pages/dashboard/dashboard-page";
import { FetcherPage } from "../pages/fetcher/fetcher-page";
import { LoginPage } from "../pages/auth/login-page";
import { RefinerPage } from "../pages/refiner/refiner-page";
import { RootEntry } from "../pages/root-entry";
import { SettingsPlaceholder } from "../pages/settings/settings-placeholder";
import { SetupPage } from "../pages/setup/setup-page";
import { SubberPage } from "../pages/subber/subber-page";
import { TrimmerPage } from "../pages/trimmer/trimmer-page";
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
          { index: true, element: <DashboardPage /> },
          { path: "activity", element: <ActivityPage /> },
          { path: "fetcher", element: <FetcherPage /> },
          { path: "refiner", element: <RefinerPage /> },
          { path: "trimmer", element: <TrimmerPage /> },
          { path: "subber", element: <SubberPage /> },
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
