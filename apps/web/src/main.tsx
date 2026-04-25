import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { AppRouter } from "./app/router";
import { AppProviders } from "./app/providers";
import { applyAppThemeToDocument, readStoredAppTheme } from "./lib/ui/app-theme";
import { applyDisplayDensityToDocument, readStoredDisplayDensity } from "./lib/ui/display-density";
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
      <AppRouter />
    </AppProviders>
  </StrictMode>,
);
