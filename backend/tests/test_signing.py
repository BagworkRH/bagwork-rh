"""EIP-712 signing and ABI encoding tests (Spec 04).

The expected values here were generated with the real JS stack
(`ethers.Interface`, `ethers.TypedDataEncoder`, `Wallet.signTypedData`) in
`contracts/src/reward_token/_crosscheck.js`. Matching them byte-for-byte proves
the Python backend and the Solidity contract agree on the EIP-712 domain, the
Claim struct, and the `claim(...)` calldata layout.
"""
import datetime
from decimal import Decimal

from django.test import SimpleTestCase
from eth_utils import to_checksum_address

from apps.blockchain import abi, signing

from .helpers import CROSS_CHECK


def _digest():
    return signing.build_claim_digest(
        wallet=CROSS_CHECK["wallet"],
        reward_id=CROSS_CHECK["reward_id"],
        token_address=CROSS_CHECK["token_address"],
        amount=CROSS_CHECK["amount_smallest_unit"],
        nonce=CROSS_CHECK["nonce"],
        deadline=CROSS_CHECK["deadline"],
        chain_id=CROSS_CHECK["chain_id"],
        contract_address=CROSS_CHECK["contract_address"],
    )


class DomainAndStructHashTests(SimpleTestCase):
    def test_domain_separator_matches_ethers(self):
        separator = signing.build_domain_separator(
            CROSS_CHECK["chain_id"], CROSS_CHECK["contract_address"]
        )
        self.assertEqual("0x" + separator.hex(), CROSS_CHECK["domain_separator"])

    def test_struct_hash_matches_ethers(self):
        struct_hash = signing.build_claim_struct_hash(
            wallet=CROSS_CHECK["wallet"],
            reward_id=CROSS_CHECK["reward_id"],
            token_address=CROSS_CHECK["token_address"],
            amount=CROSS_CHECK["amount_smallest_unit"],
            nonce=CROSS_CHECK["nonce"],
            deadline=CROSS_CHECK["deadline"],
            chain_id=CROSS_CHECK["chain_id"],
        )
        self.assertEqual("0x" + struct_hash.hex(), CROSS_CHECK["struct_hash"])

    def test_claim_digest_matches_ethers(self):
        self.assertEqual("0x" + _digest().hex(), CROSS_CHECK["digest"])

    def test_domain_separator_changes_per_chain_and_contract(self):
        base = signing.build_domain_separator(
            CROSS_CHECK["chain_id"], CROSS_CHECK["contract_address"]
        )
        other_chain = signing.build_domain_separator(
            CROSS_CHECK["chain_id"] + 1, CROSS_CHECK["contract_address"]
        )
        other_contract = signing.build_domain_separator(
            CROSS_CHECK["chain_id"], CROSS_CHECK["token_address"]
        )
        self.assertNotEqual(base, other_chain)
        self.assertNotEqual(base, other_contract)


class SignatureTests(SimpleTestCase):
    def test_signature_matches_ethers_and_recovers_signer(self):
        signature = signing.sign_claim_digest(_digest(), "0x" + "11" * 32)
        self.assertEqual(signature, CROSS_CHECK["signature"])

        recovered = signing.recover_claim_signer(_digest(), signature)
        self.assertEqual(
            to_checksum_address(recovered),
            to_checksum_address(CROSS_CHECK["signer_address"]),
        )
        self.assertTrue(
            signing.verify_claim_signature(
                _digest(), signature, CROSS_CHECK["signer_address"]
            )
        )

    def test_verify_rejects_wrong_signer(self):
        signature = signing.sign_claim_digest(_digest(), "0x" + "22" * 32)
        self.assertFalse(
            signing.verify_claim_signature(
                _digest(), signature, CROSS_CHECK["signer_address"]
            )
        )

    def test_verify_rejects_malformed_signature(self):
        self.assertFalse(
            signing.verify_claim_signature(
                _digest(), "0xdeadbeef", CROSS_CHECK["signer_address"]
            )
        )
class CalldataTests(SimpleTestCase):
    def test_selector_matches_ethers(self):
        self.assertEqual("0x" + abi.CLAIM_SELECTOR.hex(), CROSS_CHECK["selector"])

    def test_encode_claim_calldata_matches_ethers(self):
        calldata = abi.encode_claim_calldata(
            reward_id=CROSS_CHECK["reward_id"],
            wallet=CROSS_CHECK["wallet"],
            amount=CROSS_CHECK["amount_smallest_unit"],
            nonce=CROSS_CHECK["nonce"],
            deadline=CROSS_CHECK["deadline"],
            signature=CROSS_CHECK["signature"],
        )
        self.assertEqual(calldata, CROSS_CHECK["calldata"])

    def test_decode_claim_calldata_round_trip(self):
        decoded = abi.decode_claim_calldata(CROSS_CHECK["calldata"])
        self.assertEqual(decoded["reward_id"], CROSS_CHECK["reward_id"])
        self.assertEqual(decoded["wallet"], to_checksum_address(CROSS_CHECK["wallet"]))
        self.assertEqual(decoded["amount"], CROSS_CHECK["amount_smallest_unit"])
        self.assertEqual(decoded["nonce"], CROSS_CHECK["nonce"])
        self.assertEqual(decoded["deadline"], CROSS_CHECK["deadline"])
        self.assertEqual(decoded["signature"], CROSS_CHECK["signature"][2:].lower())

    def test_decode_rejects_other_calldata(self):
        with self.assertRaises(ValueError):
            abi.decode_claim_calldata("0xdeadbeef" + "00" * 32)


class AmountConversionTests(SimpleTestCase):
    def test_reward_amount_smallest_units(self):
        self.assertEqual(
            signing.reward_amount_smallest(Decimal("5"), 18), 5_000_000_000_000_000_000
        )
        self.assertEqual(signing.reward_amount_smallest(Decimal("1.5"), 6), 1_500_000)
        self.assertEqual(signing.reward_amount_smallest(Decimal("0"), 18), 0)

    def test_claim_deadline_is_utc_epoch_seconds(self):
        aware = datetime.datetime(2030, 1, 1, tzinfo=datetime.timezone.utc)
        self.assertEqual(signing.claim_deadline(aware), CROSS_CHECK["deadline"])
