import React from "react";
import { motion, AnimatePresence } from "motion/react";

const defaultTransition = { type: "spring", stiffness: 220, damping: 26, mass: 0.5 };

/** Minimal open/close disclosure, adapted from motion-primitives' Disclosure. */
export function Disclosure({ open, onOpenChange, children, className = "", style }) {
  return (
    <div className={className} style={style} data-open={open}>
      {React.Children.map(children, (child) =>
        React.isValidElement(child) ? React.cloneElement(child, { __open: open, __onOpenChange: onOpenChange }) : child
      )}
    </div>
  );
}

export function DisclosureTrigger({ children, __open, __onOpenChange }) {
  return React.isValidElement(children)
    ? React.cloneElement(children, {
        "aria-expanded": __open,
        onClick: (e) => {
          children.props.onClick?.(e);
          __onOpenChange?.(!__open);
        },
      })
    : children;
}

export function DisclosureContent({ children, __open, variants, transition = defaultTransition }) {
  return (
    <AnimatePresence initial={false}>
      {__open && (
        <motion.div
          initial="collapsed"
          animate="expanded"
          exit="collapsed"
          variants={
            variants || {
              collapsed: { height: 0, opacity: 0 },
              expanded: { height: "auto", opacity: 1 },
            }
          }
          transition={transition}
          style={{ overflow: "hidden" }}
        >
          {children}
        </motion.div>
      )}
    </AnimatePresence>
  );
}
