"""Configuration lue dans l'environnement (jamais de secret dans le dépôt)."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

HOTE_PRODUCTION = "api.urssaf.fr"
HOTE_SANDBOX = "api-edi.urssaf.fr"
SCOPE = "attn.codes_securite"
CHEMIN_TOKEN = "/api/oauth/v1/token"
CHEMIN_VERIFIER = "/attn/verification/v1/codes_securite/verifier"


@dataclass
class Settings:
    client_id: str = ""
    client_secret: str = ""
    environnement: str = "sandbox"  # "sandbox" | "production"
    mock: bool = False
    domaine_defaut: str = "URSSAF"  # "URSSAF" | "ISU"
    fichier_suivi: Path | None = None
    timeout: float = 30.0
    hote: str = field(init=False)

    def __post_init__(self) -> None:
        env = (self.environnement or "sandbox").lower()
        if env not in ("sandbox", "production"):
            raise ValueError(f"URSSAF_ENV invalide : {self.environnement!r} (sandbox|production)")
        self.environnement = env
        self.hote = HOTE_PRODUCTION if env == "production" else HOTE_SANDBOX

    @property
    def url_token(self) -> str:
        return f"https://{self.hote}{CHEMIN_TOKEN}"

    @property
    def url_verifier(self) -> str:
        return f"https://{self.hote}{CHEMIN_VERIFIER}"

    @classmethod
    def depuis_env(cls) -> "Settings":
        suivi = os.environ.get("URSSAF_FICHIER_SUIVI")
        return cls(
            client_id=os.environ.get("URSSAF_CLIENT_ID", ""),
            client_secret=os.environ.get("URSSAF_CLIENT_SECRET", ""),
            environnement=os.environ.get("URSSAF_ENV", "sandbox"),
            mock=os.environ.get("URSSAF_MOCK", "").strip() in ("1", "true", "oui"),
            domaine_defaut=os.environ.get("URSSAF_DOMAINE", "URSSAF").upper(),
            fichier_suivi=Path(suivi).expanduser() if suivi else None,
            timeout=float(os.environ.get("URSSAF_TIMEOUT", "30")),
        )
