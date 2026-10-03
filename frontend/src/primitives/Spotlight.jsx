import React from "react";
import { motion, useMotionValue, useSpring } from "motion/react";

const SPRING = { stiffness: 300, damping: 30 };

/**
 * Adapted from motion-primitives' Spotlight: a soft radial glow that
 * follows the cursor across a bordered container — used as the app's
 * hover-highlight treatment on panel borders, in Silver Pine's pine/wine
 * tones rather than the original's blue. Handles its own mousemove on the
 * wrapping element (bubbled up from any child), so it never blocks clicks.
 */
export function SpotlightPanel({ children, className = "", style, size = 320, color = "var(--pine-bright)" }) {
  const mouseX = useMotionValue(-size);
  const mouseY = useMotionValue(-size);
  const x = useSpring(mouseX, SPRING);
  const y = useSpring(mouseY, SPRING);

  function handleMove(e) {
    const rect = e.currentTarget.getBoundingClientRect();
    mouseX.set(e.clientX - rect.left - size / 2);
    mouseY.set(e.clientY - rect.top - size / 2);
  }
  function handleLeave() {
    mouseX.set(-size);
    mouseY.set(-size);
  }

  return (
    <div
      className={className}
      style={{ position: "relative", overflow: "hidden", ...style }}
      onMouseMove={handleMove}
      onMouseLeave={handleLeave}
    >
      <motion.div
        aria-hidden
        style={{
          position: "absolute",
          top: 0,
          left: 0,
          width: size,
          height: size,
          borderRadius: "50%",
          background: `radial-gradient(circle, ${color}1f 0%, transparent 72%)`,
          x,
          y,
          pointerEvents: "none",
          zIndex: 0,
        }}
      />
      <div style={{ position: "relative", zIndex: 1 }}>{children}</div>
    </div>
  );
}
