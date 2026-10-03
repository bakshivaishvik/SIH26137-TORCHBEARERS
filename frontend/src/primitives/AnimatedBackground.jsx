import React, { useState, useId } from "react";
import { motion, AnimatePresence } from "motion/react";

/**
 * Adapted from motion-primitives' AnimatedBackground: a shared-layout
 * highlight that glides behind whichever child is currently hovered
 * (or active, via `activeId`). No Tailwind here — styled with our own
 * CSS variables so it matches the Silver Pine system.
 */
export function AnimatedBackground({
  children,
  highlightClassName = "animated-bg-highlight",
  transition = { type: "spring", bounce: 0.2, duration: 0.5 },
  enableHover = true,
  activeId = null,
}) {
  const uid = useId();
  const [hoveredId, setHoveredId] = useState(null);
  const highlightId = enableHover ? hoveredId : activeId;

  return (
    <>
      {React.Children.map(children, (child, index) => {
        if (!React.isValidElement(child)) return child;
        const id = child.props["data-id"] ?? index;
        const isHighlighted = id === highlightId;
        return React.cloneElement(child, {
          key: child.key ?? index,
          style: { position: "relative", ...(child.props.style || {}) },
          onMouseEnter: (e) => {
            if (enableHover) setHoveredId(id);
            child.props.onMouseEnter?.(e);
          },
          onMouseLeave: (e) => {
            if (enableHover) setHoveredId(null);
            child.props.onMouseLeave?.(e);
          },
          children: (
            <>
              <AnimatePresence>
                {isHighlighted && (
                  <motion.div
                    layoutId={`animated-bg-${uid}`}
                    className={highlightClassName}
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    exit={{ opacity: 0 }}
                    transition={transition}
                  />
                )}
              </AnimatePresence>
              <div style={{ position: "relative", zIndex: 1 }}>{child.props.children}</div>
            </>
          ),
        });
      })}
    </>
  );
}
