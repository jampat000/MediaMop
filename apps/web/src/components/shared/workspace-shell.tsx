import type { ReactNode } from "react";
import {
  mmModuleTabBlurbBandClass,
  mmModuleTabBlurbTextClass,
} from "../../lib/ui/mm-module-tab-blurb";
import { mmSectionTabClass } from "../../lib/ui/mm-control-roles";

function classes(...values: Array<string | undefined>): string {
  return values.filter(Boolean).join(" ");
}

type WorkspacePageProps = {
  eyebrow?: string;
  title: string;
  description: ReactNode;
  children: ReactNode;
  dataTestId?: string;
  descriptionClassName?: string;
};

export function WorkspacePage({
  eyebrow,
  title,
  description,
  children,
  dataTestId,
  descriptionClassName,
}: WorkspacePageProps) {
  return (
    <div className="mm-page mm-workspace-page" data-testid={dataTestId}>
      <header className="mm-page__intro mm-workspace-page__intro">
        {eyebrow ? <p className="mm-page__eyebrow">{eyebrow}</p> : null}
        <h1 className="mm-page__title">{title}</h1>
        <p className={classes("mm-page__lead", descriptionClassName)}>
          {description}
        </p>
      </header>
      {children}
    </div>
  );
}

export type WorkspaceTabOption<Id extends string> = Readonly<{
  id: Id;
  label: string;
}>;

type WorkspaceTabListProps<Id extends string> = {
  tabs: readonly WorkspaceTabOption<Id>[];
  activeId: Id;
  onSelect: (id: Id) => void;
  ariaLabel: string;
  idPrefix: string;
  panelId: string;
  dataTestId?: string;
};

export function WorkspaceTabList<Id extends string>({
  tabs,
  activeId,
  onSelect,
  ariaLabel,
  idPrefix,
  panelId,
  dataTestId,
}: WorkspaceTabListProps<Id>) {
  return (
    <nav
      className="mm-workspace-tabs"
      aria-label={ariaLabel}
      data-testid={dataTestId}
    >
      <div
        role="tablist"
        aria-label={ariaLabel}
        className="mm-workspace-tabs__list"
      >
        {tabs.map(({ id, label }) => {
          const selected = activeId === id;
          return (
            <button
              key={id}
              type="button"
              role="tab"
              id={`${idPrefix}-${id}`}
              aria-controls={panelId}
              aria-selected={selected}
              className={`${mmSectionTabClass(selected)} mm-workspace-tabs__button`}
              onClick={() => onSelect(id)}
            >
              {label}
            </button>
          );
        })}
      </div>
    </nav>
  );
}

type WorkspacePanelProps = {
  id: string;
  labelledBy: string;
  context?: ReactNode;
  children: ReactNode;
  contextTestId?: string;
};

export function WorkspacePanel({
  id,
  labelledBy,
  context,
  children,
  contextTestId,
}: WorkspacePanelProps) {
  return (
    <section
      id={id}
      className="mm-workspace-panel mm-bubble-stack"
      role="tabpanel"
      aria-labelledby={labelledBy}
    >
      {context !== undefined ? (
        <div className={mmModuleTabBlurbBandClass} data-testid={contextTestId}>
          <p className={mmModuleTabBlurbTextClass}>{context}</p>
        </div>
      ) : null}
      <div className="mm-workspace-panel__content mm-bubble-stack">
        {children}
      </div>
    </section>
  );
}
