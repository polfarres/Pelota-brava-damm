import type { Metadata } from 'next';
import { Suspense } from 'react';
import './globals.css';
import Link from 'next/link';
import RouteSelector from '@/components/RouteSelector';

export const metadata: Metadata = {
  title: 'Smart Truck — DAMM',
  description: 'Optimizador de ruta + carga conjunto para DDI Mollet',
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="es">
      <body className="min-h-screen bg-gray-50 text-damm-dark">
        <header className="bg-damm-dark text-white px-6 py-3 flex items-center gap-6 shadow">
          <Link href="/" className="flex items-center gap-2 font-bold text-lg">
            <span className="inline-block w-3 h-3 rounded-full bg-damm-red" />
            Smart Truck
            <span className="text-xs font-normal text-gray-400 ml-2">DDI Mollet</span>
          </Link>
          <Suspense fallback={null}>
            <RouteSelector />
          </Suspense>
          <nav className="flex gap-4 text-sm ml-auto">
            <Link href="/" className="hover:text-damm-red">Dashboard</Link>
            <Link href="/pick-list" className="hover:text-damm-red">Hoja Carga</Link>
            <Link href="/truck" className="hover:text-damm-red">Truck Twin</Link>
            <Link href="/driver" className="hover:text-damm-red">Conductor</Link>
          </nav>
        </header>
        <main>
          <Suspense fallback={null}>{children}</Suspense>
        </main>
      </body>
    </html>
  );
}
