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
            retry: false,
            refetchOnWindowFocus: true,
          },
        },
      }),
  );
  useEffect(() => {
    setUnauthorizedHandler(() => {
      client.setQueryData(qk.me, null);
      void client.cancelQueries({ queryKey: qk.me });
      if (window.location.pathname.startsWith("/app")) {
        window.location.assign("/login?session=expired");
      }
    });
    return () => setUnauthorizedHandler(null);
  }, [client]);

  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}
