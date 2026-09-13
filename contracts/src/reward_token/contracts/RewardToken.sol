// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "@openzeppelin/contracts/token/ERC20/ERC20.sol";
import "@openzeppelin/contracts/access/Ownable.sol";

/// @notice DEVELOPMENT TEST TOKEN — mintable by the owner. Never use in
/// production; replace with a real/wrapped token per campaign specification.
contract RewardToken is ERC20, Ownable {
    constructor() ERC20("Reward Token", "RWD") Ownable(msg.sender) {}

    function mint(address to, uint256 amount) external onlyOwner {
        _mint(to, amount);
    }

    function decimals() public pure override returns (uint8) {
        return 18;
    }
}