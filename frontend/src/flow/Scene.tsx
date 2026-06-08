import type { ReactNode } from "react";
import { motion } from "framer-motion";

/**
 * A full-viewport scene layer. Scenes enter from the right (pushing in) and exit
 * to the left (sliding away + slight shrink/blur), which reads as a camera
 * panning across a pipeline — without moving the (fixed, crisp) background.
 */

const EASE = [0.22, 1, 0.36, 1] as const;

const sceneVariants = {
  enter: { opacity: 0, x: 90, scale: 0.94 },
  center: { opacity: 1, x: 0, scale: 1 },
  exit: { opacity: 0, x: -90, scale: 0.97, filter: "blur(4px)" },
};

export function Scene({
  children,
  className,
}: {
  children: ReactNode;
  className?: string;
}) {
  return (
    <motion.div
      className={`flow-scene${className ? ` ${className}` : ""}`}
      variants={sceneVariants}
      initial="enter"
      animate="center"
      exit="exit"
      transition={{ duration: 0.6, ease: EASE }}
    >
      {children}
    </motion.div>
  );
}
