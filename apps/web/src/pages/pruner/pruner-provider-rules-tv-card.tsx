import { MmOnOffSwitch } from "../../components/ui/mm-on-off-switch";
import { mmActionButtonClass } from "../../lib/ui/mm-control-roles";
import { PrunerGenreMultiSelect } from "./pruner-genre-multi-select";
import { PrunerPeopleRoleCheckboxes, type PrunerPeopleRoleId } from "./pruner-people-roles";
import { PrunerStudioMultiSelect } from "./pruner-studio-multi-select";
import { YearRange } from "./pruner-provider-people-card";

type PrunerProviderRulesTvCardProps = {
  provider: "emby" | "jellyfin" | "plex";
  instanceId: number;
  isPlex: boolean;
  narrowingLabelClass: string;
  tvControlsDisabled: boolean;
  watchedTv: boolean;
  setWatchedTv: (v: boolean) => void;
  neverTvDays: string;
  setNeverTvDays: (v: string) => void;
  missingPrimaryTv: boolean;
  setMissingPrimaryTv: (v: boolean) => void;
  genreTv: string[];
  setGenreTv: (v: string[]) => void;
  tvPeople: string;
  setTvPeople: (v: string) => void;
  tvRoles: PrunerPeopleRoleId[];
  setTvRoles: (v: PrunerPeopleRoleId[]) => void;
  studioTv: string[];
  setStudioTv: (v: string[]) => void;
  yearMinTv: string;
  setYearMinTv: (v: string) => void;
  yearMaxTv: string;
  setYearMaxTv: (v: string) => void;
  canOperate: boolean;
  saveDisabledTv: boolean;
  saveTv: () => Promise<void>;
  busyTv: boolean;
  msgTv: string | null;
  errTv: string | null;
};

