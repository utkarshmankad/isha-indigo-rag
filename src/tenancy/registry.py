"""Tenant registry and API-key auth (S4-T1/T3).

Each supported airline is a tenant with its own API key. This is the
lightweight stand-in for full SSO called out in the Sprint 3 roadmap
("start with simple JWT/OAuth, defer full SAML") — a tenant's staff must
present their airline's key before the pipeline is scoped to their data.

Keys come from env vars (`TENANT_APIKEY_<AIRLINE>`, e.g.
`TENANT_APIKEY_INDIGO`). If unset, an ephemeral key is generated at process
start and logged once — safe for local demo, unusable across restarts, and
loud about it so it's never mistaken for a real deployment config.
"""
import os
import secrets
from dataclasses import dataclass

from src.observability.logging_config import get_logger

logger = get_logger("tenancy.registry")

KNOWN_AIRLINES: dict[str, str] = {
    "indigo": "IndiGo (6E)",
    "air_india": "Air India (AI)",
    "spicejet": "SpiceJet (SG)",
}


@dataclass(frozen=True)
class TenantConfig:
    tenant_id: str
    airline: str
    display_name: str
    api_key: str


def _load_registry() -> dict[str, TenantConfig]:
    registry: dict[str, TenantConfig] = {}
    for airline, display_name in KNOWN_AIRLINES.items():
        env_key = f"TENANT_APIKEY_{airline.upper()}"
        api_key = os.environ.get(env_key)
        if not api_key:
            api_key = secrets.token_urlsafe(16)
            logger.warning(
                "tenant API key not configured, generated ephemeral dev key",
                airline=airline, env_var=env_key,
            )
        registry[airline] = TenantConfig(
            tenant_id=airline, airline=airline, display_name=display_name, api_key=api_key,
        )
    return registry


TENANTS: dict[str, TenantConfig] = _load_registry()


def authenticate(airline: str, api_key: str) -> TenantConfig | None:
    """Constant-time key check, scoped to a single tenant's airline."""
    tenant = TENANTS.get(airline)
    if tenant is None or not api_key:
        return None
    if secrets.compare_digest(tenant.api_key, api_key):
        return tenant
    return None
