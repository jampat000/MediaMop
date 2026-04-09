export type UserPublic = {
  id: number;
  username: string;
  role: string;
};

export type BootstrapStatus = {
  bootstrap_allowed: boolean;
  reason: string;
};
