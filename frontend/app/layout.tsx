import type { Metadata, Viewport } from "next";
import { Archivo, Big_Shoulders_Display, IBM_Plex_Mono } from "next/font/google";
import "./globals.css";
import Header from "@/components/Header";
import Footer from "@/components/Footer";
import { WalletProvider } from "@/hooks/useWallet";

/**
 * bagworkpro.xyz's type system: Archivo for text, Big Shoulders for display,
 * IBM Plex Mono for figures.
 *
 * Loaded through `next/font` so they are downloaded at build time and served
 * from our own origin — no runtime request to Google, no third-party font host
 * in the request path, and `display: "swap"` with Next's automatic size-adjust
 * fallback so text does not reflow when the real face lands.
 */
const sans = Archivo({
  subsets: ["latin"],
  variable: "--font-sans-loaded",
  display: "swap",
});
const display = Big_Shoulders_Display({
  subsets: ["latin"],
  variable: "--font-display-loaded",
  display: "swap",
});
const mono = IBM_Plex_Mono({
  subsets: ["latin"],
  weight: ["400", "500", "600"],
  variable: "--font-mono-loaded",
  display: "swap",
});

export const metadata: Metadata = {
  title: "bagworkRH — Get paid for the posts you make",
  description:
    "Post for a campaign, earn verified token rewards, claim on-chain. Connect your social accounts and wallet to get paid.",
};

/**
 * `viewportFit: "cover"` is what makes `env(safe-area-inset-*)` report real
 * values on a notched phone, so the header and footer can stay clear of the
 * status bar and home indicator instead of being clipped by them.
 */
export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  viewportFit: "cover",
  themeColor: "#151412",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html
      lang="en"
      className={`${sans.variable} ${display.variable} ${mono.variable}`}
    >
      <body>
        {/* Wallet state is shared app-wide: the header, the wallet page and
            onboarding must agree on whether a wallet is connected, or one of
            them offers "Connect Wallet" to someone who already connected. */}
        <WalletProvider>
          <Header />
          <main className="main">{children}</main>
          <Footer />
        </WalletProvider>
      </body>
    </html>
  );
}