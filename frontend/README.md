# Smart Truck — Frontend

Next.js 14 (App Router) + Tailwind + Leaflet (CartoDB Positron tiles) +
react-three-fiber. See `../Hackaton/DAMM/PLAN/Specifications.md` for FRs.

## Setup

```bash
cd frontend
npm install
npm run dev
# → http://localhost:3000
```

The frontend talks to the backend at `NEXT_PUBLIC_API_URL` (defaults to
`http://localhost:8000`). To override, create `.env.local`:

```
NEXT_PUBLIC_API_URL=http://localhost:8000
```

## Routes

- `/`           — dashboard (FR-013).
- `/truck`      — 3D truck twin (FR-015).
- `/pick-list`  — Smart Hoja Carga viewer (FR-016).
- `/driver`     — driver mobile mockup (FR-017).

## Layout

```
app/
  layout.tsx          # root layout
  page.tsx            # main dashboard (TODO)
  truck/page.tsx      # 3D twin (TODO)
  pick-list/page.tsx  # Smart Hoja Carga (TODO)
  driver/page.tsx     # driver mockup (TODO)
components/           # shared components — TODO
lib/api.ts            # typed backend client
```
