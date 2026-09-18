import { useId, type ReactNode } from "react";

/**
 * The quiet body of a page, as rule 3 of docs/design/content-language.md draws it:
 * a heading on the left, its links on the right, a hairline under both, then the
 * content. No cards, no panels, no wells.
 *
 * Lifted unchanged out of processing-overview-tab.tsx — the reference implementation
 * the design was approved on — so every page spells the same shape the same way.
 */
export function QuietSection({
  headingId,
  heading,
  aside,
  children,
  "data-testid": dataTestId,
}: {
  headingId: string;
  heading: string;
  aside?: ReactNode;
  children: ReactNode;
  "data-testid"?: string;
}) {
  return (
    <section
      className="mm-quiet-section"
      aria-labelledby={headingId}
      data-testid={dataTestId}
    >
      <div className="mm-quiet-section__head">
        <h2 id={headingId} className="mm-quiet-section__title">
          {heading}
        </h2>
        {aside ? <div className="mm-quiet-section__aside">{aside}</div> : null}
      </div>
      <div className="mm-quiet-section__body">{children}</div>
    </section>
  );
}

/**
 * One group of fields inside a long configuration form.
 *
 * Rule 3 takes the boxes off a form, and a forty-field form that loses its grouping
 * becomes unusable — so the grouping has to survive as type and whitespace instead.
 * The treatment is the one the language already gives a table's header row: uppercase
 * eyebrow type over a hairline, labelling the block beneath it. That reads clearly
 * below a `.mm-quiet-section__title` without ever becoming a second box, and the
 * `.mm-quiet-stack` these sit in supplies the 2.5rem between groups.
 *
 * The treatment earned its name, so it is `.mm-quiet-group` in weir-content.css rather
 * than a Tailwind copy here: one place to change it, and a page cannot drift from it.
 */
export function QuietFieldGroup({
  step,
  title,
  detail,
  aside,
  children,
  className,
}: {
  /** Shown before the title as a "step n of five" cue. Decorative: it is kept out of
   *  the heading's accessible name, which stays exactly the group's own title. */
  step?: number;
  title: string;
  detail?: ReactNode;
  aside?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  const headingId = useId();
  return (
    <section
      className={`mm-quiet-group${className ? ` ${className}` : ""}`}
      aria-labelledby={headingId}
    >
      <div className="mm-quiet-group__head">
        <span className="mm-quiet-group__name">
          {step === undefined ? null : (
            <span aria-hidden="true" className="mm-quiet-group__step">
              {step}
            </span>
          )}
          <h3 id={headingId} className="mm-quiet-group__title">
            {title}
          </h3>
        </span>
        {aside ?? null}
      </div>
      {detail ? <p className="mm-quiet-group__detail">{detail}</p> : null}
      <div className="mm-quiet-group__body">{children}</div>
    </section>
  );
}

/**
 * The hairline above a form's own Save row. `mm-card-action-footer` drew this when the
 * form was a card; without the card it is just a rule and the buttons under it.
 */
export const quietActionRowClass = "mm-quiet-actions";
