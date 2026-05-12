import {
  SHOW_SUPPORT_CARD,
  SHOW_SUPPORT_URL_PLACEHOLDER,
  SUPPORT_URL,
} from "../../lib/support";
import { mmActionButtonClass } from "../../lib/ui/mm-control-roles";
import {
  mmModuleTabBlurbBandClass,
  mmModuleTabBlurbTextClass,
} from "../../lib/ui/mm-module-tab-blurb";
import { SUITE_SETTINGS_DASH_CARD_CLASS } from "./settings-shared";

export { SHOW_SUPPORT_CARD };

export function SettingsSupportTab() {
  return (
    <div data-testid="suite-settings-support-tab" className="mm-bubble-stack">
      <div className={mmModuleTabBlurbBandClass}>
        <p className={mmModuleTabBlurbTextClass}>
          Optional support details for MediaMop. Core app features remain fully
          usable without any support flow.
        </p>
      </div>

      <section
        className={SUITE_SETTINGS_DASH_CARD_CLASS}
        data-testid="suite-settings-support"
        aria-labelledby="suite-settings-support-heading"
      >
        <div className="mm-card-action-body">
          <div className="space-y-3">
            <h3
              id="suite-settings-support-heading"
              className="text-base font-semibold text-[var(--mm-text1)]"
            >
              Support MediaMop
            </h3>
            <div className="space-y-2 text-sm text-[var(--mm-text2)]">
              <p>MediaMop is free to use. Support is optional.</p>
              <p>
                If MediaMop saves you time or helps keep your library cleaner,
                you can support ongoing development.
              </p>
            </div>
          </div>
          {SHOW_SUPPORT_URL_PLACEHOLDER ? (
            <p className="rounded-md border border-[var(--mm-border)] bg-[var(--mm-card-bg)] px-3 py-2 text-xs text-[var(--mm-text3)]">
              Development note: set <code>VITE_SUPPORT_URL</code> to show the
              support button.
            </p>
          ) : null}
        </div>
        {SUPPORT_URL ? (
          <div className="mm-card-action-footer">
            <a
              href={SUPPORT_URL}
              target="_blank"
              rel="noreferrer"
              className={mmActionButtonClass({
                variant: "secondary",
                disabled: false,
              })}
              data-testid="suite-settings-support-button"
            >
              Support MediaMop
            </a>
          </div>
        ) : null}
      </section>
    </div>
  );
}
