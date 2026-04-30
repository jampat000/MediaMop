import { Navigate, RouterProvider, createBrowserRouter } from "react-router-dom";
import { RouteErrorScreen } from "../components/error-boundary";
import { AppShell } from "../layouts/app-shell";
import { RequireAuth } from "./require-auth";
import { RequireSetupWizard } from "./require-setup-wizard";

const routeErrorElement = <RouteErrorScreen />;
const router = createBrowserRouter([
  {
    path: "/",
    lazy: async () => ({ Component: (await import("../pages/root-entry")).RootEntry }),
    errorElement: routeErrorElement,
  },
  {
    path: "/login",
    lazy: async () => ({ Component: (await import("../pages/auth/login-page")).LoginPage }),
    errorElement: routeErrorElement,
  },
  {
    path: "/setup",
    lazy: async () => ({ Component: (await import("../pages/setup/setup-page")).SetupPage }),
    errorElement: routeErrorElement,
  },
  {
    path: "/app",
    element: <RequireAuth />,
    errorElement: routeErrorElement,
    children: [
      {
        path: "setup-wizard",
        lazy: async () => ({ Component: (await import("../pages/setup/setup-wizard-page")).SetupWizardPage }),
        errorElement: routeErrorElement,
      },
      {
        element: <RequireSetupWizard />,
        errorElement: routeErrorElement,
        children: [
          {
            element: <AppShell />,
            errorElement: routeErrorElement,
            children: [
              {
                index: true,
                lazy: async () => ({ Component: (await import("../pages/dashboard/dashboard-page")).DashboardPage }),
                errorElement: routeErrorElement,
              },
              {
                path: "activity",
                lazy: async () => ({ Component: (await import("../pages/activity/activity-page")).ActivityPage }),
                errorElement: routeErrorElement,
              },
              {
                path: "refiner",
                lazy: async () => ({ Component: (await import("../pages/refiner/refiner-page")).RefinerPage }),
                errorElement: routeErrorElement,
              },
              {
                path: "pruner",
                errorElement: routeErrorElement,
                children: [
                  {
                    index: true,
                    lazy: async () => ({
                      Component: (await import("../pages/pruner/pruner-instances-list-page")).PrunerInstancesListPage,
                    }),
                    errorElement: routeErrorElement,
                  },
                  {
                    path: "instances/:instanceId",
                    lazy: async () => ({ Component: (await import("../pages/pruner/pruner-instance-shell")).PrunerInstanceShell }),
                    errorElement: routeErrorElement,
                    children: [
                      { index: true, element: <Navigate to="overview" replace /> },
                      {
                        path: "overview",
                        lazy: async () => ({
                          Component: (await import("../pages/pruner/pruner-instance-overview-tab")).PrunerInstanceOverviewTab,
                        }),
                        errorElement: routeErrorElement,
                      },
                      {
                        path: "tv",
                        lazy: async () => {
                          const mod = await import("../pages/pruner/pruner-scope-tab");
                          return { Component: () => <mod.PrunerScopeTab scope="tv" /> };
                        },
                        errorElement: routeErrorElement,
                      },
                      {
                        path: "movies",
                        lazy: async () => {
                          const mod = await import("../pages/pruner/pruner-scope-tab");
                          return { Component: () => <mod.PrunerScopeTab scope="movies" /> };
                        },
                        errorElement: routeErrorElement,
                      },
                      {
                        path: "connection",
                        lazy: async () => ({ Component: (await import("../pages/pruner/pruner-connection-tab")).PrunerConnectionTab }),
                        errorElement: routeErrorElement,
                      },
                    ],
                  },
                ],
              },
              {
                path: "subber",
                lazy: async () => ({ Component: (await import("../pages/subber/subber-page")).SubberPage }),
                errorElement: routeErrorElement,
              },
              {
                path: "settings",
                lazy: async () => ({ Component: (await import("../pages/settings/settings-page")).SettingsPage }),
                errorElement: routeErrorElement,
              },
            ],
          },
        ],
      },
    ],
  },
  { path: "*", element: <Navigate to="/" replace />, errorElement: routeErrorElement },
]);

function RouteLoadingScreen() {
  return (
    <main className="min-h-screen bg-[var(--mm-bg)] px-6 py-10 text-[var(--mm-text)]">
      <div className="mx-auto flex min-h-[70vh] max-w-xl flex-col justify-center">
        <p className="text-xs font-semibold uppercase tracking-[0.28em] text-[var(--mm-accent)]">MediaMop</p>
        <h1 className="mt-4 text-3xl font-semibold">Loading view...</h1>
      </div>
    </main>
  );
}

export function AppRouter() {
  return <RouterProvider router={router} fallbackElement={<RouteLoadingScreen />} />;
}
