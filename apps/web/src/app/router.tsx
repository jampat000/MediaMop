import {
  Navigate,
  RouterProvider,
  createBrowserRouter,
} from "react-router-dom";
import { RouteErrorScreen } from "../components/error-boundary";
import { AppShell } from "../layouts/app-shell";
import { RequireAuth } from "./require-auth";
import { RequireSetupWizard } from "./require-setup-wizard";
import { AppHydrateFallback } from "./hydrate-fallback";

const routeErrorElement = <RouteErrorScreen />;
const router = createBrowserRouter([
  {
    path: "/login",
    lazy: async () => ({
      Component: (await import("../pages/auth/login-page")).LoginPage,
    }),
    errorElement: routeErrorElement,
    HydrateFallback: AppHydrateFallback,
  },
  {
    path: "/setup",
    lazy: async () => ({
      Component: (await import("../pages/setup/setup-page")).SetupPage,
    }),
    errorElement: routeErrorElement,
    HydrateFallback: AppHydrateFallback,
  },
  {
    path: "/",
    element: <RequireAuth />,
    errorElement: routeErrorElement,
    HydrateFallback: AppHydrateFallback,
    children: [
      {
        path: "setup-wizard",
        lazy: async () => ({
          Component: (await import("../pages/setup/setup-wizard-page"))
            .SetupWizardPage,
        }),
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
                lazy: async () => ({
                  Component: (await import("../pages/dashboard/dashboard-page"))
                    .DashboardPage,
                }),
                errorElement: routeErrorElement,
              },
              {
                path: "activity",
                lazy: async () => ({
                  Component: (await import("../pages/activity/activity-page"))
                    .ActivityPage,
                }),
                errorElement: routeErrorElement,
              },
              {
                path: "refiner",
                lazy: async () => ({
                  Component: (await import("../pages/refiner/refiner-page"))
                    .RefinerPage,
                }),
                errorElement: routeErrorElement,
              },
              {
                path: "pruner",
                errorElement: routeErrorElement,
                children: [
                  {
                    index: true,
                    lazy: async () => ({
                      Component: (
                        await import("../pages/pruner/pruner-instances-list-page")
                      ).PrunerInstancesListPage,
                    }),
                    errorElement: routeErrorElement,
                  },
                  {
                    path: "instances/:instanceId",
                    lazy: async () => ({
                      Component: (
                        await import("../pages/pruner/pruner-instance-shell")
                      ).PrunerInstanceShell,
                    }),
                    errorElement: routeErrorElement,
                    children: [
                      {
                        index: true,
                        element: <Navigate to="overview" replace />,
                      },
                      {
                        path: "overview",
                        lazy: async () => ({
                          Component: (
                            await import("../pages/pruner/pruner-instance-overview-tab")
                          ).PrunerInstanceOverviewTab,
                        }),
                        errorElement: routeErrorElement,
                      },
                      {
                        path: "tv",
                        lazy: async () => {
                          const mod =
                            await import("../pages/pruner/pruner-scope-tab");
                          return {
                            Component: () => <mod.PrunerScopeTab scope="tv" />,
                          };
                        },
                        errorElement: routeErrorElement,
                      },
                      {
                        path: "movies",
                        lazy: async () => {
                          const mod =
                            await import("../pages/pruner/pruner-scope-tab");
                          return {
                            Component: () => (
                              <mod.PrunerScopeTab scope="movies" />
                            ),
                          };
                        },
                        errorElement: routeErrorElement,
                      },
                      {
                        path: "connection",
                        lazy: async () => ({
                          Component: (
                            await import("../pages/pruner/pruner-connection-tab")
                          ).PrunerConnectionTab,
                        }),
                        errorElement: routeErrorElement,
                      },
                    ],
                  },
                ],
              },
              {
                path: "settings",
                lazy: async () => ({
                  Component: (await import("../pages/settings/settings-page"))
                    .SettingsPage,
                }),
                errorElement: routeErrorElement,
              },
              {
                path: "*",
                lazy: async () => ({
                  Component: (await import("../pages/not-found-page"))
                    .NotFoundPage,
                }),
                errorElement: routeErrorElement,
              },
            ],
          },
        ],
      },
    ],
  },
  {
    path: "*",
    element: <Navigate to="/login" replace />,
    errorElement: routeErrorElement,
  },
]);

export function AppRouter() {
  return <RouterProvider router={router} />;
}
