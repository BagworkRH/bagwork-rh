import type { Metadata } from "next";
import "./globals.css";
import Header from "@/components/Header";
import Footer from "@/components/Footer";
import { WalletProvider } from "@/hooks/useWallet";

export const metadata: Metadata = {
  title: "bagworkRH — Get paid for the posts you make",
  description:
    "Post for a campaign, earn verified token rewards, claim on-chain. Connect your social accounts and wallet to get paid.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
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