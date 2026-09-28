// Phase 6 cross-check generator.
// Emits the values the Python backend (EIP-712 signing + ABI encoding) must
// reproduce, computed with the real ethers stack — the same library the
// contract tests use. Usage: node _crosscheck.js > _crosscheck.json
//
// The domain name below MUST stay in sync with:
//   - backend/apps/blockchain/signing.py  (DOMAIN_NAME)
//   - backend/apps/blockchain/services.py (claim authorization "domain")
//   - contracts/src/reward_token/contracts/RewardDistributor.sol (DOMAIN_SEPARATOR)
const { ethers } = require("ethers");

const DOMAIN_NAME = process.env.DOMAIN_NAME || "bagworkRH";

/** Emit a long hex string as an implicitly-concatenated Python literal. */
function pyHex(value, indent = "        ") {
  const body = value.startsWith("0x") ? value : `0x${value}`;
  const lines = [];
  for (let i = 0; i < body.length; i += 64) {
    lines.push(`${indent}"${body.slice(i, i + 64)}"`);
  }
  return `(\n${lines.join("\n")}\n    )`;
}

const FIXTURE = {
  chainId: 11155111,
  contract: "0x00000000000000000000000000000000000000BB",
  token: "0x00000000000000000000000000000000000000AA",
  wallet: "0x1111111111111111111111111111111111111111",
  rewardId: 1n,
  amount: 5000000000000000000n,
  nonce: 1n,
  deadline: 1893456000n,
};

const SIGNER_KEY = "0x" + "11".repeat(32);
const CLAIM_SIGNATURE =
  "claim(uint256 rewardId,address wallet,uint256 amount,uint256 nonce,uint256 deadline,bytes signature)";

async function main() {
  const iface = new ethers.Interface([`function ${CLAIM_SIGNATURE}`]);

  const domain = {
    name: DOMAIN_NAME,
    version: "1",
    chainId: FIXTURE.chainId,
    verifyingContract: FIXTURE.contract,
  };
  const types = {
    Claim: [
      { name: "wallet", type: "address" },
      { name: "rewardId", type: "uint256" },
      { name: "token", type: "address" },
      { name: "amount", type: "uint256" },
      { name: "nonce", type: "uint256" },
      { name: "deadline", type: "uint256" },
      { name: "chainId", type: "uint256" },
    ],
  };
  const value = {
    wallet: FIXTURE.wallet,
    rewardId: FIXTURE.rewardId,
    token: FIXTURE.token,
    amount: FIXTURE.amount,
    nonce: FIXTURE.nonce,
    deadline: FIXTURE.deadline,
    chainId: FIXTURE.chainId,
  };

  const signer = new ethers.Wallet(SIGNER_KEY);
  const signature = await signer.signTypedData(domain, types, value);
  const calldata = iface.encodeFunctionData("claim", [
    FIXTURE.rewardId,
    FIXTURE.wallet,
    FIXTURE.amount,
    FIXTURE.nonce,
    FIXTURE.deadline,
    signature,
  ]);
  const domainSep = ethers.TypedDataEncoder.hashDomain(domain);
  const structHash = ethers.TypedDataEncoder.hashStruct("Claim", types, value);
  const digest = ethers.TypedDataEncoder.hash(domain, types, value);

  console.log(
    JSON.stringify(
      {
        chain_id: Number(FIXTURE.chainId),
        contract_address: FIXTURE.contract,
        token_address: FIXTURE.token,
        wallet: FIXTURE.wallet,
        reward_id: Number(FIXTURE.rewardId),
        amount_smallest_unit: Number(FIXTURE.amount),
        nonce: Number(FIXTURE.nonce),
        deadline: Number(FIXTURE.deadline),
        selector: iface.getFunction("claim").selector,
        domain_separator: domainSep,
        struct_hash: structHash,
        digest,
        signer_address: signer.address,
        signature,
        calldata,
      },
      null,
      2
    )
  );

  if (process.argv.includes("--python")) {
    // Emit the CROSS_CHECK body for backend/tests/helpers.py verbatim so the
    // long hex values are never re-chunked by hand.
    console.log(
      [
        "    'domain_separator': " + JSON.stringify(domainSep) + ",",
        "    'struct_hash': " + JSON.stringify(structHash) + ",",
        "    'digest': " + JSON.stringify(digest) + ",",
        "    'signer_address': " + JSON.stringify(signer.address) + ",",
        "    'signature': " + pyHex(signature) + ",",
        "    'calldata': " + pyHex(calldata) + ",",
      ].join("\n")
    );
  }
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});