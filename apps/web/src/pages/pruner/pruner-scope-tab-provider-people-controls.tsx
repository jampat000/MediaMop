import { PrunerPeopleRoleCheckboxes } from "./pruner-people-roles";
import type { PrunerScopeProviderSubsectionProps } from "./pruner-scope-tab-provider-controls";

export function renderProviderPeopleControls(
  props: PrunerScopeProviderSubsectionProps,
) {
  const {
    scope,
    instanceId,
    showInteractiveControls,
    peopleText,
    setPeopleText,
    busy,
    scopeRow,
    peopleRoles,
    setPeopleRoles,
    isPlex,
  } = props;
  return (
    <div className="space-y-3">
      <label
        className="block text-sm font-medium text-[var(--mm-text1)]"
        htmlFor={`pruner-people-names-${scope}-${instanceId}`}
      >
        Names
      </label>
      {showInteractiveControls ? (
        <textarea
          id={`pruner-people-names-${scope}-${instanceId}`}
          rows={5}
          className="mm-input min-h-[7rem] w-full resize-y font-sans text-sm"
          placeholder="e.g. Alex Carter, Jordan Lee (comma or one per line)"
          value={peopleText}
          disabled={busy}
          onChange={(e) => setPeopleText(e.target.value)}
        />
      ) : (
        <p className="whitespace-pre-wrap text-xs text-[var(--mm-text2)]">
          {(scopeRow?.preview_include_people ?? []).join("\n") || "—"}
        </p>
      )}
      <p className="text-xs text-[var(--mm-text3)]">
        Leave blank to use no name filter.
      </p>
      {showInteractiveControls ? (
        <PrunerPeopleRoleCheckboxes
          value={peopleRoles}
          onChange={setPeopleRoles}
          disabled={busy}
          variant={isPlex ? "plex" : "emby-jellyfin"}
          testId={`pruner-provider-inline-people-roles-${instanceId}-${scope}`}
        />
      ) : (
        <p className="text-xs text-[var(--mm-text2)]">
          Roles:{" "}
          <strong>
            {(scopeRow?.preview_include_people_roles ?? []).length
              ? (scopeRow?.preview_include_people_roles ?? []).join(", ")
              : "all credits"}
          </strong>
        </p>
      )}
    </div>
  );
}
