# Cinematic Page-Flow & Scene Transitions Skill

> Implementation handbook for TicketGuard's "camera-like" page flow: a single
> fixed viewport where **scenes** (input → pipeline → agent → report) enter/exit
> with directional, transported transitions that *feel* like a camera panning
> across a pipeline — without a giant canvas (the grass background + R3F ball
> physics must stay crisp and untouched). Read this before building the flow.

---

## 1. The core illusion (why we don't move a big world)

We can NOT build a viewport-larger canvas and translate it — the grass texture
has limited resolution and would blur, and the R3F ball-rain layer must stay
put. So the "camera move" is faked **inside a fixed viewport**:

- The **background stays fixed** (grass + balls), with only a tiny (≤ ~24px)
  parallax nudge per phase to sell motion. Never scale or pan it enough to blur.
- Each **scene is a full-viewport layer** swapped via `AnimatePresence`.
- A transition reads as a camera move because the old scene **exits with
  direction** (slide + slight scale-down/blur) while the new scene **enters from
  the opposite side, pushing in (scale 0.92→1)**.
- A **transported object** (the URL "packet" / a light beam) flies across the
  seam between the exiting and entering scene, stitching two separate scenes
  into one continuous "the camera followed the data" motion.

Net effect: it looks like one world the camera glides through; technically it's
directional scene swaps + a flying connector + micro-parallax.

---

## 2. The toolbox (what we already have — no new deps)

`framer-motion@^11` is installed. These are the exact primitives to use:

| Need | API | Notes |
|---|---|---|
| Swap scenes with enter/exit | `<AnimatePresence mode="wait">` + `motion.div` with `initial/animate/exit` | One scene at a time; give each a stable `key`. |
| **Transported element across scenes** | **`layoutId`** (shared-element transition) | A `motion.div` with the same `layoutId` in two scenes auto-animates between their positions — this IS the "data packet flies to the next stage". |
| **Curved flight path** | `transition={{ layout: { path: arc() } }}` (`import { arc } from "motion/react"`) | Makes the packet arc instead of moving in a straight line. |
| Number count-up (final score) | animate a `motionValue` + `useTransform`, or `<AnimateNumber>` | Score gauge settles with a ticking number. |
| Orchestrated reveals | `variants` + `staggerChildren` / `delayChildren` on a parent | Reveal report parts in sequence. |
| Path draw (beam/edges) | SVG `stroke-dasharray`/`dashoffset` animated, or `motion.path` `pathLength` | For the "light beam" handoff + future trace edges. |
| Respect users | `useReducedMotion()` | If reduced → skip cinematics, jump to `report`. |
| Sync layout across siblings | `<LayoutGroup>` | When two non-co-rendering components affect each other's layout. |

Gotchas (from Motion docs):
- Exit animations need a **stable unique `key`** on each `AnimatePresence` child.
- `AnimatePresence` must sit **outside** the conditional that unmounts the child.
- `layout`/`layoutId` animate via `transform: scale()` → set `borderRadius`/
  `boxShadow` via `style` so Motion can scale-correct them; add `layout` to
  distorting children, or `layout="position"` for aspect-ratio changes.
- SVG elements don't support `layout`; animate their attributes (`cx`, `pathLength`) directly.
- For `mode="wait"`, use `ease:"easeIn"` on exit + `ease:"easeOut"` on enter for an overall easeInOut feel.

---

## 3. Reference material (study before building)

Official (authoritative — fetch when unsure):
- AnimatePresence: https://motion.dev/docs/react-animate-presence
- Layout & shared-element (`layoutId`): https://motion.dev/docs/react-layout-animations
- Arc paths: https://motion.dev/docs/arc · LayoutGroup: https://motion.dev/docs/react-layout-group
- AnimateNumber: https://motion.dev/docs/react-animate-number · Transitions: https://motion.dev/docs/react-transitions
- useReducedMotion: https://motion.dev/docs/react-use-reduced-motion
- App Store shared-layout tutorial (cards expand to full screen — the canonical
  "zoom into a scene" pattern): https://motion.dev/tutorials/react-app-store
- Magic Motion (how layout animation works, interactive): https://www.nan.fyi/magic-motion

Scrollytelling / step-driven storytelling (patterns & high-star repos — use for
step-trigger architecture and inspiration, not necessarily as deps):
- Scrollama (IntersectionObserver step triggers, framework-agnostic): https://github.com/russellsamora/scrollama
- react-scrollama: https://github.com/jsonkao/react-scrollama
- Code Hike (scene-synced content reveal): https://github.com/code-hike/codehike
- basement/scrollytelling (React + GSAP): https://github.com/basementstudio/scrollytelling
- GitHub topic hub: https://github.com/topics/scrollytelling

When to borrow which: our flow is **state/event-driven** (click + SSE + timers),
not scroll-driven, so we drive phases ourselves (§4) and only borrow the
"one beat at a time, sticky background, transported focus" *ideas* from
scrollytelling — we do NOT need a scroll library for the core flow.

---

## 4. Phase state machine (the spine)

Drive everything from one `phase`; each phase sets the camera target + scene.

```
input → dispatch(~1.2s anim) → pipeline(real: wait for SSE done)
      → handoff(~1s anim) → agent(timed: no backend yet) → settle(~0.8s) → report
```

- `dispatch` / `handoff` / `settle` are pure-frontend transition beats.
- `pipeline` = **real wait**: reuse the existing streaming `ThreatIntelPanel`;
  advance when its SSE `done` fires.
- `agent` = **timed choreography** for now (scripted "investigating…" lines),
  with a seam to later plug in the real ADK event stream from `osint_subagent`.
- Keep a single `CAMERA`/scene config object so phases, parallax offsets, and
  durations live in one place.
- Always provide a **Skip** control and a `useReducedMotion()` path that jumps
  straight to `report` with the full static report.

---

## 5. Patterns mapped to our transitions

- **input → pipeline:** the typed URL morphs into a glowing clay "packet"
  (`layoutId="url-packet"`) that arcs (`path: arc()`) toward the pipeline entry;
  input scene slides left + scales down, pipeline scene pushes in from the right.
- **pipeline reveal:** existing 13-source SSE stream plays inside the pipeline
  scene (already built — drop it in).
- **pipeline → agent:** results converge into a beam (`motion.path` `pathLength`)
  exiting the right edge; agent scene catches it on the left; agent core pulses.
- **agent → report (settle):** push-in (scale up then settle) collapses into the
  report hero; the risk gauge runs a number count-up to its final score.
- **background:** small parallax `x` per phase; optional one-shot horizontal
  "wind" impulse on the R3F balls so they react to the camera move.

---

## 6. Performance & guardrails

- Animate only `transform` + `opacity` (and `filter: blur` sparingly) — never
  `width/height/left/top` for the camera feel.
- Keep the background un-scaled to preserve grass crispness.
- Cap total scripted time; never block interaction — provide Skip.
- Verify in a **foreground** browser (the R3F caveat from the design skill).
- reduced-motion = correctness requirement, not a nice-to-have.

---

## 7. Build order (each step independently verifiable)

1. `phase` state machine + fixed-viewport scene swap (`AnimatePresence`,
   directional enter/exit) with placeholder scenes; prove the "camera pan" feel.
2. `dispatch` packet morph + `arc()` flight (`layoutId`).
3. Drop `ThreatIntelPanel` into the `pipeline` scene; advance on SSE `done`.
4. `agent` scene timed choreography + `handoff` beam (seam for ADK stream).
5. `settle` → `report` with gauge count-up; keep report scrollable/explorable.
6. Background parallax + ball wind impulse + reduced-motion + Skip + tests.
