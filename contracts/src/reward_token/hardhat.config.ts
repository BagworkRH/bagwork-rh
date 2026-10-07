// Loads `.env` from this directory into process.env at config-evaluation time.
// Must be imported before anything reads an env var below: the `networks`
// object resolves DEPLOYER_PRIVATE_KEY at module scope, so without this the
// key sitting in `.env` is invisible and hardhat reports "No signer available".
// `.env` is gitignored; see `.env.example` for the keys it expects.
import "dotenv/config";

import { HardhatUserConfig } from "hardhat/config";
import "@nomicfoundation/hardhat-toolbox";

const config: HardhatUserConfig = {
  solidity: {
    version: "0.8.24",
    settings: {
      optimizer: { enabled: true, runs: 200 },
    },
  },
  networks: {
    // Robinhood Chain (Arbitrum L2 on Ethereum). This is the chain the
    // platform launches on, so it is the primary deployment target.
    //   testnet: chainId 46630, explorer.testnet.chain.robinhood.com
    //   mainnet: chainId 4663,  robinhoodchain.blockscout.com
    // Public endpoints are rate-limited; use a provider (Alchemy, QuickNode)
    // for production by setting RH_RPC_URL.
    robinhoodTestnet: {
      url:
        process.env.RH_RPC_URL_TESTNET || "https://rpc.testnet.chain.robinhood.com",
      chainId: 46630,
      accounts: process.env.DEPLOYER_PRIVATE_KEY
        ? [process.env.DEPLOYER_PRIVATE_KEY]
        : [],
    },
    robinhood: {
      url: process.env.RH_RPC_URL || "https://rpc.mainnet.chain.robinhood.com",
      chainId: 4663,
      accounts: process.env.DEPLOYER_PRIVATE_KEY
        ? [process.env.DEPLOYER_PRIVATE_KEY]
        : [],
    },
    sepolia: {
      url: process.env.RPC_URL || "https://rpc.sepolia.org",
      chainId: 11155111,
      accounts: process.env.DEPLOYER_PRIVATE_KEY
        ? [process.env.DEPLOYER_PRIVATE_KEY]
        : [],
    },
  },
};

export default config;