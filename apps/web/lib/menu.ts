// The simple pilot deliberately exposes only the one workflow we are testing:
// customer request -> human decision -> booking. Everything else stays in the repo and
// remains reachable by direct route for development, but it is not part of the pilot UI.
//
// NEXT_PUBLIC_NOVAXIS_EXTRAS still controls experimental details inside the four screens.

export const EXTRAS = process.env.NEXT_PUBLIC_NOVAXIS_EXTRAS === "1";
export const SIMPLE_PILOT = true;

export type MenuLink = { href: string; label: string; icon: string; roles?: string[]; extra?: boolean };

const LINKS: MenuLink[] = [
  { href: "/inbox", label: "Inbox", icon: "inbox" },
  { href: "/approvals", label: "Approvals", icon: "check" },
  { href: "/schedule", label: "Schedule", icon: "calendar" },
  { href: "/settings", label: "Settings", icon: "settings" },
];

const OPERATOR_LINKS: MenuLink[] = [{ href: "/operator", label: "Tenants", icon: "building" }];

export function menuFor(role: string, operatorConsole: boolean, extras: boolean = EXTRAS): MenuLink[] {
  void role;
  void extras;
  if (operatorConsole) return OPERATOR_LINKS;
  return LINKS;
}
