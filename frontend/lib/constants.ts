/** Platform constants (Spec 01: brand, supported networks). */

export const BRAND_NAME = "bagworkRH";

export const SUPPORTED_NETWORKS = [
  {
    // Robinhood Chain testnet — the launch chain.
    chainId: 46630,
    name: "Robinhood Chain Testnet",
    token: "ETH",
    rpcUrl: "https://rpc.testnet.chain.robinhood.com",
    explorerUrl: "https://explorer.testnet.chain.robinhood.com",
    testnet: true,
  },
  {
    chainId: 4663,
    name: "Robinhood Chain",
    token: "ETH",
    rpcUrl: "https://rpc.mainnet.chain.robinhood.com",
    explorerUrl: "https://robinhoodchain.blockscout.com",
    testnet: false,
  },
  {
    chainId: 11155111,
    name: "Sepolia",
    token: "ETH",
    rpcUrl: "https://rpc.sepolia.org",
    explorerUrl: "https://sepolia.etherscan.io",
    testnet: true,
  },
] as const;

/**
 * The stablecoin brands fund with and creators are paid in.
 *
 * One definition, mirrored from `FUNDING_TOKEN_SYMBOL` in
 * `backend/config/settings/base.py`. Keep the two in step: the backend stamps
 * it on every deposit and every quote, so a mismatch here would show a brand
 * a token the platform does not actually record.
 *
 * USDG is Paxos's Global Dollar, the stablecoin Robinhood Chain documents.
 */
export const FUNDING_TOKEN_SYMBOL = process.env.NEXT_PUBLIC_FUNDING_TOKEN || "USDG";

export const NAV_LINKS = [
  { href: "/", label: "Home" },
  { href: "/campaigns", label: "Campaigns" },
  { href: "/how-it-works", label: "How It Works" },
  { href: "/dashboard", label: "Dashboard" },
  // Brands fund campaigns rather than earn from them, so they get a separate
  // surface. Linking it from the main nav is what makes the platform usable by
  // both sides without conflating a brand's balance with a creator's earnings.
  { href: "/brand", label: "For Brands" },
  { href: "/help", label: "Help" },
] as const;

/**
 * The chain the platform actually pays on: the first entry above, which is
 * Robinhood Chain testnet. Named so a component never has to hardcode an id —
 * the connect button previously compared against Sepolia, which told users on
 * the correct chain that they were on the wrong one.
 */
export const LAUNCH_CHAIN = SUPPORTED_NETWORKS[0];

/**
 * Deep links that open a page inside a mobile wallet's own browser.
 *
 * A phone browser has no injected provider, so `window.ethereum` does not exist
 * there and no amount of retrying will connect. Handing the URL to the wallet
 * opens it in the wallet's built-in browser, which *does* inject a provider —
 * so the same connect flow then works unchanged, extension or not.
 *
 * WalletConnect (Reown) is the alternative for wallets without a dapp browser;
 * it needs a project ID and an extra dependency, so it is deliberately not the
 * first step here.
 */
export function walletDeepLinks(url: string): { name: string; href: string }[] {
  const bare = url.replace(/^https?:\/\//, "");
  return [
    { name: "MetaMask", href: `https://metamask.app.link/dapp/${bare}` },
    {
      name: "Trust Wallet",
      href: `https://link.trustwallet.com/open_url?coin_id=60&url=${encodeURIComponent(url)}`,
    },
    {
      name: "Coinbase Wallet",
      href: `https://go.cb-w.com/dapp?cb_url=${encodeURIComponent(url)}`,
    },
  ];
}

/** Shorten an EVM address for display: 0x1234...ABCD */
export function shortenAddress(address: string, chars = 4): string {
  if (!address) return "";
  if (address.length <= 2 + chars * 2) return address;
  return `${address.slice(0, 2 + chars)}...${address.slice(-chars)}`;
}