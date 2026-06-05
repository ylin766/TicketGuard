import { useEffect, useState } from "react";
import { BallRain } from "./BallRain";

/**
 * Full-viewport pitch background.
 *
 * A single grass photo is shown as a CSS `cover` background (see
 * `.pitch-bg-canvas` in global.css). One image, no tiling — so there are no
 * repeat seams and it stays crisp. Static and non-interactive, behind the UI.
 *
 * On top of the grass we render a physics-driven ball-rain overlay, unless the
 * user prefers reduced motion (in which case only the static grass shows).
 */
export function PitchScene() {
  const [animate, setAnimate] = useState(false);

  useEffect(() => {
    const mq = window.matchMedia("(prefers-reduced-motion: reduce)");
    setAnimate(!mq.matches);
    const onChange = () => setAnimate(!mq.matches);
    mq.addEventListener("change", onChange);
    return () => mq.removeEventListener("change", onChange);
  }, []);

  return (
    <>
      <div className="pitch-bg-canvas" aria-hidden="true" />
      {animate ? <BallRain /> : null}
    </>
  );
}
