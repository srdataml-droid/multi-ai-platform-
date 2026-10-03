// The pilot defaults to one workflow: request -> decision -> booking.
// NEXT_PUBLIC_NOVAXIS_EXTRAS=1 restores the parked product surfaces without deleting code,
// and is used by end-to-end tests so the larger platform keeps working while hidden.

export const EXTRAS = process.env.NEXT_PUBLIC_NOVAXIS_EXTRAS === "1";
export const SIMPLE_PILOT = !EXTRAS;

export type MenuLink = { href: string; label: string; icon: string; roles?: string[]; extra?: boolean };

const OWNERS = ["owner", "operator"];

const PILOT_LINKS: MenuLink[] = [
  { href: "/inbox", label: "Inbox", icon: "inbox" },
  { href: "/approvals", label: "Approvals", icon: "check" },
  { href: "/schedule", label: "Schedule", icon: "calendar" },
  { href: "/settings", label: "Settings", icon: "settings" },
];

const FULL_LINKS: MenuLink[] = [
  { href: "/inbox", label: "Inbox", icon: "inbox" },
  { href: "/approvals", label: "Approvals", icon: "check" },
  { href: "/schedule", label: "Schedule", icon: "calendar" },
  { href: "/contacts", label: "Contacts", icon: "users" },
  { href: "/settings", label: "Settings", icon: "settings" },
  { href: "/onboarding", label: "Setup", icon: "rocket", roles: OWNERS },
  { href: "/billing", label: "Billing", icon: "card", roles: OWNERS },
  { href: "/queue", label: "Work queue", icon: "queue" },
  { href: "/analytics", label: "Analytics", icon: "chart" },
  { href: "/stock", label: "Stock", icon: "box" },
];

const OPERATOR_LINKS: MenuLink[] = [{ href: "/operator", label: "Tenants", icon: "building" }];

export function menuFor(role: string, operatorConsole: boolean, extras: boolean = EXTRAS): MenuLink[] {
  if (operatorConsole) return OPERATOR_LINKS;
  const links = extras ? FULL_LINKS : PILOT_LINKS;
  return links.filter((l) => !l.roles || l.roles.includes(role));
}
