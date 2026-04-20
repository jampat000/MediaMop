import { lazy, Suspense } from "react";
import { createBrowserRouter, Navigate, RouterProvider } from "react-router-dom";
import { PageLoading } from "../components/shared/page-loading";
import { AppShell } from "../layouts/app-shell";
import { ActivityPage } from "../pages/activity/activity-page";
import { DashboardPage } from "../pages/dashboard/dashboard-page";
import { FetcherPage } from "../pages/fetcher/fetcher-page";

const BrokerPage = lazy(async () => {
  const m = await import("../pages/broker/broker-page");
  return { default: m.BrokerPage };
});
import { LoginPage } from "../pages/auth/login-page";
import { RefinerPage } from "../pages/refiner/refiner-page";
import { RootEntry } from "../pages/root-entry";
import { SettingsPage } from "../pages/settings/settings-page";
import { SetupPage } from "../pages/setup/setup-page";
import { SubberPage } from "../pages/subber/subber-page";
import { PrunerConnectionTab } from "../pages/pruner/pruner-connection-tab";
import { PrunerInstanceOverviewTab } from "../pages/pruner/pruner-instance-overview-tab";
import { PrunerInstanceShell } from "../pages/pruner/pruner-instance-shell";
import { PrunerInstancesListPage } from "../pages/pruner/pruner-instances-list-page";
import { PrunerScopeTab } from "../pages/pruner/pruner-scope-tab";
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
          {
            path: "broker",
            element: (
              <Suspense fallback={<PageLoading />}>
                <BrokerPage />
              </Suspense>
            ),
          },
          { path: "fetcher", element: <FetcherPage /> },
          { path: "refiner", element: <RefinerPage /> },
          {
            path: "pruner",
            children: [
              { index: true, element: <PrunerInstancesListPage /> },
              {
                path: "instances/:instanceId",
                element: <PrunerInstanceShell />,
                children: [
                  { index: true, element: <Navigate to="overview" replace /> },
                  { path: "overview", element: <PrunerInstanceOverviewTab /> },
                  { path: "tv", element: <PrunerScopeTab scope="tv" /> },
                  { path: "movies", element: <PrunerScopeTab scope="movies" /> },
                  { path: "connection", element: <PrunerConnectionTab /> },
                ],
              },
            ],
          },
          { path: "subber", element: <SubberPage /> },
          { path: "settings", element: <SettingsPage /> },
        ],
      },
    ],
  },
  { path: "*", element: <Navigate to="/" replace /> },
]);

export function AppRouter() {
  return <RouterProvider router={router} />;
}
