import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "@fontsource/outfit/400.css";
import "@fontsource/outfit/500.css";
import "@fontsource/outfit/600.css";
import "@fontsource/outfit/700.css";
import { AppRouter } from "./app/router";
import { AppProviders } from "./app/providers";
import { StartupGate } from "./app/startup-gate";
import { AppErrorScreen, ErrorBoundary } from "./components/error-boundary";
import {
  applyAppThemeToDocument,
  readStoredAppTheme,
} from "./lib/ui/app-theme";
import {
  applyDisplayDensityToDocument,
  readStoredDisplayDensity,
} from "./lib/ui/display-density";
import "./index.css";

applyAppThemeToDocument(readStoredAppTheme());
applyDisplayDensityToDocument(readStoredDisplayDensity());

const el = document.getElementById("root");
if (!el) {
  throw new Error("Root element #root not found");
}

createRoot(el).render(
  <StrictMode>
    <AppProviders>
      <ErrorBoundary fallback={(error) => <AppErrorScreen error={error} />}>
        <StartupGate>
          <AppRouter />
        </StartupGate>
      </ErrorBoundary>
    </AppProviders>
  </StrictMode>,
);
