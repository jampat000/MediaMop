import {
  Navigate,
  RouterProvider,
  createBrowserRouter,
  useLocation,
} from "react-router-dom";
import { RouteErrorScreen } from "../components/error-boundary";
import { AppShell } from "../layouts/app-shell";
import { RequireAuth } from "./require-auth";
import { RequireSetupWizard } from "./require-setup-wizard";
import { AppHydrateFallback } from "./hydrate-fallback";

const routeErrorElement = <RouteErrorScreen />;

/** An old address that moved: keep the query (`?tab=…`) and hash so deep links still land. */
function MovedTo({ path }: { path: string }) {
  const location = useLocation();
  return <Navigate to={`${path}${location.search}${location.hash}`} replace />;
}

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
                // What Weir currently has custody of. The landing screen, because it is
                // the question an operator actually opens the app to answer (#463).
                index: true,
                lazy: async () => ({
                  Component: (await import("../pages/in-hand/in-hand-page"))
                    .InHandPage,
                }),
                errorElement: routeErrorElement,
              },
              {
                // The dashboard folded into In hand (#459). Old bookmarks land there.
                path: "dashboard",
                element: <Navigate to="/" replace />,
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
                // "Refiner" became the whole app, so its page is now Processing.
                path: "refiner",
                element: <MovedTo path="/processing" />,
              },
              {
                path: "processing",
                lazy: async () => ({
                  Component: (await import("../pages/refiner/refiner-page"))
                    .RefinerPage,
                }),
                errorElement: routeErrorElement,
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
