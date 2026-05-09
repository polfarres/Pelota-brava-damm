import type { Metadata } from 'next';
import './globals.css';
import Link from 'next/link';

export const metadata: Metadata = {
  title: 'Smart Truck — DAMM',
  description: 'Optimitzador conjunt de ruta i càrrega per a DDI Mollet',
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="ca">
      <body className="min-h-screen bg-gray-50 text-damm-dark">
        <header className="bg-damm-dark text-white px-6 py-3 flex items-center gap-6 shadow">
          <Link href="/" className="flex items-center gap-2 font-bold text-lg">
            <span className="inline-block w-3 h-3 rounded-full bg-damm-red" />
            Smart Truck
            <span className="text-xs font-normal text-gray-400 ml-2">
              DDI Mollet · DR0027 · 2026-05-08
            </span>
          </Link>
          <nav className="flex gap-4 text-sm ml-auto">
            <Link href="/" className="hover:text-damm-red">Tauler</Link>
            <Link href="/pick-list" className="hover:text-damm-red">Full de Càrrega</Link>
            <Link href="/truck" className="hover:text-damm-red">Camió</Link>
            <Link href="/driver" className="hover:text-damm-red">Conductor</Link>
          </nav>
        </header>
        <main>{children}</main>
      </body>
    </html>
  );
}
