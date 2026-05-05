import { mmActionButtonClass } from "../../lib/ui/mm-control-roles";
import { PrunerProviderSection } from "./pruner-scope-tab-sections";
import {
  renderProviderFiltersControls,
  renderProviderRulesControls,
  type PrunerScopeProviderSubsectionProps,
} from "./pruner-scope-tab-provider-controls";
import { renderProviderPeopleControls } from "./pruner-scope-tab-provider-people-controls";

function ProviderSaveFooter(props: {
  showInteractiveControls: boolean;
  saveDisabled: boolean;
  busy: boolean;
  saveLabel: string;
  onSave: () => Promise<void>;
  bundleMsg: string | null;
  err: string | null;
}) {
  const {
    showInteractiveControls,
    saveDisabled,
    busy,
    saveLabel,
    onSave,
    bundleMsg,
    err,
  } = props;
  if (showInteractiveControls) {
    return (
      <div className="mm-card-action-footer">
        <button
          type="button"
          className={mmActionButtonClass({
            variant: "primary",
            disabled: saveDisabled,
          })}
          disabled={saveDisabled}
          onClick={() => void onSave()}
        >
          {busy ? "Saving..." : saveLabel}
        </button>
        {bundleMsg ? (
          <p className="text-sm text-green-600">{bundleMsg}</p>
        ) : null}
        {err ? (
          <p className="text-sm text-red-600" role="alert">
            {err}
          </p>
        ) : null}
      </div>
    );
  }
  return (
    <>
      {bundleMsg ? (
        <p className="mt-3 text-sm text-green-600">{bundleMsg}</p>
      ) : null}
      {err ? (
        <p className="mt-2 text-sm text-red-600" role="alert">
          {err}
        </p>
      ) : null}
    </>
  );
}

export function PrunerScopeProviderSubsection(
  props: PrunerScopeProviderSubsectionProps,
) {
  const {
    scope,
    provSub,
    disabledMode,
    isPlex,
    busy,
    showInteractiveControls,
    saveProviderTvRulesBundle,
    saveProviderMoviesRulesBundle,
    saveProviderFiltersBundle,
    saveProviderPeopleBundle,
    bundleMsg,
    err,
  } = props;

  if (provSub === "rules") {
    const saveLabel = scope === "tv" ? "Save TV rules" : "Save Movies rules";
    const onSave =
      scope === "tv"
        ? saveProviderTvRulesBundle
        : saveProviderMoviesRulesBundle;
    const saveDisabled =
      busy || !showInteractiveControls || (isPlex && scope === "tv");
    return (
      <PrunerProviderSection scope={scope} section="rules">
        <fieldset
          disabled={Boolean(disabledMode)}
          className="flex min-h-0 flex-1 flex-col"
        >
          <div className="mm-card-action-body min-h-0 flex-1">
            {renderProviderRulesControls(props)}
          </div>
          <ProviderSaveFooter
            showInteractiveControls={showInteractiveControls}
            saveDisabled={saveDisabled}
            busy={busy}
            saveLabel={saveLabel}
            onSave={onSave}
            bundleMsg={bundleMsg}
            err={err}
          />
        </fieldset>
      </PrunerProviderSection>
    );
  }

  if (provSub === "filters") {
    const saveLabel =
      scope === "tv" ? "Save TV filters" : "Save Movies filters";
    return (
      <PrunerProviderSection scope={scope} section="filters">
        <fieldset
          disabled={Boolean(disabledMode)}
          className="flex min-h-0 flex-1 flex-col"
        >
          <div className="mm-card-action-body min-h-0 flex-1">
            {renderProviderFiltersControls(props)}
          </div>
          <ProviderSaveFooter
            showInteractiveControls={showInteractiveControls}
            saveDisabled={busy}
            busy={busy}
            saveLabel={saveLabel}
            onSave={saveProviderFiltersBundle}
            bundleMsg={bundleMsg}
            err={err}
          />
        </fieldset>
      </PrunerProviderSection>
    );
  }

  if (provSub === "people") {
    const saveLabel = scope === "tv" ? "Save TV people" : "Save Movies people";
    return (
      <PrunerProviderSection scope={scope} section="people">
        <fieldset
          disabled={Boolean(disabledMode)}
          className="flex min-h-0 flex-1 flex-col"
        >
          <div className="mm-card-action-body min-h-0 flex-1">
            {renderProviderPeopleControls(props)}
          </div>
          <ProviderSaveFooter
            showInteractiveControls={showInteractiveControls}
            saveDisabled={busy}
            busy={busy}
            saveLabel={saveLabel}
            onSave={saveProviderPeopleBundle}
            bundleMsg={bundleMsg}
            err={err}
          />
        </fieldset>
      </PrunerProviderSection>
    );
  }

  return (
    <p
      className="text-sm text-red-600"
      role="alert"
      data-testid="pruner-provider-subsection-missing"
    >
      Something is misconfigured. Try reloading the page or opening the provider
      tab again.
    </p>
  );
}
