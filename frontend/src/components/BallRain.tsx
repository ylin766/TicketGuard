import { Suspense, useEffect, useMemo, useState } from "react";
import { Canvas } from "@react-three/fiber";
import { useGLTF } from "@react-three/drei";
import {
  Physics,
  RigidBody,
  BallCollider,
  CuboidCollider,
} from "@react-three/rapier";
import * as THREE from "three";

/**
 * Physics-driven "ball rain" overlay.
 *
 * A handful of full-resolution soccer balls (Draco-compressed for transfer)
 * drop from the top of the viewport under gravity, collide with the page's UI
 * cards (logo / input / button) and the floor, then settle and fall asleep so
 * the simulation costs ~0 CPU once at rest.
 *
 * Coordinate system: an orthographic camera at zoom 1 maps 1 world unit to 1
 * CSS pixel with the origin at the viewport centre and +y pointing up. That
 * lets us convert any DOM rect (via getBoundingClientRect) straight into a
 * physics collider.
 */

const MODEL_URL = `${import.meta.env.BASE_URL}models/soccer-ball.glb`;
const BALL_COUNT = 20;
const BALL_RADIUS = 42; // px
const WALL_THICKNESS = 40;
const COLLIDER_DEPTH = 60; // z half-extent so locked-z balls can't slip past

useGLTF.preload(MODEL_URL);

/** Selectors of UI elements that balls should rest on (not pass through). */
const COLLIDER_SELECTORS = [".brand-logo", ".input-card", ".audit-button"];

interface Viewport {
  w: number;
  h: number;
}

function useViewport(): Viewport {
  const [vp, setVp] = useState<Viewport>(() => ({
    w: window.innerWidth,
    h: window.innerHeight,
  }));
  useEffect(() => {
    const onResize = () =>
      setVp({ w: window.innerWidth, h: window.innerHeight });
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, []);
  return vp;
}

/** A single soccer ball rigid body, constrained to the z = 0 plane. */
function Ball({
  startX,
  startY,
  scale,
  center,
}: {
  startX: number;
  startY: number;
  scale: number;
  center: THREE.Vector3;
}) {
  const { scene } = useGLTF(MODEL_URL);
  const model = useMemo(() => scene.clone(true), [scene]);

  return (
    <RigidBody
      ccd
      colliders={false}
      position={[startX, startY, 0]}
      enabledTranslations={[true, true, false]}
      enabledRotations={[false, false, true]}
      restitution={0.2}
      friction={0.9}
      linearDamping={0.15}
      angularDamping={0.4}
    >
      <BallCollider args={[BALL_RADIUS]} />
      <primitive
        object={model}
        scale={scale}
        position={[
          -center.x * scale,
          -center.y * scale,
          -center.z * scale,
        ]}
      />
    </RigidBody>
  );
}

/** Fixed walls: floor + left/right so balls stay on screen. */
function Walls({ w, h }: Viewport) {
  return (
    <>
      <RigidBody type="fixed" colliders={false} position={[0, -h / 2 - WALL_THICKNESS, 0]}>
        <CuboidCollider args={[w / 2 + WALL_THICKNESS, WALL_THICKNESS, COLLIDER_DEPTH]} />
      </RigidBody>
      <RigidBody type="fixed" colliders={false} position={[-w / 2 - WALL_THICKNESS, 0, 0]}>
        <CuboidCollider args={[WALL_THICKNESS, h, COLLIDER_DEPTH]} />
      </RigidBody>
      <RigidBody type="fixed" colliders={false} position={[w / 2 + WALL_THICKNESS, 0, 0]}>
        <CuboidCollider args={[WALL_THICKNESS, h, COLLIDER_DEPTH]} />
      </RigidBody>
    </>
  );
}

interface Rect {
  x: number;
  y: number;
  hw: number;
  hh: number;
}

/** Maps live DOM rects of UI cards into fixed physics colliders. */
function DomColliders() {
  const [rects, setRects] = useState<Rect[]>([]);

  useEffect(() => {
    const measure = () => {
      const next: Rect[] = [];
      for (const sel of COLLIDER_SELECTORS) {
        const el = document.querySelector(sel);
        if (!el) continue;
        const r = el.getBoundingClientRect();
        if (r.width === 0 || r.height === 0) continue;
        next.push({
          x: r.left + r.width / 2 - window.innerWidth / 2,
          y: window.innerHeight / 2 - (r.top + r.height / 2),
          hw: r.width / 2,
          hh: r.height / 2,
        });
      }
      setRects(next);
    };

    measure();
    // Re-measure after fonts load and the entrance animation settles, since
    // late layout shifts would otherwise leave colliders out of sync.
    const timers = [150, 400, 700, 1100].map((ms) =>
      window.setTimeout(measure, ms),
    );
    if (document.fonts?.ready) {
      document.fonts.ready.then(measure).catch(() => {});
    }
    const ro = new ResizeObserver(measure);
    ro.observe(document.body);
    for (const sel of COLLIDER_SELECTORS) {
      const el = document.querySelector(sel);
      if (el) ro.observe(el);
    }
    window.addEventListener("resize", measure);
    return () => {
      timers.forEach((t) => window.clearTimeout(t));
      ro.disconnect();
      window.removeEventListener("resize", measure);
    };
  }, []);

  return (
    <>
      {rects.map((r, i) => (
        <RigidBody key={i} type="fixed" colliders={false} position={[r.x, r.y, 0]}>
          <CuboidCollider args={[r.hw, r.hh, COLLIDER_DEPTH]} />
        </RigidBody>
      ))}
    </>
  );
}

function Scene({ w, h }: Viewport) {
  const { scene } = useGLTF(MODEL_URL);

  // Normalise the model once: scale so its largest dimension == ball diameter,
  // and capture its centre so the visual mesh aligns with the ball collider.
  const { scale, center } = useMemo(() => {
    const box = new THREE.Box3().setFromObject(scene);
    const size = box.getSize(new THREE.Vector3());
    const maxDim = Math.max(size.x, size.y, size.z) || 1;
    return {
      scale: (BALL_RADIUS * 2) / maxDim,
      center: box.getCenter(new THREE.Vector3()),
    };
  }, [scene]);

  const balls = useMemo(
    () =>
      Array.from({ length: BALL_COUNT }, (_, i) => ({
        id: i,
        x: (Math.random() - 0.5) * (w - BALL_RADIUS * 2),
        y: h / 2 + 120 + Math.random() * (h + 600),
      })),
    [w, h],
  );

  return (
    <Physics gravity={[0, -1800, 0]} timeStep={1 / 120}>
      <Walls w={w} h={h} />
      <DomColliders />
      {balls.map((b) => (
        <Ball key={b.id} startX={b.x} startY={b.y} scale={scale} center={center} />
      ))}
    </Physics>
  );
}

export function BallRain() {
  const { w, h } = useViewport();

  return (
    <div className="ball-layer" aria-hidden="true">
      <Canvas
        orthographic
        dpr={[1, 1.5]}
        camera={{ position: [0, 0, 300], zoom: 1, near: 0.1, far: 2000 }}
        gl={{ antialias: true, alpha: true }}
      >
        <ambientLight intensity={1.1} />
        <hemisphereLight args={["#ffffff", "#9ec48a", 0.7]} />
        <directionalLight position={[200, 400, 300]} intensity={1.8} />
        <Suspense fallback={null}>
          <Scene w={w} h={h} />
        </Suspense>
      </Canvas>
    </div>
  );
}
