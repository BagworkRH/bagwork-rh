"""Domain exceptions for the reward engine."""


class RewardEngineError(Exception):
    """Raised when a reward cannot be calculated, approved, or reversed.

    The message is safe to surface to API consumers.
    """