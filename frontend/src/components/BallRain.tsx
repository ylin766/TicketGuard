import { Suspense, useEffect, useMemo, useRef, useState } from "react";
import { Canvas, useFrame } from "@react-three/fiber";
import { useGLTF } from "@react-three/drei";
import {
  Physics,
  RigidBody,
  BallCollider,
  CuboidCollider,
  type RapierRigidBody,
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
const BALL_RADIUS = 42; // px — identical for every ball (no size variation)
const WALL_THICKNESS = 40;
const Z_RANGE = 90; // balls roam within ±Z_RANGE on the depth axis
const COLLIDER_DEPTH = 180; // z half-extent; ≥ Z_RANGE so balls always rest on UI

useGLTF.preload(MODEL_URL);

/** UI blocks that balls should bounce off — input screen only. The report
 *  screen instead renders above the ball layer (see App / global.css), so its
 *  cards don't shove balls around. Missing elements park off-screen. */
const COLLIDER_SELECTORS = [".brand-logo", ".input-card", ".audit-button"];

/** Far-away parking spot for colliders whose element isn't on screen. */
const FAR_AWAY = 100000;

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

/** A single soccer ball rigid body, free to tumble in 3D within a z-band. */
function Ball({
  startX,
  startY,
  startZ,
  spin,
  scale,
  center,
  register,
}: {
  startX: number;
  startY: number;
  startZ: number;
  spin: [number, number, number];
  scale: number;
  center: THREE.Vector3;
  register: (body: RapierRigidBody | null) => void;
}) {
  const { scene } = useGLTF(MODEL_URL);
  const model = useMemo(() => scene.clone(true), [scene]);

  return (
    <RigidBody
      ref={register}
      ccd
      colliders={false}
      position={[startX, startY, startZ]}
      angularVelocity={spin}
      enabledTranslations={[true, true, true]}
      enabledRotations={[true, true, true]}
      restitution={0.45}
      friction={0.55}
      linearDamping={0.05}
      angularDamping={0.08}
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

/** Fixed walls: floor + left/right + front/back so balls stay in the box. */
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
      <RigidBody type="fixed" colliders={false} position={[0, 0, COLLIDER_DEPTH + WALL_THICKNESS]}>
        <CuboidCollider args={[w, h, WALL_THICKNESS]} />
      </RigidBody>
      <RigidBody type="fixed" colliders={false} position={[0, 0, -COLLIDER_DEPTH - WALL_THICKNESS]}>
        <CuboidCollider args={[w, h, WALL_THICKNESS]} />
      </RigidBody>
    </>
  );
}

/**
 * One kinematic collider that tracks a live DOM element every frame. Because
 * it's a kinematicPosition body, any movement (e.g. the user scrolling the
 * report) imparts velocity to balls it touches — so cards can shove balls.
 */
function TrackedCollider({ selector }: { selector: string }) {
  const ref = useRef<RapierRigidBody>(null);
  const [size, setSize] = useState<{ hw: number; hh: number }>({ hw: 1, hh: 1 });
  const sizeRef = useRef(size);
  sizeRef.current = size;

  useFrame(() => {
    const body = ref.current;
    if (!body) return;
    const el = document.querySelector(selector);
    const r = el?.getBoundingClientRect();
    if (!r || r.width === 0 || r.height === 0) {
      body.setNextKinematicTranslation({ x: FAR_AWAY, y: FAR_AWAY, z: 0 });
      return;
    }
    const hw = r.width / 2;
    const hh = r.height / 2;
    const cur = sizeRef.current;
    if (Math.abs(cur.hw - hw) > 2 || Math.abs(cur.hh - hh) > 2) {
      setSize({ hw, hh });
    }
    body.setNextKinematicTranslation({
      x: r.left + r.width / 2 - window.innerWidth / 2,
      y: window.innerHeight / 2 - (r.top + r.height / 2),
      z: 0,
    });
  });

  return (
    <RigidBody
      ref={ref}
      type="kinematicPosition"
      colliders={false}
      position={[FAR_AWAY, FAR_AWAY, 0]}
    >
      <CuboidCollider args={[size.hw, size.hh, COLLIDER_DEPTH]} />
    </RigidBody>
  );
}

/** Live kinematic colliders for every tracked UI block. */
function DomColliders() {
  return (
    <>
      {COLLIDER_SELECTORS.map((sel) => (
        <TrackedCollider key={sel} selector={sel} />
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
        // Staggered release: each ball starts progressively higher (plus jitter)
        // so they stream in at different times instead of one solid drop.
        y: h / 2 + 140 + i * 150 + Math.random() * 120,
        z: (Math.random() - 0.5) * 2 * Z_RANGE,
        spin: [
          (Math.random() - 0.5) * 8,
          (Math.random() - 0.5) * 8,
          (Math.random() - 0.5) * 8,
        ] as [number, number, number],
      })),
    [w, h],
  );

  // Keep references to every ball so we can wake them when the user scrolls.
  // A sleeping ball ignores gravity, so a moving card could otherwise leave it
  // floating in mid-air; waking them guarantees they always fall back down.
  const bodies = useRef<(RapierRigidBody | null)[]>([]);

  useEffect(() => {
    let raf = 0;
    const wake = () => {
      cancelAnimationFrame(raf);
      // Wake on the next frame so it runs after the scroll-driven layout shift.
      raf = requestAnimationFrame(() => {
        for (const b of bodies.current) b?.wakeUp();
      });
    };
    window.addEventListener("scroll", wake, { passive: true });
    window.addEventListener("wheel", wake, { passive: true });
    window.addEventListener("touchmove", wake, { passive: true });
    return () => {
      cancelAnimationFrame(raf);
      window.removeEventListener("scroll", wake);
      window.removeEventListener("wheel", wake);
      window.removeEventListener("touchmove", wake);
    };
  }, []);

  return (
    <Physics gravity={[0, -1800, 0]} timeStep={1 / 120}>
      <Walls w={w} h={h} />
      <DomColliders />
      {balls.map((b, i) => (
        <Ball
          key={b.id}
          startX={b.x}
          startY={b.y}
          startZ={b.z}
          spin={b.spin}
          scale={scale}
          center={center}
          register={(body) => {
            bodies.current[i] = body;
          }}
        />
      ))}
    </Physics>
  );
}

/** A row of overhead spotlights for an exhibition / stadium-floodlight look. */
function Spotlights({ w, h }: Viewport) {
  const count = 5;
  const targets = useMemo(
    () => Array.from({ length: count }, () => new THREE.Object3D()),
    [],
  );
  return (
    <>
      {targets.map((target, i) => {
        const t = i / (count - 1);
        const x = (t - 0.5) * w * 0.9;
        return (
          <group key={i}>
            <primitive object={target} position={[x, -h / 2, 0]} />
            <spotLight
              position={[x, h / 2 + 160, 320]}
              target={target}
              angle={0.6}
              penumbra={0.7}
              distance={0}
              decay={0}
              intensity={1.6}
              color="#ffffff"
            />
          </group>
        );
      })}
    </>
  );
}

export function BallRain() {
  const { w, h } = useViewport();

  return (
    <div className="ball-layer" aria-hidden="true">
      <Canvas
        orthographic
        dpr={[1, 1.5]}
        style={{ pointerEvents: "none" }}
        camera={{ position: [0, 0, 600], zoom: 1, near: 0.1, far: 4000 }}
        gl={{ antialias: true, alpha: true }}
      >
        <ambientLight intensity={0.85} />
        <hemisphereLight args={["#ffffff", "#9ec48a", 0.6]} />
        <directionalLight position={[150, 300, 400]} intensity={1.1} />
        <Spotlights w={w} h={h} />
        <Suspense fallback={null}>
          <Scene w={w} h={h} />
        </Suspense>
      </Canvas>
    </div>
  );
}
