/** Platform constants (Spec 01: brand, supported networks). */

export const BRAND_NAME = "bagworkRH";

export const SUPPORTED_NETWORKS = [
  {
    chainId: 11155111,
    name: "Sepolia",
    token: "ETH",
    rpcUrl: "https://rpc.sepolia.org",
    testnet: true,
  },
  {
    chainId: 1,
    name: "Ethereum",
    token: "ETH",
    rpcUrl: "https://eth.llamarpc.com",
    testnet: false,
  },
] as const;

export const NAV_LINKS = [
  { href: "/", label: "Home" },
  { href: "/campaigns", label: "Campaigns" },
  { href: "/how-it-works", label: "How It Works" },
  { href: "/dashboard", label: "Dashboard" },
  { href: "/help", label: "Help" },
] as const;

/** Shorten an EVM address for display: 0x1234...ABCD */
export function shortenAddress(address: string, chars = 4): string {
  if (!address) return "";
  if (address.length <= 2 + chars * 2) return address;
  return `${address.slice(0, 2 + chars)}...${address.slice(-chars)}`;
}