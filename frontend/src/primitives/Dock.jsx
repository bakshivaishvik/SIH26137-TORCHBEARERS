import React, { useRef, useState } from "react";
import { motion, useMotionValue, useSpring, useTransform } from "motion/react";

const SPRING = { mass: 0.1, stiffness: 150, damping: 12 };

/** Adapted from motion-primitives' Dock: macOS-style icon magnification nav. */
export function Dock({ children, className = "", style }) {
  const mouseX = useMotionValue(Infinity);
  return (
    <motion.div
      onMouseMove={(e) => mouseX.set(e.pageX)}
      onMouseLeave={() => mouseX.set(Infinity)}
      className={`dock ${className}`}
      style={style}
    >
      {React.Children.map(children, (child) =>
        React.isValidElement(child) ? React.cloneElement(child, { __mouseX: mouseX }) : child
      )}
    </motion.div>
  );
}

export function DockItem({ children, className = "", onClick, active, label, __mouseX }) {
  const ref = useRef(null);
  const [hovered, setHovered] = useState(false);

  const distance = useTransform(__mouseX, (val) => {
    const bounds = ref.current?.getBoundingClientRect() ?? { x: 0, width: 0 };
    return val - bounds.x - bounds.width / 2;
  });
  const widthSync = useTransform(distance, [-140, 0, 140], [40, 60, 40]);
  const width = useSpring(widthSync, SPRING);

  return (
    <motion.button
      ref={ref}
      type="button"
      onClick={onClick}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      style={{ width }}
      className={`dock-item ${active ? "active" : ""} ${className}`}
      aria-current={active ? "true" : undefined}
    >
      {label && (
        <motion.span
          className="dock-label"
          initial={{ opacity: 0, y: 6 }}
          animate={hovered ? { opacity: 1, y: 0 } : { opacity: 0, y: 6 }}
          transition={{ duration: 0.15 }}
        >
          {label}
        </motion.span>
      )}
      <span className="dock-icon">{children}</span>
      {active && <span className="dock-dot" />}
    </motion.button>
  );
}
