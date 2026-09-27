import type { Metadata } from "next";
import type { ReactNode } from "react";
import "./globals.css";

export const metadata: Metadata = {
  title: "Novaxis Worker",
  description: "Multitenant AI worker for service businesses",
  manifest: "/manifest.webmanifest",
  appleWebApp: { capable: true, title: "Novaxis" },
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body className="font-sans antialiased">{children}</body>
    </html>
  );
}
