import { useEffect, useMemo, useRef, useState } from "react";
import { mmSectionTabClass } from "../../lib/ui/mm-control-roles";
import type { PrunerServerInstance } from "../../lib/pruner/api";
import {
  PrunerProviderRulesCard,
  type PrunerProviderRulesCardHandle,
} from "./pruner-provider-operator-workspace";
import { PrunerConnectionCredentialPanel } from "./pruner-connection-credential-panel";
import { PrunerGlobalScheduleRow } from "./pruner-global-schedule-row";
import type {
  ProviderTab,
  ProviderWorkspaceSection,
} from "./pruner-page-types";
import { providerDisabledInstance, providerLabel } from "./pruner-page-utils";

type ProviderConfigurationWorkspaceProps = {
  provider: ProviderTab;
  allInstances: PrunerServerInstance[];
  initialSection?: ProviderWorkspaceSection;
};

export function ProviderConfigurationWorkspace({
  provider,
  allInstances,
  initialSection = "connection",
}: ProviderConfigurationWorkspaceProps) {
  const providerName = providerLabel(provider);
  const providerInstances = useMemo(
    () => allInstances.filter((x) => x.provider === provider),
    [allInstances, provider],
  );
  const [selectedInstanceId, setSelectedInstanceId] = useState<number | null>(
    providerInstances[0]?.id ?? null,
  );
  const [providerSection, setProviderSection] =
    useState<ProviderWorkspaceSection>(initialSection);
  const selectedInstance =
    providerInstances.find((x) => x.id === selectedInstanceId) ??
    providerInstances[0];
  const rulesCardRef = useRef<PrunerProviderRulesCardHandle>(null);

  useEffect(() => {
    setSelectedInstanceId((prev) => {
      if (prev != null && providerInstances.some((x) => x.id === prev))
        return prev;
      return providerInstances[0]?.id ?? null;
    });
  }, [provider, providerInstances]);

  useEffect(() => {
    setProviderSection(initialSection);
  }, [provider, initialSection]);

  const disabledCtx = {
    instanceId: 0,
    instance: providerDisabledInstance(provider),
  } as const;
  const instanceSelection = {
    selectedId: selectedInstanceId,
    onSelectedIdChange: setSelectedInstanceId,
  };

  return (
    <section
      className="mm-bubble-stack"
      data-testid={`pruner-provider-tab-${provider}`}
    >
      {providerInstances.length > 1 ? (
        <label className="block max-w-md text-sm text-[var(--mm-text2)]">
          <span className="mb-1 block text-xs text-[var(--mm-text3)]">
            Server
          </span>
          <select
            className="mm-input mt-1 w-full"
            value={selectedInstance?.id ?? ""}
            onChange={(e) => setSelectedInstanceId(Number(e.target.value))}
          >
            {providerInstances.map((inst) => (
              <option key={inst.id} value={inst.id}>
                {inst.display_name}
              </option>
            ))}
          </select>
        </label>
      ) : null}

      <nav
        className="flex flex-wrap gap-2 border-b border-[var(--mm-border)] pb-3"
        aria-label={`${providerName} configuration sections`}
        data-testid={`pruner-provider-subnav-${provider}`}
      >
        {(
          [
            ["connection", "Connection"],
            ["cleanup", "Cleanup"],
            ["schedule", "Schedule"],
          ] as const
        ).map(([id, label]) => (
          <button
            key={id}
            type="button"
            className={mmSectionTabClass(providerSection === id)}
            aria-current={providerSection === id ? "page" : undefined}
            onClick={() => setProviderSection(id)}
          >
            {label}
          </button>
        ))}
      </nav>

      <div data-testid={`pruner-provider-sections-${provider}`}>
        {providerSection === "connection" ? (
          <PrunerConnectionCredentialPanel
            provider={provider}
            allInstances={allInstances}
            instanceSelection={instanceSelection}
          />
        ) : null}

        {providerSection === "cleanup" || providerSection === "schedule" ? (
          <div
            className={providerSection !== "cleanup" ? "hidden" : undefined}
            data-testid={
              providerSection === "cleanup"
                ? "pruner-provider-cleanup-wrap"
                : undefined
            }
            aria-hidden={providerSection !== "cleanup"}
          >
            <PrunerProviderRulesCard
              ref={rulesCardRef}
              provider={provider}
              instanceId={selectedInstance?.id ?? 0}
              instance={selectedInstance ?? disabledCtx.instance}
            />
          </div>
        ) : null}

        {providerSection === "schedule" ? (
          <div
            className="mm-dash-grid"
            data-testid="pruner-provider-schedule-wrap"
          >
            <PrunerGlobalScheduleRow
              provider={provider}
              scope="tv"
              instance={selectedInstance}
              ensureScopeSaved={async () => {
                await rulesCardRef.current?.ensureTvSaved();
              }}
            />
            <PrunerGlobalScheduleRow
              provider={provider}
              scope="movies"
              instance={selectedInstance}
              ensureScopeSaved={async () => {
                await rulesCardRef.current?.ensureMoviesSaved();
              }}
            />
          </div>
        ) : null}
      </div>
    </section>
  );
}
