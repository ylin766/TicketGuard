# TicketGuard Frontend Design System & Build Skill

> Read this before building or editing any frontend component. It captures the
> exact visual language, the real-world references it imitates, the locked
> dependency versions, the reusable patterns, the test framework, and the
> end-to-end workflow — so any agent can extend the UI at the same quality and
> direction.

---

## 0. Overall direction & how to learn this codebase

### What "good" means here (the north star)
Every screen should feel like **soft clay toys arranged on a real football
pitch**: warm, tactile, rounded, matte, with green-tinted soft shadows so
elements look *embedded in the scene*, never like flat cards floating on white.
Motion is **playful but never in the way** (physics balls that respect the UI,
reduced-motion fallbacks). When in doubt, choose the option that is **softer,
rounder, more tactile, and more saturated-but-not-washed-out**.

### How to learn before you touch code (do this first, every time)
1. **Read this skill end to end**, then open the three anchor files it keeps
   pointing at:
   - `src/styles/global.css` — the `:root` tokens + the reusable surface classes
     (`.clay`, `.glass`, `.neu-inset`, `.neu-raised`). This is the visual source
     of truth.
   - `src/components/BallRain.tsx` — the entire physics/3D pattern library.
   - `src/components/RiskGauge.tsx` + `ReportScreen.css` — how colored emboss is
     done correctly (no hue wash).
   - `src/components/threatintel/` — the data-driven source-panel registry (§6.5)
     for rendering many typed backend results.
2. **Imitate, don't invent.** Find the closest existing component and mirror its
   structure, class composition, and token usage. New shadows/colors/radii are a
   smell — reuse the tokens and surface classes.
3. **Ground every visual decision in a real reference** (see §0.1). We do not
   freestyle a "raised" or "frosted" look; we copy an established, named recipe
   and tune it with the project tokens.
4. **Verify assumptions in a real browser**, not from memory (see §7). The 3D
   layer in particular behaves differently than plain DOM.

### 0.1 Reference material (where the design & techniques come from)
Fetch the relevant page before implementing an unfamiliar effect — APIs and
recipes drift, and grounding beats guessing.

| Topic | Authoritative reference |
|---|---|
| Claymorphism (style origin) | https://hype4.academy/articles/coding/how-to-create-claymorphism-using-css · generator https://hype4.academy/tools/claymorphism-generator |
| Neumorphism / Soft UI | https://neumorphism.io (shadow generator) |
| Glassmorphism | https://hype4.academy/tools/glassmorphism-generator |
| SVG lighting filters (3D emboss) | https://developer.mozilla.org/en-US/docs/Web/SVG/Element/feDiffuseLighting · https://developer.mozilla.org/en-US/docs/Web/SVG/Element/feSpecularLighting |
| React Three Fiber (v8) | https://r3f.docs.pmnd.rs/ |
| drei helpers | https://github.com/pmndrs/drei |
| react-three-rapier (v1) | https://github.com/pmndrs/react-three-rapier |
| Rapier physics concepts | https://rapier.rs/docs/ |
| Free 3D models (CC-BY) | https://poly.pizza |
| Draco / glTF compression | https://github.com/CesiumGS/gltf-pipeline |
| Fredoka font | https://fonts.google.com/specimen/Fredoka |
| Framer Motion (entrance anim) | https://www.framer.com/motion/ |
| Vitest (test runner) | https://vitest.dev/ |
| Testing Library (React) | https://testing-library.com/docs/react-testing-library/intro/ |
| jest-dom matchers | https://github.com/testing-library/jest-dom |

### 0.2 Possibly-useful material (reach for these when extending)
- **Color/contrast:** keep text on clay readable — use `--ink` / `--ink-soft`
  / `--ink-faint`, check WCAG AA. Tool: https://webaim.org/resources/contrastchecker/
- **More CC-BY 3D assets:** https://poly.pizza and https://sketchfab.com (filter
  to downloadable + CC). Always keep attribution.
- **Easing for clay motion:** prefer soft spring/`cubic-bezier(0.22, 1, 0.36, 1)`
  (used in report entrance) over linear.
- **Icon style:** rounded, filled, friendly (emoji are used as quick category
  glyphs in `ScoreCard`); keep any future icon set rounded to match Fredoka.

---

## 1. Design DNA (what we are imitating)

The UI blends three named UI styles on a football-pitch theme. Every new
component MUST read as belonging to this family.

