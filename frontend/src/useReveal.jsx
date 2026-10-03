import React from "react";
import { InView } from "./primitives/InView.jsx";

/**
 * Reveal: the scroll-entrance wrapper used throughout the app. Internally
 * powered by the InView primitive (motion/react's useInView + variants) so
 * every section gets the same spring-eased blur/rise-in as it scrolls into
 * view, with an optional stagger delay between sibling sections.
 */
export function Reveal({ as = "div", delay = 0, className = "", style, children, ...rest }) {
  return (
    <InView
      as={as}
      className={className}
      style={style}
      transition={{ duration: 0.6, ease: [0.22, 1, 0.36, 1], delay: delay / 1000 }}
      {...rest}
    >
      {children}
    </InView>
  );
}
