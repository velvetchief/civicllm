"""Tenant profiles make the engine repurposable.

A tenant is any institution with a governed corpus: a city (land development code),
a university (student policies), a hospital (care/administrative policies). Everything
institution-specific — corpus sources, citation formats, personas, disclaimers — lives
in the tenant YAML, never in code.
"""

from dataclasses import dataclass, field
from pathlib import Path

import yaml

TENANTS_DIR = Path(__file__).parent / "tenants"


@dataclass
class Mode:
    """A presentation mode, e.g. internal staff vs. public resident."""

    persona: str
    disclaimer: str = ""
    disclaimer_es: str = ""

    def disclaimer_for(self, language: str) -> str:
        return self.disclaimer_es or self.disclaimer if language == "es" else self.disclaimer


@dataclass
class Channel:
    """A real-world handoff channel — refusals route here instead of dead-ending."""

    label: str
    detail: str
    url: str | None = None
    label_es: str = ""
    detail_es: str = ""


@dataclass
class TenantProfile:
    id: str
    display_name: str
    corpus_name: str  # e.g. "Austin Land Development Code (Title 25)"
    citation_noun: str  # e.g. "section" / "policy" / "article"
    source_link_label: str  # e.g. "View on Municode"
    modes: dict[str, Mode] = field(default_factory=dict)
    example_questions: list[str] = field(default_factory=list)
    example_questions_es: list[str] = field(default_factory=list)
    scope_statement: str = ""  # HAX G1/G2: what the system can and cannot do
    scope_statement_es: str = ""
    channels: list[Channel] = field(default_factory=list)
    ingest: dict = field(default_factory=dict)  # source-specific ingestion config

    @property
    def languages(self) -> list[str]:
        has_es = bool(self.scope_statement_es or self.example_questions_es)
        return ["en", "es"] if has_es else ["en"]


def load_tenant(tenant_id: str) -> TenantProfile:
    path = TENANTS_DIR / f"{tenant_id}.yaml"
    if not path.exists():
        raise KeyError(f"Unknown tenant: {tenant_id}")
    raw = yaml.safe_load(path.read_text())
    modes = {k: Mode(**v) for k, v in raw.pop("modes", {}).items()}
    channels = [Channel(**c) for c in raw.pop("channels", [])]
    return TenantProfile(id=tenant_id, modes=modes, channels=channels, **raw)


def list_tenants() -> list[str]:
    return sorted(p.stem for p in TENANTS_DIR.glob("*.yaml"))
