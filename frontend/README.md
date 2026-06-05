# TicketGuard Frontend

Two-screen UI for the TicketGuard pre-purchase audit, styled with a blend of
**claymorphism + glassmorphism + neumorphism** and a subtle **Three.js** 3D
clay-blob background.

## Screens

1. **URL input** — paste a ticket listing URL and run an audit.
2. **Report** — risk scorecard with an overall gauge, recommendation banner,
   four weighted dimension cards (website credibility, price, compliance,
   sightline), and a **Back** button to audit another listing.

## Stack

- React 18 + TypeScript + Vite
- Three.js (animated background)
- Framer Motion (screen transitions)
- Plain CSS design system in [src/styles/global.css](src/styles/global.css)
  (`.clay`, `.glass`, `.neu-inset`, `.neu-raised`)

## Develop

```bash
npm install
npm run dev      # http://localhost:5173
npm run build    # type-check + production build
```

## Backend wiring

The audit call lives in [src/api.ts](src/api.ts). It currently returns the
demo report in [src/data/mockReport.ts](src/data/mockReport.ts) after a short
delay. To use the real backend:

1. Set `USE_BACKEND = true` in [src/api.ts](src/api.ts).
2. Ensure the backend exposes `POST /api/audit` returning a `TicketReport`
   (see [src/types.ts](src/types.ts)). The dev server proxies `/api` to
   `http://localhost:8000` (configurable in [vite.config.ts](vite.config.ts)).

The `TicketReport` dimension shape mirrors the backend session-state contract
(`{ score, flags, detail }`) in `backend/core/state_keys.py`.