| Style | Role in TicketGuard | Reference / origin |
|---|---|---|
| **Claymorphism** | Primary surface language — puffy, soft, matte 3D cards & buttons | Coined by **Michal Malewicz / Hype4 Academy**. Generator: https://hype4.academy/tools/claymorphism-generator · Article: https://hype4.academy/articles/coding/how-to-create-claymorphism-using-css |
| **Neumorphism** | Pressed-in fields & raised buttons (`neu-inset`, `neu-raised`) | Soft-UI / neumorphism (dual inset/outset shadows). |
| **Glassmorphism** | Light frosted chips & banners (`glass`) | Frosted translucent pills. |

**Core idea:** warm pistachio-cream "clay" surfaces sitting on a real grass
pitch, with green-tinted shadows (never pure black) so cards feel embedded in
the scene rather than floating on white.

### The claymorphism recipe (memorize this)
A clay surface = **outer green-tinted cast shadow** + **inner top-left white
highlight** + **inner bottom-right green shade**. Shadows are *same-family*
(green-tinted), never neutral grey/black. This is why it reads as soft clay and
not as a generic card.

```css
box-shadow:
  0 22px 46px -10px var(--clay-cast),   /* outer drop, green-tinted */
  inset 6px 6px 14px var(--clay-hi),    /* inner highlight, top-left */
  inset -7px -9px 16px var(--clay-lo);  /* inner shade, bottom-right */
```

---

## 2. Design tokens (source of truth: `src/styles/global.css` `:root`)

Always use these CSS variables — never hardcode hex values in components.

```
Backgrounds (pitch greens):  --bg-1 #d8f3c8  --bg-2 #a7e090  --bg-3 #4ca85a
Clay surface:                --clay-base #eef4e3  --clay-top #f7faf0  --clay-bottom #e3ecd5
Clay shadow ingredients:     --clay-hi rgba(255,255,255,.95)   (inner highlight)
                             --clay-lo rgba(150,178,138,.55)   (inner shade, green)
                             --clay-cast rgba(22,58,34,.3)     (outer cast, green)
Ink (text):                  --ink #233027  --ink-soft #4f5e52  --ink-faint #8a988c
Accent:                      --accent #2e9e54  --accent-soft #6fc683
Verdict:                     --safe #2bb673 / --caution #e8a13a / --danger #e5484d
                             (+ *-soft variants)
Radius scale:                --radius-lg 34px  --radius-md 24px  --radius-sm 18px
Font:                        --font-body / --font-display = "Fredoka" (rounded)
Glass:                       --glass-bg rgba(255,255,255,.55)  --glass-border rgba(255,255,255,.7)
```

**Font:** [Fredoka](https://fonts.google.com/specimen/Fredoka) (Google Fonts,
weights 400–700), loaded in `index.html`. One rounded family everywhere;
**weight sets hierarchy**, not different typefaces. Headings use weight 700–900.

---

## 3. Reusable surface classes (in `global.css`)

Compose components from these — do not reinvent shadows per component.

| Class | Shape | Use for |
|---|---|---|
| `.clay` | convex puffy card, `--radius-lg` | main panels, hero |
| `.glass` | lighter convex pill, `--radius-md` | chips, banners |
| `.neu-inset` | concave pressed-in, no outer cast | input fields, gauges' wells |
| `.neu-raised` | convex button; lifts on hover, presses on `:active` | buttons |
| `.eyebrow` | uppercase, letter-spaced micro-label | section kickers |

When you need an embossed *colored* shape (progress fill, ring), see §6.

---

## 4. 3D / physics stack (LOCKED versions — do not upgrade)

The homepage "ball rain" uses React Three Fiber + Rapier. These versions are
pinned for **React 18** compatibility. **Do NOT bump to fiber v9 / rapier v2 —
they require React 19 and will break the build.**

```
react 18.3.1 · react-dom 18.3.1
three 0.166.1
@react-three/fiber 8.18.0      (v8 — needs ResizeObserver to report size > 0 before it boots)
@react-three/drei 9.122.0
@react-three/rapier ^1.5.0     (v1)
```

Reference docs:
- R3F: https://r3f.docs.pmnd.rs/
- drei: https://github.com/pmndrs/drei
- react-three-rapier: https://github.com/pmndrs/react-three-rapier
- Rapier physics: https://rapier.rs/docs/

