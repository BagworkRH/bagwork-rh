/**
 * bagworkRH brand mark and wordmark (Spec 01 design direction).
 *
 * The mark is a set of rounded bars with the final one rising, reading as
 * "work -> reward". It deliberately avoids a literal shopping bag, since "bag"
 * is crypto slang for holding a losing position.
 *
 * Two rendering contexts, one source of truth:
 *   - `full` (header/footer): mark + wordmark
 *   - `mark` (favicons, OG images, docs): the glyph on its own
 *
 * The glyph uses `currentColor` so it inherits the surrounding text colour and
 * stays in sync with the theme tokens in `app/globals.css`.
 */
type BrandLogoProps = {
  variant?: "full" | "mark";
  /** Pixel size of the mark. The wordmark scales with it. */
  size?: number;
  className?: string;
};

/** The glyph only, coloured by the surrounding text. */
export function BrandMark({ size = 28, className }: Omit<BrandLogoProps, "variant">) {
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
      {/* Bar mark, echoing the YAP glyph but with a rising final bar to read
          as "work -> reward". Current-color so it inherits the header ink. */}
      <g fill="currentColor">
        <rect x="6" y="22" width="11" height="20" rx="5.5" />
        <rect x="22" y="12" width="11" height="30" rx="5.5" />
        <rect x="38" y="16" width="11" height="26" rx="5.5" opacity="0.65" />
        <rect x="54" y="6" width="4" height="36" rx="2" />
      </g>
    </svg>
  );
}

/** Mark + wordmark. The mark is `currentColor`, so the wordmark stays plain ink
 *  and the `RH` suffix takes the highlight accent. */
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
