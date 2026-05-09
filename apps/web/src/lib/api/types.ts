import type { components } from "./generated/openapi-types";

type OpenApiSchemaName = keyof components["schemas"];
type OpenApiSchema<T extends OpenApiSchemaName> = components["schemas"][T];

export type UserPublic = OpenApiSchema<"UserPublic">;
export type CurrentSession = OpenApiSchema<"CurrentSessionOut">;
export type BootstrapStatus = OpenApiSchema<"BootstrapStatusOut">;
export type DashboardSystemStatus = OpenApiSchema<"SystemStatusOut">;
export type ActivityEventItem = OpenApiSchema<"ActivityEventItemOut">;
export type DashboardActivitySummary = OpenApiSchema<"ActivitySummaryOut">;
export type DashboardStatus = OpenApiSchema<"DashboardStatusOut">;
export type ActivityRecentResponse = OpenApiSchema<"ActivityRecentOut">;
