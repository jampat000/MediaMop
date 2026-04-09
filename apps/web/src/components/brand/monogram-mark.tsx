import * as React from "react";

type MonogramMarkProps = {
  className?: string;
  title?: string;
};

export function MonogramMark({
  className,
  title = "MediaMop",
}: MonogramMarkProps) {
  const gradientId = React.useId();
  const titleId = React.useId();

  return (
    <svg
      viewBox="0 0 48 48"
      width="100%"
      height="100%"
      role="img"
      aria-labelledby={titleId}
      className={className}
      fill="none"
    >
      <title id={titleId}>{title}</title>

      <defs>
        <linearGradient id={gradientId} x1="10" y1="10" x2="38" y2="36">
          <stop offset="0%" stopColor="#F3E2A3" />
          <stop offset="45%" stopColor="#D4AF37" />
          <stop offset="100%" stopColor="#9B7620" />
        </linearGradient>
      </defs>

      <g
        stroke={`url(#${gradientId})`}
        strokeWidth="2.4"
        strokeLinecap="round"
        strokeLinejoin="round"
        vectorEffect="non-scaling-stroke"
      >
        <path d="M12 31V16L19.25 24L26.5 16" />
        <path d="M28 16V31" />
        <path d="M28 16H31.2C34.4 16 36.2 17.55 36.2 20.2C36.2 23 34.1 24.6 31.1 24.6H28" />
        <path d="M28 24.6H31.8C35 24.6 37 26.25 37 29.1C37 31.95 34.9 33.5 31.2 33.5H28" />
      </g>
    </svg>
  );
}

export default MonogramMark;
