import type { ReactNode } from "react";

type ProviderSectionProps = {
  scope: "tv" | "movies";
  section: "rules" | "filters" | "people";
  children: ReactNode;
};

export function PrunerRulesSection({ children }: { children: ReactNode }) {
  return <>{children}</>;
}

export function PrunerFiltersSection({ children }: { children: ReactNode }) {
  return <>{children}</>;
}

export function PrunerScheduleSection({ children }: { children: ReactNode }) {
  return <>{children}</>;
}

export function PrunerApplySection({ children }: { children: ReactNode }) {
  return <>{children}</>;
}

export function PrunerProviderSection({ scope, section, children }: ProviderSectionProps) {
  return (
    <section className="flex min-h-0 w-full min-w-0 flex-1 flex-col" data-testid={`pruner-provider-subsection-${section}-${scope}`}>
      {children}
    </section>
  );
}
