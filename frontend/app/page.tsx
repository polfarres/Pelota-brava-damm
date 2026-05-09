export default function Home() {
  return (
    <main className="mx-auto max-w-4xl px-6 py-16">
      <h1 className="text-4xl font-bold tracking-tight text-damm-red">
        Smart Truck
      </h1>
      <p className="mt-2 text-lg text-neutral-600">
        DAMM DDI · Interhack BCN 2026
      </p>

      <section className="mt-10 space-y-4">
        <p>
          Joint optimisation of route and truck-load configuration for the
          Mollet warehouse, with reverse-logistics awareness and a hybrid
          client-cluster + LIFO load model.
        </p>
        <p className="text-sm text-neutral-600">
          Backend API:{" "}
          <code className="rounded bg-neutral-100 px-2 py-1">
            {process.env.NEXT_PUBLIC_API_URL}
          </code>
        </p>
      </section>

      <nav className="mt-10 grid grid-cols-1 gap-4 sm:grid-cols-3">
        <a
          href="/truck"
          className="rounded-lg border border-neutral-200 p-6 transition hover:border-damm-red hover:shadow"
        >
          <div className="text-sm uppercase tracking-wide text-neutral-500">
            Camió
          </div>
          <div className="mt-2 text-xl font-semibold">Truck twin 3D</div>
        </a>
        <a
          href="/pick-list"
          className="rounded-lg border border-neutral-200 p-6 transition hover:border-damm-red hover:shadow"
        >
          <div className="text-sm uppercase tracking-wide text-neutral-500">
            Magatzem
          </div>
          <div className="mt-2 text-xl font-semibold">Smart Hoja Carga</div>
        </a>
        <a
          href="/driver"
          className="rounded-lg border border-neutral-200 p-6 transition hover:border-damm-red hover:shadow"
        >
          <div className="text-sm uppercase tracking-wide text-neutral-500">
            Xofer
          </div>
          <div className="mt-2 text-xl font-semibold">Driver mobile</div>
        </a>
      </nav>
    </main>
  );
}
