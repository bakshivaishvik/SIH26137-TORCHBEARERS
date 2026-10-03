import React, { useEffect, useState } from "react";
import { motion, AnimatePresence } from "motion/react";

/** Adapted from motion-primitives' TextLoop: cycles through children, one at a time. */
export function TextLoop({ children, interval = 2200, className = "", style }) {
  const items = React.Children.toArray(children);
  const [index, setIndex] = useState(0);

  useEffect(() => {
    if (items.length < 2) return;
    const id = setInterval(() => setIndex((i) => (i + 1) % items.length), interval);
    return () => clearInterval(id);
  }, [items.length, interval]);

  return (
    <span className={className} style={{ position: "relative", display: "inline-block", ...style }}>
      <AnimatePresence mode="wait" initial={false}>
        <motion.span
          key={index}
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: -8 }}
          transition={{ duration: 0.28, ease: [0.22, 1, 0.36, 1] }}
          style={{ display: "inline-block" }}
        >
          {items[index]}
        </motion.span>
      </AnimatePresence>
    </span>
  );
}