### 3D asset sourcing & compression
- **Model source:** [Poly Pizza](https://poly.pizza) — free low-poly models.
  Current ball: *"Simple soccer football"* by **Smirnoff Alexander**, license
  **CC-BY 3.0** (attribution required — keep it in commit messages / credits).
- **Compression:** use Draco for *transfer* only, never reduce faces (keep full
  mesh precision). Command:
  ```bash
  npx --yes gltf-pipeline@4 -i input.glb -o output.glb -d
  ```
  (Compressed the ball 533.9 KB → 216 KB, face count unchanged.)
- drei's `useGLTF` auto-loads the Draco decoder from the gstatic CDN at runtime.
- Store models in `frontend/public/models/`; reference via
  `` `${import.meta.env.BASE_URL}models/<name>.glb` ``.

### Physics patterns that work (see `src/components/BallRain.tsx`)
- **Coordinate system:** orthographic camera at `zoom: 1` ⇒ **1 world unit = 1
  CSS pixel**, origin at viewport center, +y up. This lets any DOM
  `getBoundingClientRect()` map straight onto a physics collider.
- **Prevent tunnelling into UI:** enable `ccd` on fast bodies + use a finer
  `<Physics timeStep={1/120}>`.
- **DOM-tracking colliders:** a `type="kinematicPosition"` RigidBody updated each
  `useFrame` via `setNextKinematicTranslation` follows a live DOM rect; park it
  far away when the element is absent.
- **Sleeping bodies float bug:** a sleeping ball ignores gravity, so a moving
  kinematic collider can leave it mid-air. Fix: `wakeUp()` all bodies on
  `scroll` / `wheel` / `touchmove`.
- **Overlay must not block clicks:** the canvas layer is `pointer-events:none`
  (and `.ball-layer * { pointer-events:none !important }` because R3F re-enables
  it on its own wrapper for raycasting). Pass `style={{ pointerEvents:"none" }}`
  to `<Canvas>` too.
- **Layering:** balls render at `z-index:2` (in front of UI on the input
  screen). On the report screen, raise content with `.app-shell--above-balls`
  (`z-index:3`) so balls don't cover info — the two never collide there.
- **Accessibility:** gate the animation behind `prefers-reduced-motion` (grass
  only, no balls) and cap `dpr={[1, 1.5]}`.

---

## 5. Lighting for clay (3D scene)

Clay is **matte** — avoid hard specular/plastic highlights.
- Use soft `ambientLight` + `hemisphereLight` + a gentle `directionalLight`.
- For "spotlight row" / stadium looks with `spotLight`: our world unit is a
  pixel, so the default physically-correct `decay={2}` (1/d²) kills intensity
  over hundreds of px. **Set `decay={0}` and `distance={0}`** or the lights do
  nothing and balls look dark.

---

## 6. Embossed COLORED shapes (rings, progress fills)

When a *colored* element must look raised (e.g. the risk gauge ring, score
bars), keep the base hue saturated. **Key rule: a white blend over a color =
washed-out pastel (red→pink). Use `multiply` (darken-only) for shading so the
hue stays true; add only a thin white highlight.**

### Linear progress fills → pure CSS (cheap, preferred)
Keep the inline `background: <verdictColor>`; add inset emboss via shadow only:
```css
.score-bar-fill {
  box-shadow:
    inset 0 2px 2px rgba(255,255,255,.55),   /* top inner highlight */
    inset 0 -3px 4px rgba(31,42,28,.18);      /* bottom inner shade (green-dark) */
}
```

### Circular ring → SVG lighting filter (see `RiskGauge.tsx`)
Use the stroke's own alpha as a bump map; clip every lighting layer back
**into** the stroke with `feComposite operator="in"` so nothing spills outside:
1. `feGaussianBlur` on `SourceAlpha` → rounded "bump".
2. `feDiffuseLighting` (matte, no specular) with a `feDistantLight`.
3. Blend the diffuse onto the colored stroke with **`mode="multiply"`** (keeps
   the hue saturated — no pink wash).
4. Add a *narrow* inner top highlight (white, low opacity) and a *same-family
   dark* inner bottom shade (e.g. `#1f2a1c`, never pure black).
- Tuning knobs: `surfaceScale` (bulge height), light `elevation` (contrast),
  blur `stdDeviation` (softness), highlight `floodOpacity` (sheen).
- Reference: MDN SVG filters —
  https://developer.mozilla.org/en-US/docs/Web/SVG/Element/feDiffuseLighting ·
  https://developer.mozilla.org/en-US/docs/Web/SVG/Element/feSpecularLighting

---

## 6.5 Data-driven panels (source-panel registry pattern)

When rendering a list of heterogeneous backend results that each carry their own
native fields (e.g. the threat-intel sources — VirusTotal engine counts, RDAP
registration date, Tranco rank, IPGeo country), **do NOT render them all with one
generic icon+text row** (that throws away the data) and **do NOT hand-write a
fully independent component per item** (unmaintainable). Use a **registry**: one
shared clay shell + a per-type body renderer keyed by name. Reference
implementation: `src/components/threatintel/`.

Structure (mirror this for any similar "many typed results" feature):
- `fixtures.ts` — capture **real** backend output (clean + flagged variants) so
  panels are built and tested **without a live backend**. Get the real shapes by
  actually running the backend once (don't invent field names).
- `fields.ts` — **safe typed accessors** (`num/str/bool/strList`) that narrow the
  `[key: string]: unknown` fields to a type with a fallback, plus derived helpers
  (e.g. `domainAge`, date formatting). Panels must never crash on a missing field.
- `icons.tsx` — one stroke-based, `currentColor`, clay-sized glyph per type +
  a `glyphForX(name)` mapper with a generic fallback. No emoji (see §3 rules).
- `SourcePanel.tsx` — the shared shell (icon, name, verdict pip, detail) that
  dispatches to a body via a `Record<string, (props) => JSX | null>` registry.
  Unknown types fall back to detail-only. Reusable micro-viz live here: ratio
  bars, chips, big stat, key/value — all built from clay tokens (§2–3).
- Group results by meaning (e.g. "Threat scan" vs "Domain intelligence") and give
  the container a **verdict summary** header (counts + streaming progress).

Rules:
- Each micro-visualization is **colored by verdict** (`--safe/--caution/--danger`)
  and uses the §6 colored-emboss rules (no hue wash) for any filled bar.
- Adding a new source = add a fixture entry + a glyph + one body renderer +
  register it. No edits to the shell or the panel.
- Test the registry through the full panel with the fixtures (§8): assert each
  type renders its key field, and scope queries with `within(panelEl)` to avoid
  matching the same word in both a chip and the detail sentence.

---


## 7. Build, run & verify

```bash
cd frontend
npm install          # first time
npm run dev          # http://localhost:5173
npm run build        # tsc -b && vite build — MUST pass before commit
npm test             # vitest run — unit/component tests, MUST pass before commit
npm run test:watch   # vitest in watch mode while developing
npm run test:ui      # vitest UI dashboard in the browser
```

- Verify visuals in a **real, foreground browser tab**. A backgrounded/hidden
  tab throttles `ResizeObserver` + `requestAnimationFrame`, which prevents R3F
  v8 from booting and breaks screenshots — that is an environment limitation,
  not a code bug.
- The physics bundle is large (~3.2 MB / ~1.1 MB gzip from Rapier WASM + three +
  R3F). Acceptable for now; lazy-load / code-split if it becomes a concern.

---

## 8. Test framework (Vitest + Testing Library)

We test components behaviorally — what the user sees and does — not
implementation details.

### Stack & config
| Piece | Value | File |
|---|---|---|
| Runner | **Vitest** (`vitest run`) | `vite.config.ts` → `test` block |
| DOM env | **jsdom** | `test.environment: "jsdom"` |
| Render/query | **@testing-library/react** | — |
| User actions | **@testing-library/user-event** | — |
| Matchers | **@testing-library/jest-dom** (`toBeInTheDocument`, …) | `src/test/setup.ts` |
| Globals | `describe/it/expect` available without imports | `test.globals: true` |
| Setup | imports jest-dom before every file | `src/test/setup.ts` |

Test files live next to the component: `Component.test.tsx` (see
`src/components/ThreatIntelPanel.test.tsx` as the reference example) or as
`*.test.ts` for pure logic (see `src/types.test.ts`).

### What to test (and what NOT to)
- **DO** test: loading/empty/error/success states, conditional rendering,
  user interactions (`userEvent.click/type`), accessible text/roles, and that
  network calls are made with the right inputs.
- **DON'T** test: exact shadow/box CSS, the WebGL/physics canvas (R3F doesn't
  run under jsdom — keep `BallRain` logic-free enough to skip, or mock it).
- **Query by user-visible things:** `getByRole`, `getByText`, `getByLabelText`.
  Avoid querying by class names or test-ids unless nothing else works.
- **Mock the network:** `vi.spyOn(globalThis, "fetch").mockResolvedValue(...)`;
  reset with `vi.restoreAllMocks()` in `beforeEach`. Use `findBy*` / `waitFor`
  for async UI.

### Minimal test pattern
```tsx
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MyThing } from "./MyThing";

describe("MyThing", () => {
  it("does the user-visible thing", async () => {
    render(<MyThing />);
    await userEvent.click(screen.getByRole("button", { name: /audit/i }));
    expect(screen.getByText(/result/i)).toBeInTheDocument();
  });
});
```

---

## 9. End-to-end workflow: from search → reference → design → check → test → ship

Follow these stages in order for any non-trivial component or visual change.

1. **Search / orient** — Read this skill + the anchor files (§0). Grep the
   codebase for the closest existing component and the tokens/classes it uses.
   Identify which surface class and which verdict/accent colors apply.
2. **Reference** — For any unfamiliar effect, fetch the authoritative page from
   §0.1 (e.g. claymorphism recipe, SVG lighting filter, R3F/Rapier API). Ground
   the technique; don't freestyle. Note the exact recipe you'll adapt.
3. **Design** — Compose from existing surface classes + tokens. Decide hierarchy
   via font-weight, spacing via the radius scale. For colored emboss, plan the
   `multiply`-shade + thin-highlight approach (§6) so the hue stays true. Sketch
   states (default / hover / active / loading / empty / error).
4. **Implement** — Edit the real files; keep changes minimal and idiomatic.
   Reuse `--vars`; never hardcode hex. Respect `prefers-reduced-motion` and
   `pointer-events` layering rules. For 3D, honor the locked versions (§4) and
   pixel=unit coordinate system.
5. **Check (static)** — Run `get_errors` / TypeScript; run `npm run build`
   (`tsc -b && vite build`) and ensure it passes with no type errors. Re-read the
   diff against the §11 checklist.
6. **Test** — Add/adjust a `*.test.tsx` for new behavior (states + interactions).
   Run `npm test` (`vitest run`) until green. Mock network; query by role/text.
7. **Verify visually** — Load `http://localhost:5173` in a **real foreground
   browser**. Confirm clay feel, color fidelity (no pink wash), motion, that
   buttons remain clickable (overlay `pointer-events`), and reduced-motion
   fallback. The embedded/hidden verification tab can't boot R3F — don't trust a
   blank canvas there.
8. **Ship** — Atomic, conventional commits (`feat(frontend): …`, `fix(frontend):
   …`, `docs: …`), one logical change each. Build + tests green. Branch off the
   umbrella `Paxton/feat-frontend`; open focused sub-branches; merge back
   `--no-ff`. Credit any CC-BY assets.

---

## 10. Pitfalls already discovered (don't repeat these)

- **R3F v8 won't boot in a hidden/backgrounded tab** — ResizeObserver/rAF are
  throttled so it never measures the container. Not a bug; verify in foreground.
- **`<Canvas>` re-enables `pointer-events`** on its wrapper → blocked clicks.
  Force `pointer-events:none` on the canvas and all `.ball-layer` descendants.
- **Sleeping physics bodies float** when a kinematic collider moves; `wakeUp()`
  them on scroll/wheel/touchmove.
- **`spotLight` with default `decay={2}` goes black** in a pixel-scaled world;
  set `decay={0}` / `distance={0}`.
- **White blend over a color = pastel wash** (red→pink). Shade colored emboss
  with `multiply`; keep highlights thin.
- **Don't upgrade R3F/rapier** to v9/v2 — they need React 19 and break the build.
- **`cd frontend` first** for every npm command; the persistent terminal may not
  be in the subfolder.

---

## 11. Conventions checklist for a NEW component

- [ ] Read this skill + anchor files; imitated the closest existing component.
- [ ] Grounded any new effect in a §0.1 reference before coding.
- [ ] Build from `.clay` / `.glass` / `.neu-inset` / `.neu-raised`; don't invent shadows.
- [ ] Use design tokens (CSS vars), not hardcoded colors; verdict colors for risk states.
- [ ] Fredoka font inherited; set hierarchy via font-weight only.
- [ ] Shadows green-tinted (same-family), never neutral black.
- [ ] Colored emboss: `multiply` for shade + thin white highlight (no hue wash).
- [ ] Rendering many typed backend results? Use the source-panel registry (§6.5),
      not one generic row or N independent components.
- [ ] Respect `prefers-reduced-motion` for any animation.
- [ ] Keep clickable UI above overlays; overlays `pointer-events:none`.
- [ ] Added/updated `*.test.tsx` for new states & interactions; `npm test` green.
- [ ] `npm run build` passes; verified visually in a foreground browser.
- [ ] Atomic conventional commits; merged back via the umbrella branch `--no-ff`.
- [ ] Credit any CC-BY 3D assets (e.g. ball by Smirnoff Alexander, CC-BY 3.0).
```
