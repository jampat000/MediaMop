import {
  SHOW_SUPPORT_CARD,
  SHOW_SUPPORT_URL_PLACEHOLDER,
  SUPPORT_URL,
} from "../../lib/support";
import {
  mmModuleTabBlurbBandClass,
  mmModuleTabBlurbTextClass,
} from "../../lib/ui/mm-module-tab-blurb";
import { SettingsQuietSection } from "./settings-shared";

export { SHOW_SUPPORT_CARD };

export function SettingsSupportTab() {
  return (
    <div data-testid="suite-settings-support-tab" className="mm-quiet-stack">
      <div className={mmModuleTabBlurbBandClass}>
        <p className={mmModuleTabBlurbTextClass}>
          Optional support details for Weir. Core app features remain fully
          usable without any support flow.
        </p>
      </div>

      <SettingsQuietSection
        headingId="suite-settings-support-heading"
        heading="Support Weir"
        data-testid="suite-settings-support"
      >
        <p className="mm-quiet-note">
          Weir is free to use. Support is optional.
        </p>
        <p className="mm-quiet-note mt-2">
          If Weir saves you time or keeps your downloads clean, you can support
          ongoing development.
        </p>
        {SUPPORT_URL ? (
          <p className="mt-4">
            <a
              href={SUPPORT_URL}
              target="_blank"
              rel="noreferrer"
              className="mm-quiet-link"
              data-testid="suite-settings-support-button"
            >
              Support Weir →
            </a>
          </p>
        ) : null}
        {SHOW_SUPPORT_URL_PLACEHOLDER ? (
          <p className="mt-3 text-[length:var(--mm-type-caption)] leading-[1.45] text-[var(--mm-text3)]">
            Development note: set <code>VITE_SUPPORT_URL</code> to show the
            support button.
          </p>
        ) : null}
      </SettingsQuietSection>
    </div>
  );
}
