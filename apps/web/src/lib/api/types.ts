import type { components } from "./generated/openapi-types";

type OpenApiSchemaName = keyof components["schemas"];
type OpenApiSchema<T extends OpenApiSchemaName> = components["schemas"][T];

export type UserPublic = OpenApiSchema<"UserPublic">;
export type CurrentSession = OpenApiSchema<"CurrentSessionOut">;
export type ActiveSession = OpenApiSchema<"SessionOut">;
export type SessionAction = OpenApiSchema<"SessionActionOut">;
export type BootstrapStatus = OpenApiSchema<"BootstrapStatusOut">;
export type ActivityEventItem = OpenApiSchema<"ActivityEventItemOut">;
export type DashboardStatus = OpenApiSchema<"DashboardStatusOut">;
export type ActivityRecentResponse = OpenApiSchema<"ActivityRecentOut">;
