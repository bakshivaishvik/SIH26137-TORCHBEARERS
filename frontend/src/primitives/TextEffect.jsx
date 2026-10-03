import React from "react";
import { motion } from "motion/react";

const defaultVariants = {
  container: {
    hidden: { opacity: 0 },
    visible: { opacity: 1, transition: { staggerChildren: 0.035 } },
  },
  item: {
    hidden: { opacity: 0, rotateX: 70, y: 8 },
    visible: { opacity: 1, rotateX: 0, y: 0, transition: { duration: 0.3, ease: [0.22, 1, 0.36, 1] } },
  },
};

const blurPreset = {
  container: { hidden: { opacity: 1 }, visible: { opacity: 1, transition: { staggerChildren: 0.02 } } },
  item: {
    hidden: { opacity: 0, filter: "blur(6px)" },
    visible: { opacity: 1, filter: "blur(0px)", transition: { duration: 0.35 } },
  },
};

/** Adapted from motion-primitives' TextEffect: per-character (or per-word) reveal. */
export function TextEffect({
  children,
  per = "char",
  delay = 0,
  as: Tag = "span",
  className = "",
  style,
  variants,
  preset,
}) {
  const text = typeof children === "string" ? children : "";
  const units = per === "word" ? text.split(/(\s+)/) : Array.from(text);
  const v = variants || (preset === "blur" ? blurPreset : defaultVariants);
  const MotionTag = motion[Tag] || motion.span;

  return (
    <MotionTag
      className={className}
      style={{ display: "inline-block", perspective: 600, ...style }}
      initial="hidden"
      animate="visible"
      variants={v.container}
      transition={{ delayChildren: delay }}
    >
      {units.map((unit, i) => (
        <motion.span
          key={i}
          variants={v.item}
          style={{ display: "inline-block", whiteSpace: unit === " " ? "pre" : "normal" }}
        >
          {unit}
        </motion.span>
      ))}
    </MotionTag>
  );
}
