import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { type ReactNode, useEffect, useState } from "react";
import { setUnauthorizedHandler } from "../lib/api/client";
import { qk } from "../lib/auth/queries";

export function AppProviders({ children }: { children: ReactNode }) {
  const [client] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            staleTime: 30_000,
            retry: 1,
            refetchOnWindowFocus: true,
          },
          mutations: {
            retry: false,
          },
        },
      }),
  );
  useEffect(() => {
    setUnauthorizedHandler(() => {
      client.setQueryData(qk.me, null);
      client.setQueryData(qk.session, null);
      void client.cancelQueries({ queryKey: qk.me });
      void client.cancelQueries({ queryKey: qk.session });
      if (window.location.pathname.startsWith("/app")) {
        window.history.replaceState(null, "", "/login?session=expired");
        window.dispatchEvent(new PopStateEvent("popstate"));
      }
    });
    return () => setUnauthorizedHandler(null);
  }, [client]);

  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}
