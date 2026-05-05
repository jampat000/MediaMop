import { PrunerScopeProviderSubsection } from "./pruner-scope-tab-provider-subsection";
import {
  Ctx,
  type PrunerScopeTabProps,
  usePrunerScopeTabController,
} from "./pruner-scope-tab-controller";
import { PrunerScopeTabDefaultLayout } from "./pruner-scope-tab-default-layout";

export type { Ctx };

export function PrunerScopeTab(props: PrunerScopeTabProps) {
  const c = usePrunerScopeTabController(props);

  if (c.isProvider) {
    return (
      <PrunerScopeProviderSubsection
        scope={props.scope}
        provSub={c.provSub}
        instanceId={c.instanceId}
        disabledMode={props.disabledMode}
        isPlex={c.isPlex}
        busy={c.busy}
        showInteractiveControls={c.showInteractiveControls}
        scopeRow={c.scopeRow}
        watchedTvEnabled={c.watchedTvEnabled}
        setWatchedTvEnabled={c.setWatchedTvEnabled}
        rulesTvOlderDaysStr={c.rulesTvOlderDaysStr}
        setRulesTvOlderDaysStr={c.setRulesTvOlderDaysStr}
        watchedMoviesEnabled={c.watchedMoviesEnabled}
        setWatchedMoviesEnabled={c.setWatchedMoviesEnabled}
        rulesMoviesLowRatingStr={c.rulesMoviesLowRatingStr}
        setRulesMoviesLowRatingStr={c.setRulesMoviesLowRatingStr}
        rulesMoviesUnwatchedDaysStr={c.rulesMoviesUnwatchedDaysStr}
        setRulesMoviesUnwatchedDaysStr={c.setRulesMoviesUnwatchedDaysStr}
        genreSelection={c.genreSelection}
        setGenreSelection={c.setGenreSelection}
        yearMinStr={c.yearMinStr}
        setYearMinStr={c.setYearMinStr}
        yearMaxStr={c.yearMaxStr}
        setYearMaxStr={c.setYearMaxStr}
        studioText={c.studioText}
        setStudioText={c.setStudioText}
        peopleText={c.peopleText}
        setPeopleText={c.setPeopleText}
        peopleRoles={c.peopleRoles}
        setPeopleRoles={c.setPeopleRoles}
        bundleMsg={c.bundleMsg}
        err={c.err}
        saveProviderTvRulesBundle={c.saveProviderTvRulesBundle}
        saveProviderMoviesRulesBundle={c.saveProviderMoviesRulesBundle}
        saveProviderFiltersBundle={c.saveProviderFiltersBundle}
        saveProviderPeopleBundle={c.saveProviderPeopleBundle}
      />
    );
  }

  return (
    <section
      className="mm-bubble-stack max-w-3xl"
      aria-labelledby="pruner-scope-heading"
    >
      <fieldset
        disabled={Boolean(props.disabledMode)}
        className="mm-bubble-stack"
      >
        <PrunerScopeTabDefaultLayout
          instanceId={c.instanceId}
          scope={props.scope}
          disabledMode={props.disabledMode}
          label={c.label}
          libraryTabPhrase={c.libraryTabPhrase}
          isPlex={c.isPlex}
          showInteractiveControls={c.showInteractiveControls}
          busy={c.busy}
          scopeRow={c.scopeRow}
          previewMaxItems={c.previewMaxItems}
          setPreviewMaxItems={c.setPreviewMaxItems}
          previewMaxItemsMsg={c.previewMaxItemsMsg}
          savePreviewMaxItemsSettings={c.savePreviewMaxItemsSettings}
          genreSelection={c.genreSelection}
          setGenreSelection={c.setGenreSelection}
          saveGenreFilters={c.saveGenreFilters}
          genreMsg={c.genreMsg}
          peopleText={c.peopleText}
          setPeopleText={c.setPeopleText}
          peopleRoles={c.peopleRoles}
          setPeopleRoles={c.setPeopleRoles}
          savePeopleFilters={c.savePeopleFilters}
          peopleMsg={c.peopleMsg}
          yearMinStr={c.yearMinStr}
          setYearMinStr={c.setYearMinStr}
          yearMaxStr={c.yearMaxStr}
          setYearMaxStr={c.setYearMaxStr}
          savePreviewYearBounds={c.savePreviewYearBounds}
          yearMsg={c.yearMsg}
          studioText={c.studioText}
          setStudioText={c.setStudioText}
          saveStudioPreviewFilters={c.saveStudioPreviewFilters}
          studioMsg={c.studioMsg}
          collectionText={c.collectionText}
          setCollectionText={c.setCollectionText}
          saveCollectionPreviewFilters={c.saveCollectionPreviewFilters}
          collectionMsg={c.collectionMsg}
          staleNeverEnabled={c.staleNeverEnabled}
          setStaleNeverEnabled={c.setStaleNeverEnabled}
          staleNeverDays={c.staleNeverDays}
          setStaleNeverDays={c.setStaleNeverDays}
          staleNeverMsg={c.staleNeverMsg}
          saveStaleNeverSettings={c.saveStaleNeverSettings}
          runStaleNeverPreview={c.runStaleNeverPreview}
          watchedTvEnabled={c.watchedTvEnabled}
          setWatchedTvEnabled={c.setWatchedTvEnabled}
          watchedTvMsg={c.watchedTvMsg}
          saveWatchedTvSettings={c.saveWatchedTvSettings}
          runWatchedTvPreview={c.runWatchedTvPreview}
          watchedMoviesEnabled={c.watchedMoviesEnabled}
          setWatchedMoviesEnabled={c.setWatchedMoviesEnabled}
          watchedMoviesMsg={c.watchedMoviesMsg}
          saveWatchedMoviesSettings={c.saveWatchedMoviesSettings}
          runWatchedMoviesPreview={c.runWatchedMoviesPreview}
          lowRatingEnabled={c.lowRatingEnabled}
          setLowRatingEnabled={c.setLowRatingEnabled}
          lowRatingMax={c.lowRatingMax}
          setLowRatingMax={c.setLowRatingMax}
          lowRatingMsg={c.lowRatingMsg}
          saveLowRatingMovieSettings={c.saveLowRatingMovieSettings}
          runLowRatingMoviesPreview={c.runLowRatingMoviesPreview}
          unwatchedStaleEnabled={c.unwatchedStaleEnabled}
          setUnwatchedStaleEnabled={c.setUnwatchedStaleEnabled}
          unwatchedStaleDays={c.unwatchedStaleDays}
          setUnwatchedStaleDays={c.setUnwatchedStaleDays}
          unwatchedStaleMsg={c.unwatchedStaleMsg}
          saveUnwatchedStaleMovieSettings={c.saveUnwatchedStaleMovieSettings}
          runUnwatchedStaleMoviesPreview={c.runUnwatchedStaleMoviesPreview}
          runPreview={c.runPreview}
          loadJsonFor={c.loadJsonFor}
          schedEnabled={c.schedEnabled}
          setSchedEnabled={c.setSchedEnabled}
          schedIntervalSec={c.schedIntervalSec}
          schedIntervalMinDraft={c.schedIntervalMinDraft}
          setSchedIntervalMinDraft={c.setSchedIntervalMinDraft}
          schedHoursLimited={c.schedHoursLimited}
          setSchedHoursLimited={c.setSchedHoursLimited}
          schedDays={c.schedDays}
          setSchedDays={c.setSchedDays}
          schedStart={c.schedStart}
          setSchedStart={c.setSchedStart}
          schedEnd={c.schedEnd}
          setSchedEnd={c.setSchedEnd}
          fmt={c.fmt}
          schedMsg={c.schedMsg}
          saveSchedule={c.saveSchedule}
          runs={c.runsQuery.data}
          runsLoading={c.runsQuery.isLoading}
          runsError={c.runsQuery.isError ? (c.runsQuery.error as Error) : null}
          canOperate={c.canOperate}
          provider={c.instance?.provider}
          ruleFamilyColumnLabel={c.ruleFamilyColumnLabel}
          openApplyModal={c.openApplyModal}
          applyModalRunId={c.applyModalRunId}
          applySnapshotOperatorLabel={c.applySnapshotOperatorLabel}
          applyEligibilityLoading={c.applyEligQuery.isLoading}
          applyEligibilityError={
            c.applyEligQuery.isError ? (c.applyEligQuery.error as Error) : null
          }
          applyEligibilityData={c.applyEligQuery.data}
          applySnapshotConfirmed={c.applySnapshotConfirmed}
          setApplySnapshotConfirmed={c.setApplySnapshotConfirmed}
          closeApplyModal={c.closeApplyModal}
          confirmApplyFromSnapshot={c.confirmApplyFromSnapshot}
          err={c.err}
          preview={c.preview}
          jsonPreview={c.jsonPreview}
        />
      </fieldset>
    </section>
  );
}
