// What the menu shows. The prototype keeps to the core loop (docs/prototype.md): Inbox,
// Approvals, Schedule, Customers, Settings. Parked parts keep their pages and API and come
// back on a deployment that sets NEXT_PUBLIC_NOVAXIS_EXTRAS=1.

export const EXTRAS = process.env.NEXT_PUBLIC_NOVAXIS_EXTRAS === "1";

export type MenuLink = { href: string; label: string; icon: string; roles?: string[]; extra?: boolean };

// Everyone can read every page; the API refuses what a role may not do. Setup and billing
// are the owner's alone, so nobody else is shown them.
const OWNERS = ["owner", "operator"];

const LINKS: MenuLink[] = [
  { href: "/inbox", label: "Inbox", icon: "inbox" },
  { href: "/approvals", label: "Approvals", icon: "check" },
  { href: "/schedule", label: "Schedule", icon: "calendar" },
  { href: "/contacts", label: "Contacts", icon: "users" },
  { href: "/settings", label: "Settings", icon: "settings" },
  { href: "/onboarding", label: "Setup", icon: "rocket", roles: OWNERS },
  { href: "/billing", label: "Billing", icon: "card", roles: OWNERS },
  { href: "/queue", label: "Work queue", icon: "queue", extra: true },
  { href: "/analytics", label: "Analytics", icon: "chart", extra: true },
  { href: "/stock", label: "Stock", icon: "box", extra: true },
];

const OPERATOR_LINKS: MenuLink[] = [{ href: "/operator", label: "Tenants", icon: "building" }];

export function menuFor(role: string, operatorConsole: boolean, extras: boolean = EXTRAS): MenuLink[] {
  if (operatorConsole) return OPERATOR_LINKS;
  return LINKS.filter((l) => (!l.roles || l.roles.includes(role)) && (!l.extra || extras));
}
