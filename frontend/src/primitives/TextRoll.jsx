import React from "react";
import { motion, AnimatePresence } from "motion/react";

/**
 * Adapted from motion-primitives' TextRoll: when `children` (a string)
 * changes, the old text rolls up/out and the new text rolls in — used for
 * live status lines ("click the map…" -> "re-optimizing…" -> "last reroute: 41ms").
 */
export function TextRoll({ children, as: Tag = "span", className = "", style }) {
  const text = typeof children === "string" ? children : String(children ?? "");
  const MotionTag = motion[Tag] || motion.span;

  return (
    <MotionTag className={className} style={{ display: "inline-block", overflow: "hidden", ...style }}>
      <AnimatePresence mode="wait" initial={false}>
        <motion.span
          key={text}
          initial={{ y: "60%", opacity: 0 }}
          animate={{ y: "0%", opacity: 1 }}
          exit={{ y: "-60%", opacity: 0 }}
          transition={{ duration: 0.22, ease: [0.22, 1, 0.36, 1] }}
          style={{ display: "inline-block" }}
        >
          {text}
        </motion.span>
      </AnimatePresence>
    </MotionTag>
  );
}
