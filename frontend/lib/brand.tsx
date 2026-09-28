/**
 * bagworkRH brand mark and wordmark (Spec 01 design direction).
 *
 * The mark is a token diamond with an upward arrow through it: "work -> reward".
 * It deliberately avoids a literal shopping bag, since "bag" is crypto slang for
 * holding a losing position.
 *
 * Two rendering contexts, one source of truth:
 *   - `full` (header/footer): mark + wordmark
 *   - `mark` (favicons, OG images, docs): the glyph on its own
 * Colours mirror the CSS custom properties in `app/globals.css` so the logo
 * stays in sync with the theme.
 */
import { useId } from "react";

type BrandLogoProps = {
  variant?: "full" | "mark";
  /** Pixel size of the mark. The wordmark scales with it. */
  size?: number;
  className?: string;
};

/** The glyph only, coloured by the theme. */
export function BrandMark({ size = 28, className }: Omit<BrandLogoProps, "variant">) {
  // Gradient ids must be unique: the header and footer both render a mark,
  // and duplicate ids in one document make the second reference unpredictable.
  const gradientId = useId();

  return (
    <svg
      className={className}
      width={size}
      height={size}
      viewBox="0 0 64 64"
      role="img"
      aria-label="bagworkRH"
      focusable="false"
    >
      <defs>
        <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="#f7cf4a" />
          <stop offset="100%" stopColor="#f0b90b" />
        </linearGradient>
      </defs>
      {/* Token diamond */}
      <path
        d="M32 3 61 32 32 61 3 32Z"
        fill={`url(#${gradientId})`}
        stroke="rgba(255,255,255,0.22)"
        strokeWidth="1.5"
        strokeLinejoin="round"
      />
      {/* Facets, for depth at small sizes */}
      <path d="M32 3 61 32 32 32Z" fill="rgba(255,255,255,0.18)" />
      <path d="M32 3 3 32 32 32Z" fill="rgba(0,0,0,0.08)" />
      {/* Upward arrow: the "work -> reward" beat */}
      <path
        d="M32 15.5 46 30.5h-7.5V48h-13V30.5H18Z"
        fill="#0b0e14"
        stroke="#0b0e14"
        strokeWidth="1.5"
        strokeLinejoin="round"
      />
    </svg>
  );
}

/** Mark + wordmark, with `RH` accented to signal the Robinhood Chain scope. */
export default function BrandLogo({
  variant = "full",
  size = 28,
  className,
}: BrandLogoProps) {
  if (variant === "mark") {
    return <BrandMark size={size} className={className} />;
  }

  return (
    <span className={`brand-logo${className ? ` ${className}` : ""}`}>
      <BrandMark size={size} className="brand-logo-mark" />
      <span className="brand-logo-text">
        bagwork<span className="brand-logo-rh">RH</span>
      </span>
    </span>
  );
}
