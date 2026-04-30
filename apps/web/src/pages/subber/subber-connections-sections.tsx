import type { ReactNode } from "react";

type SubberConnectionSectionProps = {
  children: ReactNode;
};

export function SonarrConnectionSection({
  children,
}: SubberConnectionSectionProps) {
  return <>{children}</>;
}

export function RadarrConnectionSection({
  children,
}: SubberConnectionSectionProps) {
  return <>{children}</>;
}

export function PathMappingSection({ children }: SubberConnectionSectionProps) {
  return <>{children}</>;
}

export function SyncActionsSection({ children }: SubberConnectionSectionProps) {
  return <>{children}</>;
}
