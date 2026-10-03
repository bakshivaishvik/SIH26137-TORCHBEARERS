import React from "react";
import { motion, useInView } from "motion/react";
import { useRef } from "react";

const defaultVariants = {
  hidden: { opacity: 0, y: 28, scale: 0.985, filter: "blur(3px)" },
  visible: { opacity: 1, y: 0, scale: 1, filter: "blur(0px)" },
};

/**
 * Adapted from motion-primitives' InView: reveals children (optionally
 * staggered, via `variants.visible.transition.staggerChildren`) once the
 * element scrolls into the viewport.
 */
export function InView({
  as: Tag = "div",
  children,
  variants = defaultVariants,
  viewOptions = { once: true, margin: "0px 0px -80px 0px" },
  transition = { duration: 0.6, ease: [0.22, 1, 0.36, 1] },
  className = "",
  style,
  ...rest
}) {
  const ref = useRef(null);
  const inView = useInView(ref, viewOptions);
  const MotionTag = motion[Tag] || motion.div;

  return (
    <MotionTag
      ref={ref}
      initial="hidden"
      animate={inView ? "visible" : "hidden"}
      variants={variants}
      transition={transition}
      className={className}
      style={style}
      {...rest}
    >
      {children}
    </MotionTag>
  );
}
