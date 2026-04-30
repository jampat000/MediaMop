export type CuratedTimezoneOption = {
  id: string;
  country: string;
  city: string;
  zoneName: string;
};

export const CURATED_TIMEZONE_OPTIONS: readonly CuratedTimezoneOption[] = [
  {
    id: "Australia/Sydney",
    country: "Australia",
    city: "Sydney",
    zoneName: "",
  },
  {
    id: "Australia/Melbourne",
    country: "Australia",
    city: "Melbourne",
    zoneName: "",
  },
  {
    id: "Australia/Brisbane",
    country: "Australia",
    city: "Brisbane",
    zoneName: "",
  },
  {
    id: "Australia/Adelaide",
    country: "Australia",
    city: "Adelaide",
    zoneName: "",
  },
  {
    id: "Australia/Darwin",
    country: "Australia",
    city: "Darwin",
    zoneName: "",
  },
  { id: "Australia/Perth", country: "Australia", city: "Perth", zoneName: "" },
  {
    id: "America/New_York",
    country: "United States",
    city: "New York",
    zoneName: "Eastern",
  },
  {
    id: "America/Chicago",
    country: "United States",
    city: "Chicago",
    zoneName: "Central",
  },
  {
    id: "America/Denver",
    country: "United States",
    city: "Denver",
    zoneName: "Mountain",
  },
  {
    id: "America/Los_Angeles",
    country: "United States",
    city: "Los Angeles",
    zoneName: "Pacific",
  },
  {
    id: "America/Anchorage",
    country: "United States",
    city: "Anchorage",
    zoneName: "Alaska",
  },
  {
    id: "Pacific/Honolulu",
    country: "United States",
    city: "Honolulu",
    zoneName: "Hawaii",
  },
  { id: "Asia/Shanghai", country: "China", city: "Shanghai", zoneName: "" },
  { id: "Asia/Kolkata", country: "India", city: "Mumbai", zoneName: "" },
  { id: "Asia/Tokyo", country: "Japan", city: "Tokyo", zoneName: "" },
  { id: "Europe/Berlin", country: "Germany", city: "Berlin", zoneName: "" },
  {
    id: "Europe/London",
    country: "United Kingdom",
    city: "London",
    zoneName: "",
  },
  { id: "Europe/Paris", country: "France", city: "Paris", zoneName: "" },
  { id: "Europe/Rome", country: "Italy", city: "Rome", zoneName: "" },
  {
    id: "America/Sao_Paulo",
    country: "Brazil",
    city: "Sao Paulo",
    zoneName: "",
  },
  { id: "America/Toronto", country: "Canada", city: "Toronto", zoneName: "" },
  { id: "Europe/Moscow", country: "Russia", city: "Moscow", zoneName: "" },
  { id: "Asia/Seoul", country: "South Korea", city: "Seoul", zoneName: "" },
  {
    id: "Asia/Singapore",
    country: "Singapore",
    city: "Singapore",
    zoneName: "",
  },
  { id: "Asia/Jakarta", country: "Indonesia", city: "Jakarta", zoneName: "" },
  { id: "Asia/Bangkok", country: "Thailand", city: "Bangkok", zoneName: "" },
  {
    id: "Asia/Dubai",
    country: "United Arab Emirates",
    city: "Dubai",
    zoneName: "",
  },
  {
    id: "Europe/Amsterdam",
    country: "Netherlands",
    city: "Amsterdam",
    zoneName: "",
  },
  { id: "Europe/Madrid", country: "Spain", city: "Madrid", zoneName: "" },
  {
    id: "Africa/Johannesburg",
    country: "South Africa",
    city: "Johannesburg",
    zoneName: "",
  },
  {
    id: "Asia/Hong_Kong",
    country: "Hong Kong",
    city: "Hong Kong",
    zoneName: "",
  },
  {
    id: "Pacific/Auckland",
    country: "New Zealand",
    city: "Auckland",
    zoneName: "",
  },
];

export const CURATED_TIMEZONE_ID_SET: Set<string> = new Set(
  CURATED_TIMEZONE_OPTIONS.map((o) => o.id),
);

function timezoneOffsetLabel(tz: string): string {
  try {
    const formatter = new Intl.DateTimeFormat(undefined, {
      hour: "2-digit",
      minute: "2-digit",
      timeZoneName: "shortOffset",
      timeZone: tz,
    });
    const part = formatter
      .formatToParts(new Date())
      .find((p) => p.type === "timeZoneName");
    return (part?.value || "UTC+0").replace("GMT", "UTC");
  } catch {
    return "UTC+0";
  }
}

export function curatedTimezoneLabelById(tz: string): string | null {
  const option = CURATED_TIMEZONE_OPTIONS.find((o) => o.id === tz);
  if (!option) {
    return null;
  }
  const zone = option.zoneName ? ` (${option.zoneName})` : "";
  return `${option.country} — ${option.city}${zone} (${timezoneOffsetLabel(option.id)})`;
}

export function curatedTimezoneOptionsSorted(): Array<{
  id: string;
  label: string;
}> {
  return CURATED_TIMEZONE_OPTIONS.map((o) => {
    const zone = o.zoneName ? ` (${o.zoneName})` : "";
    return {
      id: o.id,
      label: `${o.country} — ${o.city}${zone} (${timezoneOffsetLabel(o.id)})`,
    };
  }).sort((a, b) => a.label.localeCompare(b.label));
}

export function timezoneDisplayLabelForUi(tz: string): string {
  return curatedTimezoneLabelById(tz) ?? tz;
}
