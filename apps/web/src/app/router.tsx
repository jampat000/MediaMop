import { createBrowserRouter, Navigate, RouterProvider } from "react-router-dom";
import { AppShell } from "../layouts/app-shell";
import { ActivityPlaceholder } from "../pages/activity/activity-placeholder";
import { DashboardPage } from "../pages/dashboard/dashboard-page";
import { FetcherPlaceholder } from "../pages/fetcher/fetcher-placeholder";
import { LoginPage } from "../pages/auth/login-page";
import { RefinerPlaceholder } from "../pages/refiner/refiner-placeholder";
import { RootEntry } from "../pages/root-entry";
import { SettingsPlaceholder } from "../pages/settings/settings-placeholder";
import { SetupPage } from "../pages/setup/setup-page";
import { SubtitlesPlaceholder } from "../pages/subtitles/subtitles-placeholder";
import { TrimmerPlaceholder } from "../pages/trimmer/trimmer-placeholder";
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
          { path: "activity", element: <ActivityPlaceholder /> },
          { path: "fetcher", element: <FetcherPlaceholder /> },
          { path: "refiner", element: <RefinerPlaceholder /> },
          { path: "trimmer", element: <TrimmerPlaceholder /> },
          { path: "subtitles", element: <SubtitlesPlaceholder /> },
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
