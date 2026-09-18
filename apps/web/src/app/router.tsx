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

// Every route below is an address Weir 3.0.0 actually serves. There are deliberately no
// redirects from addresses earlier versions used: the `refiner` redirect and the MovedTo
// helper went when the #578 rename turned the redirect into a route pointing at itself, and
// `/dashboard` — the page #459 folded into Home — has gone with them. 3.0.0 is a breaking
// release with no installs to migrate, so an old bookmark gets the Not found page rather than
// a silent rewrite that then has to be carried forever. The one `Navigate` left is the
// signed-out catch-all, which is authentication, not history.
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
                  Component: (await import("../pages/home/home-page")).HomePage,
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
                path: "processing",
                lazy: async () => ({
                  Component: (
                    await import("../pages/processing/processing-page")
                  ).ProcessingPage,
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
