/**
 * Full-viewport pitch background.
 *
 * A single grass photo is shown as a CSS `cover` background (see
 * `.pitch-bg-canvas` in global.css). One image, no tiling — so there are no
 * repeat seams and it stays crisp. Static and non-interactive, behind the UI.
 */
export function PitchScene() {
  return <div className="pitch-bg-canvas" aria-hidden="true" />;
}