export function PrunerProviderRulesTvCard({
  provider,
  instanceId,
  isPlex,
  narrowingLabelClass,
  tvControlsDisabled,
  watchedTv,
  setWatchedTv,
  neverTvDays,
  setNeverTvDays,
  missingPrimaryTv,
  setMissingPrimaryTv,
  genreTv,
  setGenreTv,
  tvPeople,
  setTvPeople,
  tvRoles,
  setTvRoles,
  studioTv,
  setStudioTv,
  yearMinTv,
  setYearMinTv,
  yearMaxTv,
  setYearMaxTv,
  canOperate,
  saveDisabledTv,
  saveTv,
  busyTv,
  msgTv,
  errTv,
}: PrunerProviderRulesTvCardProps) {
  return (
    <fieldset
      disabled={tvControlsDisabled}
      className="mm-card mm-dash-card min-w-0 border border-[var(--mm-border)] bg-[var(--mm-card-bg)] p-5 sm:p-6"
    >
      <div
        className="flex min-h-0 min-w-0 flex-1 flex-col"
        data-testid={`pruner-provider-tv-config-${provider}`}
      >
        <div className="mm-card-action-body min-h-0 flex-1">
          <div className="space-y-1 border-b border-[var(--mm-border)] pb-2">
            <span className="text-sm font-semibold uppercase tracking-wide text-[var(--mm-text1)]">
              TV
            </span>
          </div>
          <p className={narrowingLabelClass}>Rules</p>
          {isPlex ? (
            <div
              className="rounded-md border border-amber-600/40 bg-amber-950/20 px-4 py-3 text-sm text-[var(--mm-text)]"
              data-testid="pruner-plex-tv-rules-scope-note"
              role="note"
            >
              <p className="font-semibold text-amber-100">Plex TV — limited options</p>
              <p className="mt-2 text-sm text-[var(--mm-text2)]">
                {"Plex doesn't provide a watched signal for TV shows, so only the missing poster rule is available here. Watched TV cleanup is not supported on Plex."}
              </p>
            </div>
          ) : null}
          {!isPlex ? (
            <>
              <MmOnOffSwitch
                id={`pruner-op-tv-watched-${provider}`}
                label="Delete TV episodes you have already watched"
                enabled={watchedTv}
                disabled={tvControlsDisabled}
                onChange={setWatchedTv}
              />
              <label className="block text-sm text-[var(--mm-text1)]">
                <span className="mb-1 block text-xs text-[var(--mm-text3)]">
                  Delete TV shows not watched in the last ___ days (0 = off)
                </span>
                <input
                  type="number"
                  min={0}
                  max={3650}
                  className="mm-input w-full max-w-xs"
                  value={neverTvDays}
                  onChange={(e) => setNeverTvDays(e.target.value)}
                  disabled={tvControlsDisabled}
                />
              </label>
            </>
          ) : null}
          <MmOnOffSwitch
            id={`pruner-op-tv-missing-${provider}`}
            label="Delete TV items missing a main poster or episode image"
            enabled={missingPrimaryTv}
            disabled={tvControlsDisabled}
            onChange={setMissingPrimaryTv}
          />

          <div className="border-t border-[var(--mm-border)] pt-4 mt-1" aria-hidden="true" />

          <div className="space-y-1">
            <span className="mb-1 block text-xs font-medium text-[var(--mm-text3)]">
              Delete content in these genres
            </span>
            <PrunerGenreMultiSelect
              value={genreTv}
              onChange={setGenreTv}
              disabled={tvControlsDisabled}
              testId={`pruner-rules-genre-tv-${provider}`}
            />
          </div>
          <label
            className="block text-sm text-[var(--mm-text2)]"
            data-testid={`pruner-provider-tv-people-${provider}`}
          >
            <span className="mb-1 block text-xs font-medium text-[var(--mm-text3)]">
              Delete content involving these people
            </span>
            <textarea
              className="mm-input min-h-[6rem] w-full font-sans text-sm"
              rows={5}
              placeholder="e.g. Alex Carter, Jordan Lee (comma or one per line)"
              value={tvPeople}
              disabled={tvControlsDisabled}
              onChange={(e) => setTvPeople(e.target.value)}
            />
            <span className="mt-1 block text-xs text-[var(--mm-text3)]">
              Leave empty to skip.
            </span>
          </label>
          <PrunerPeopleRoleCheckboxes
            value={tvRoles}
            onChange={setTvRoles}
            disabled={tvControlsDisabled}
            variant={isPlex ? "plex" : "emby-jellyfin"}
            testId={`pruner-provider-tv-people-roles-${provider}`}
            rolesHeading="Check these credits when matching names"
          />
          <div className="space-y-1">
            <span className="mb-1 block text-xs font-medium text-[var(--mm-text3)]">
              Delete content from these studios
            </span>
            <PrunerStudioMultiSelect
              value={studioTv}
              onChange={setStudioTv}
              disabled={tvControlsDisabled}
              instanceId={instanceId}
              scope="tv"
              testId={`pruner-rules-studio-tv-${provider}`}
            />
          </div>
          <YearRange
            min={yearMinTv}
            max={yearMaxTv}
            onMin={setYearMinTv}
            onMax={setYearMaxTv}
            disabled={tvControlsDisabled}
            title="Delete content released in these years"
            helperText="Leave empty to skip."
          />
        </div>
        <div className="mm-card-action-footer">
          {canOperate ? (
            <button
              type="button"
              className={mmActionButtonClass({
                variant: "primary",
                disabled: saveDisabledTv,
              })}
              disabled={saveDisabledTv}
              onClick={() => void saveTv()}
            >
              {busyTv ? "Saving..." : "Save TV settings"}
            </button>
          ) : null}
          {msgTv ? (
            <p className="text-sm text-green-600" role="status">
              {msgTv}
            </p>
          ) : null}
          {errTv ? (
            <p className="text-sm text-red-500" role="alert">
              {errTv}
            </p>
          ) : null}
        </div>
      </div>
    </fieldset>
  );
}
