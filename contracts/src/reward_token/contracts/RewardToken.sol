// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "@openzeppelin/contracts/token/ERC20/ERC20.sol";
import "@openzeppelin/contracts/access/Ownable.sol";

/**
 * @title RewardToken
 * @notice Capped ERC-20 used for testnet deployment and integration testing.
 *
 * @dev PRODUCTION: this contract is NOT the production token. The production
 * token is launched on pons, which mints a fixed supply of 1,000,000,000
 * tokens at deployment with no further minting. MAX_SUPPLY below matches that
 * figure so a pons token is a drop-in replacement and the test token cannot
 * model economics the real token cannot reproduce.
 *
 * The cap exists because the earlier owner-mintable, uncapped version made
 * supply unbounded: a compromised deployer key could print tokens at will,
 * which contradicts every deflationary/supply argument made about the token.
 *
 * `burn` is provided so a future fee-burn can be introduced without another
 * token deployment. It is deliberately NOT called by the reward claim path:
 * creators are paid in fiat and no burn takes effect until treasury is funded
 * (see RewardDistributor).
 */
contract RewardToken is ERC20, Ownable {
    /// @notice Hard supply ceiling: 1 billion, 18 decimals — pons' fixed launch
    /// supply. Reached by a testnet deployment only if every token is minted.
    uint256 public constant MAX_SUPPLY = 1_000_000_000 * (10 ** 18);

    error CapExceeded(uint256 requested, uint256 cap);

    constructor() ERC20("Reward Token", "RWD") Ownable(msg.sender) {}

    /**
     * @notice Mint tokens, up to the hard cap. Owner only.
     * @dev Reverts rather than silently minting a partial amount, so a caller
     * never has to reason about what it actually received.
     */
    function mint(address to, uint256 amount) external onlyOwner {
        uint256 newSupply = totalSupply() + amount;
        if (newSupply > MAX_SUPPLY) revert CapExceeded(newSupply, MAX_SUPPLY);
        _mint(to, amount);
    }

    /// @notice Burn the caller's own tokens. Never used by the claim path today.
    function burn(uint256 amount) external {
        _burn(msg.sender, amount);
    }

    /// @notice Burn tokens from an approved allowance. Never used by the claim path.
    function burnFrom(address account, uint256 amount) external {
        _spendAllowance(account, msg.sender, amount);
        _burn(account, amount);
    }

    function decimals() public pure override returns (uint8) {
        return 18;
    }
}