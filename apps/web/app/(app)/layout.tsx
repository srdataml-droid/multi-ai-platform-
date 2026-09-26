import type { ReactNode } from "react";
import { Nav } from "@/components/Nav";

export default function AppLayout({ children }: { children: ReactNode }) {
  return (
    <div className="flex min-h-screen flex-col md:flex-row">
      <Nav />
      <main className="min-w-0 flex-1 p-4 md:p-6">{children}</main>
    </div>
  );
}
