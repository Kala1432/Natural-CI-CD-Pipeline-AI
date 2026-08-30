/**
 * FluxForge logo — hexagon shield containing an infinity loop
 * (representing continuous CI/CD flow) with two connection nodes.
 *
 * Two color modes:
 *  - "onDark" (default): white outline + light-blue accent, designed for
 *    dark UIs (the main app header, the landing page on dark bg, etc.)
 *  - "onLight": navy outline + bright blue accent, designed for light
 *    backgrounds (favicons, light cards, email link icons).
 *
 * Reusable across the app (header, landing page, email templates).
 */

const PALETTES = {
  onDark: {
    hexagon: "#ffffff",
    accent: "#7dd3fc",   // sky-300
    infinity: "#7dd3fc",
    node: "#ffffff",
  },
  onLight: {
    hexagon: "#0a1b3d",  // navy
    accent: "#1e90ff",   // dodger blue
    infinity: "#1e90ff",
    node: "#0a1b3d",
  },
}

const Mark = ({ size, variant = "onDark" }) => {
  const c = PALETTES[variant] || PALETTES.onDark
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 64 64"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      role="img"
      aria-label="FluxForge logo mark"
    >
      {/* Hexagon shield outline */}
      <path
        d="M32 3 L57 17 L57 47 L32 61 L7 47 L7 17 Z"
        fill="none"
        stroke={c.hexagon}
        strokeWidth="3.2"
        strokeLinejoin="round"
      />
      {/* Right-side accent stripe */}
      <path
        d="M57 17 L57 47 L40 56.5"
        fill="none"
        stroke={c.accent}
        strokeWidth="3.2"
        strokeLinejoin="round"
        strokeLinecap="round"
      />
      {/* Infinity loop */}
      <path
        d="M22 32
           a8 8 0 0 1 13 -4
           a8 8 0 0 1 13 4
           a8 8 0 0 1 -13 4
           a8 8 0 0 1 -13 -4 z"
        fill="none"
        stroke={c.infinity}
        strokeWidth="3.2"
        strokeLinecap="round"
      />
      {/* Top node */}
      <line x1="35" y1="13" x2="35" y2="20" stroke={c.node} strokeWidth="2" strokeLinecap="round" />
      <circle cx="35" cy="13" r="2.2" fill="none" stroke={c.node} strokeWidth="2" />
      {/* Bottom node */}
      <line x1="29" y1="51" x2="29" y2="44" stroke={c.node} strokeWidth="2" strokeLinecap="round" />
      <circle cx="29" cy="51" r="2.2" fill="none" stroke={c.node} strokeWidth="2" />
    </svg>
  )
}

/**
 * <Logo /> — the FluxForge mark, optionally followed by the wordmark.
 *
 * Props:
 *  - size:      pixel size of the square mark (default 32)
 *  - showText:  render the "FluxForge" wordmark next to the mark
 *  - variant:   "onDark" (default, white outline) | "onLight" (navy outline)
 *  - className: extra classes for the outer wrapper
 */
const Logo = ({
  size = 32,
  showText = false,
  variant = "onDark",
  className = "",
}) => {
  const textColor = variant === "onLight" ? "text-slate-900" : "text-white"

  return (
    <span
      className={`inline-flex items-center gap-2.5 ${className}`}
      aria-label="FluxForge"
    >
      <Mark size={size} variant={variant} />
      {showText && (
        <span
          className={`${textColor} font-semibold tracking-tight`}
          style={{ fontSize: Math.round(size * 0.5) }}
        >
          FluxForge
        </span>
      )}
    </span>
  )
}

export default Logo

/**
 * Returns the inline SVG markup for embedding in HTML emails.
 */
export const logoMarkupForEmail = (size = 96) => {
  return `
<svg xmlns="http://www.w3.org/2000/svg" width="${size}" height="${size}" viewBox="0 0 64 64" role="img" aria-label="FluxForge">
  <path d="M32 3 L57 17 L57 47 L32 61 L7 47 L7 17 Z" fill="none" stroke="#0a1b3d" stroke-width="3.2" stroke-linejoin="round"/>
  <path d="M57 17 L57 47 L40 56.5" fill="none" stroke="#1e90ff" stroke-width="3.2" stroke-linejoin="round" stroke-linecap="round"/>
  <path d="M22 32 a8 8 0 0 1 13 -4 a8 8 0 0 1 13 4 a8 8 0 0 1 -13 4 a8 8 0 0 1 -13 -4 z" fill="none" stroke="#1e90ff" stroke-width="3.2" stroke-linecap="round"/>
  <line x1="35" y1="13" x2="35" y2="20" stroke="#0a1b3d" stroke-width="2" stroke-linecap="round"/>
  <circle cx="35" cy="13" r="2.2" fill="none" stroke="#0a1b3d" stroke-width="2"/>
  <line x1="29" y1="51" x2="29" y2="44" stroke="#0a1b3d" stroke-width="2" stroke-linecap="round"/>
  <circle cx="29" cy="51" r="2.2" fill="none" stroke="#0a1b3d" stroke-width="2"/>
</svg>`
}
