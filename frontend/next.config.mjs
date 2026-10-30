/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: `${process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"}/api/:path*`,
      },
    ];
  },
  /**
   * Cache policy, stated explicitly because the defaults caused a real problem:
   * Next serves prerendered pages with `s-maxage=31536000`, and the hashed JS
   * chunks with a one-year immutable cache. After a deploy a browser that still
   * held the old document could render the entire old app from its own cache -
   * the fix shipped, the page did not change, and it looked like the deploy had
   * failed. Hashed assets are still cached forever (their name changes when
   * their content does); documents must revalidate.
   */
  async headers() {
    return [
      {
        source: "/:path*",
        headers: [{ key: "Cache-Control", value: "no-cache, must-revalidate" }],
      },
      {
        // More specific, and last, so it wins for build output.
        source: "/_next/static/:path*",
        headers: [
          { key: "Cache-Control", value: "public, max-age=31536000, immutable" },
        ],
      },
    ];
  },
};

export default nextConfig;
