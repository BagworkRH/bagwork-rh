import type { Metadata } from "next";
import "./globals.css";
import Header from "@/components/Header";
import Footer from "@/components/Footer";

export const metadata: Metadata = {
  title: "bagworkRH — Earn crypto for verified social promotion",
  description:
    "Connect your X account and EVM wallet, join campaigns, publish qualifying posts, and earn crypto rewards.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <Header />
        <main className="main">{children}</main>
        <Footer />
      </body>
    </html>
  );
}