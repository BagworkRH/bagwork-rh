"""Platform test package.

`config.settings.base` loads `backend/.env`, so a developer's locally configured
chain would otherwise leak into the suite: paths that must report "disabled"
would suddenly reach a real node, and claims that must rest at CREATED would move
to SIGNING once a signer key is present. The suite's baseline is "no chain
configured"; tests that need one opt in explicitly with `signer_settings()` or
`chain_settings()`. Clearing the ambient values here keeps a local .env from
changing what the tests mean, without touching how they are run.
"""
from django.conf import settings

for _name in ("RPC_URL", "CONTRACT_ADDRESS", "CLAIM_SIGNER", "CLAIM_SIGNER_ADDRESS"):
    setattr(settings, _name, "")

