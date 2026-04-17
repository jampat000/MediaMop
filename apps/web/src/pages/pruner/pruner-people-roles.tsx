/** Wire tokens stored per scope (API + backend). */
import { MmOnOffSwitch } from "../../components/ui/mm-on-off-switch";

export const PRUNER_PEOPLE_ROLE_IDS = ["cast", "director", "writer", "producer", "guest_star"] as const;
export type PrunerPeopleRoleId = (typeof PRUNER_PEOPLE_ROLE_IDS)[number];

const ROLE_LABELS: Record<PrunerPeopleRoleId, string> = {
  cast: "Cast (actors)",
  director: "Directors",
  writer: "Writers",
  producer: "Producers",
  guest_star: "Guest stars",
};

const PLEX_UNAVAILABLE: ReadonlySet<PrunerPeopleRoleId> = new Set(["producer", "guest_star"]);

export const DEFAULT_PRUNER_PEOPLE_ROLES: PrunerPeopleRoleId[] = ["cast"];

export function normalizePeopleRolesFromApi(raw: string[] | undefined | null): PrunerPeopleRoleId[] {
  const out: PrunerPeopleRoleId[] = [];
  const seen = new Set<string>();
  for (const id of PRUNER_PEOPLE_ROLE_IDS) {
    if (raw?.some((x) => x.trim().toLowerCase() === id) && !seen.has(id)) {
      seen.add(id);
      out.push(id);
    }
  }
  return out.length ? out : [...DEFAULT_PRUNER_PEOPLE_ROLES];
}

/** Plex PATCH: omit tags Plex cannot supply (greyed UI). */
export function peopleRolesForPlexPersist(roles: readonly PrunerPeopleRoleId[]): PrunerPeopleRoleId[] {
  return roles.filter((r) => !PLEX_UNAVAILABLE.has(r));
}

function persistableRolesEmpty(roles: readonly PrunerPeopleRoleId[], variant: "emby-jellyfin" | "plex"): boolean {
  const persistable =
    variant === "plex" ? roles.filter((r) => !PLEX_UNAVAILABLE.has(r)) : [...roles];
  return persistable.length === 0;
}

type PrunerPeopleRoleCheckboxesProps = {
  value: PrunerPeopleRoleId[];
  onChange: (next: PrunerPeopleRoleId[]) => void;
  disabled: boolean;
  variant: "emby-jellyfin" | "plex";
  /** Shown when UI coerced empty selection back to cast. */
  coerceCastMsg: string | null;
  onClearCoerceMsg: () => void;
  onCoercedToCast?: () => void;
  testId?: string;
};

export function PrunerPeopleRoleCheckboxes({
  value,
  onChange,
  disabled,
  variant,
  coerceCastMsg,
  onClearCoerceMsg,
  onCoercedToCast,
  testId,
}: PrunerPeopleRoleCheckboxesProps) {
  const isPlex = variant === "plex";
  const baseTestId = testId ?? "pruner-people-role-toggles";

  function setRoleEnabled(id: PrunerPeopleRoleId, enabled: boolean) {
    onClearCoerceMsg();
    if (isPlex && PLEX_UNAVAILABLE.has(id)) return;

    let next: PrunerPeopleRoleId[];
    if (enabled) {
      next = value.includes(id) ? value : [...value, id];
    } else {
      next = value.filter((x) => x !== id);
    }

    if (persistableRolesEmpty(next, variant)) {
      onCoercedToCast?.();
      onChange([...DEFAULT_PRUNER_PEOPLE_ROLES]);
      return;
    }
    onChange(next);
  }

  const helper =
    variant === "plex"
      ? "Only people matching the selected roles will be used."
      : "Only people matching the selected roles will be used. Uses cast when nothing is selected.";

  return (
    <div className="space-y-4" data-testid={baseTestId}>
      <p className="text-xs font-medium text-[var(--mm-text2)]">Match people in these credit roles</p>
      <div className="space-y-5">
        {PRUNER_PEOPLE_ROLE_IDS.map((id) => {
          const grey = isPlex && PLEX_UNAVAILABLE.has(id);
          const label =
            id === "producer" && grey
              ? "Producers (not available on Plex)"
              : id === "guest_star" && grey
                ? "Guest stars (not available on Plex)"
                : ROLE_LABELS[id];
          const roleOn = value.includes(id);
          return (
            <MmOnOffSwitch
              key={id}
              id={`${baseTestId}-${id}`}
              label={label}
              enabled={grey ? false : roleOn}
              disabled={disabled || grey}
              onChange={(v) => setRoleEnabled(id, v)}
            />
          );
        })}
      </div>
      <p className="text-xs text-[var(--mm-text3)]">{helper}</p>
      {coerceCastMsg ? (
        <p className="text-xs text-amber-600/95" role="status">
          {coerceCastMsg}
        </p>
      ) : null}
    </div>
  );
}
