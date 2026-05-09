import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Smart Truck — DAMM DDI",
  description:
    "Joint route + load optimisation for the DDI Mollet warehouse. Interhack BCN 2026.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="ca">
      <body className="min-h-screen bg-white text-damm-dark antialiased">
        {children}
      </body>
    </html>
  );
}
