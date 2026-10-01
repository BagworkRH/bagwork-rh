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

/** Shorten an EVM address for display: 0x1234...ABCD */
export function shortenAddress(address: string, chars = 4): string {
  if (!address) return "";
  if (address.length <= 2 + chars * 2) return address;
  return `${address.slice(0, 2 + chars)}...${address.slice(-chars)}`;
}