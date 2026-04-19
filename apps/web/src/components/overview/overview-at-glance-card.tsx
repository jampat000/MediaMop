import type { ReactNode } from "react";

/**
 * Inner “At a glance” tile used on module overview tabs.
 * Typography matches `.mm-card__body` from `mediamop-shell.css` (0.90625rem / 1.58 on `--mm-text2`).
 */
export function OverviewAtGlanceCard({
  title,
  body,
  glanceOrder,
  emphasis,
  footer,
  gridClassName,
  size = "default",
  "data-testid": dataTestId,
}: {
  title: string;
  body: ReactNode;
  glanceOrder: string;
  emphasis?: boolean;
  footer?: ReactNode;
  gridClassName?: string;
  size?: "default" | "large";
  "data-testid"?: string;
}) {
  const large = size === "large";
  return (
    <div
      className={[
        "flex h-full min-h-0 flex-col rounded-md border border-[var(--mm-border)]",
        large ? "gap-4 p-5 text-sm lg:gap-5 lg:p-6" : "gap-3 p-5 text-sm",
        emphasis
          ? "bg-[var(--mm-card-bg)] shadow-[inset_0_1px_0_0_rgba(255,255,255,0.04)]"
          : "bg-[var(--mm-card-bg)]",
        large ? "lg:text-[0.9375rem] lg:leading-relaxed" : "",
        gridClassName ?? "",
      ]
        .filter(Boolean)
        .join(" ")}
      data-at-glance-order={glanceOrder}
      data-testid={dataTestId}
    >
      <h3 className="text-sm font-semibold text-[var(--mm-text1)]">{title}</h3>
      <div
        className={[
          "min-h-0 flex-1 text-[0.90625rem] leading-[1.58] text-[var(--mm-text2)]",
          large ? "mt-1 lg:mt-1.5" : "",
        ]
          .filter(Boolean)
          .join(" ")}
      >
        {body}
      </div>
      {footer ? (
        <div className={["mt-auto border-t border-[var(--mm-border)] pt-4", large ? "lg:pt-5" : ""].filter(Boolean).join(" ")}>
          {footer}
        </div>
      ) : null}
    </div>
  );
}
