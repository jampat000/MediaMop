/** Wire tokens stored per scope (API + backend). */
import { MmOnOffSwitch } from "../../components/ui/mm-on-off-switch";

export const PRUNER_PEOPLE_ROLE_IDS = ["cast", "director", "writer", "producer", "guest_star"] as const;
export type PrunerPeopleRoleId = (typeof PRUNER_PEOPLE_ROLE_IDS)[number];

const PLEX_UI_ROLE_IDS: readonly PrunerPeopleRoleId[] = ["cast", "director", "writer"];

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

/** Plex PATCH: omit tags Plex cannot supply. */
export function peopleRolesForPlexPersist(roles: readonly PrunerPeopleRoleId[]): PrunerPeopleRoleId[] {
  return roles.filter((r) => !PLEX_UNAVAILABLE.has(r));
}

/** Hydrate Plex People UI: drop roles Plex cannot supply; empty → cast default. */
export function peopleRolesForPlexUiState(raw: string[] | undefined | null): PrunerPeopleRoleId[] {
  const n = normalizePeopleRolesFromApi(raw).filter((r) => !PLEX_UNAVAILABLE.has(r));
  return n.length ? n : [...DEFAULT_PRUNER_PEOPLE_ROLES];
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
  /** Overrides the default section title above role toggles. */
  rolesHeading?: string;
  /** Extra helper line (e.g. scope-specific copy). */
  footerHelper?: string | null;
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
  rolesHeading,
  footerHelper,
}: PrunerPeopleRoleCheckboxesProps) {
  const isPlex = variant === "plex";
  const baseTestId = testId ?? "pruner-people-role-toggles";
  const roleIds: readonly PrunerPeopleRoleId[] = isPlex ? PLEX_UI_ROLE_IDS : PRUNER_PEOPLE_ROLE_IDS;

  function setRoleEnabled(id: PrunerPeopleRoleId, enabled: boolean) {
    onClearCoerceMsg();

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

  const helper = "Only applies when names are entered above. Cast is used by default if no roles are selected.";

  const heading = rolesHeading ?? "Match people in these credit roles";
  return (
    <div className="space-y-4" data-testid={baseTestId}>
      <p className="text-xs font-medium text-[var(--mm-text2)]">{heading}</p>
      <div className="space-y-4">
        {roleIds.map((id) => {
          const label = ROLE_LABELS[id];
          const roleOn = value.includes(id);
          return (
            <MmOnOffSwitch
              key={id}
              id={`${baseTestId}-${id}`}
              label={label}
              layout="inline"
              enabled={roleOn}
              disabled={disabled}
              onChange={(v) => setRoleEnabled(id, v)}
            />
          );
        })}
      </div>
      <p className="text-xs text-[var(--mm-text3)]">{helper}</p>
      {footerHelper ? <p className="text-xs text-[var(--mm-text3)]">{footerHelper}</p> : null}
      {coerceCastMsg ? (
        <p className="text-xs text-amber-600/95" role="status">
          {coerceCastMsg}
        </p>
      ) : null}
    </div>
  );
}
