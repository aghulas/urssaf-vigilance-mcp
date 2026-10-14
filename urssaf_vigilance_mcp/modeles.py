"""Modèles de données normalisés (indépendants du format brut de l'API)."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date

NATURES = {
    "AVG_UR": "Attestation de vigilance Urssaf",
    "AVG_RSI": "Attestation de vigilance ISU (artisans / commerçants)",
    "CSG_UR": "Attestation de part déductible CSG/CRDS Urssaf",
    "CSG_RSI": "Attestation de part déductible CSG/CRDS ISU",
    "CFP_UR": "Attestation de contribution à la formation professionnelle Urssaf",
    "CFP_RSI": "Attestation de contribution à la formation professionnelle ISU",
    "EPM_UR": "Attestation employeur de personnel de maison",
    "FRS_UR": "Attestation de frontalier suisse",
    "CAA_UR": "Attestation annuelle de chiffre d'affaires (micro-entrepreneur) Urssaf",
    "CAA_RSI": "Attestation annuelle de chiffre d'affaires (micro-entrepreneur) ISU",
    "CAP_UR": "Attestation périodique de chiffre d'affaires (micro-entrepreneur) Urssaf",
    "CAP_RSI": "Attestation périodique de chiffre d'affaires (micro-entrepreneur) ISU",
    "ASAA_UR": "Attestation AGESSA (artistes-auteurs)",
}
NATURES_VIGILANCE = {"AVG_UR", "AVG_RSI"}

# Statuts normalisés renvoyés par le connecteur
VALIDE = "valide"
PERIMEE = "perimee"
INCONNUE = "inconnue"
INCOMPLETE = "incomplete"  # FUNC203 donnée de sécurisation manquante
ERREUR = "erreur"


@dataclass
class Etablissement:
    siret: str
    adresse: str

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ResultatVerification:
    """Résultat normalisé de la vérification d'un code de sécurité."""

    code_securite: str
    statut: str  # VALIDE | PERIMEE | INCONNUE | INCOMPLETE | ERREUR
    message: str = ""
    nature: str | None = None
    nature_libelle: str | None = None
    est_attestation_vigilance: bool = False
    denomination: str | None = None
    organisme_emetteur: str | None = None
    date_certification: str | None = None  # JJ/MM/AAAA tel que renvoyé
    siren: str | None = None
    etablissements: list[Etablissement] = field(default_factory=list)
    derniere_periode_analysee: str | None = None
    masse_salariale: str | None = None
    effectif: str | None = None
    perimee_depuis: str | None = None  # JJ/MM/AAAA (FUNC201)
    fault_code: str | None = None
    brut: dict | None = None

    @property
    def sirets(self) -> list[str]:
        return [e.siret for e in self.etablissements]

    def to_dict(self, inclure_brut: bool = False) -> dict:
        d = asdict(self)
        d["sirets"] = self.sirets
        if not inclure_brut:
            d.pop("brut", None)
        return d


@dataclass
class AttestationPdf:
    """Données extraites du PDF d'une attestation de vigilance Urssaf."""

    fichier: str
    code_securite: str | None = None
    siren: str | None = None
    raison_sociale: str | None = None
    organisme_emetteur: str | None = None
    date_delivrance: date | None = None
    a_jour_au: date | None = None  # date de fin de période analysée
    mois_analyse: str | None = None  # ex. "août 2026"
    effectif: int | None = None
    masse_salariale: int | None = None
    sirets: list[str] = field(default_factory=list)
    texte: str = ""

    def to_dict(self) -> dict:
        d = asdict(self)
        d["date_delivrance"] = self.date_delivrance.isoformat() if self.date_delivrance else None
        d["a_jour_au"] = self.a_jour_au.isoformat() if self.a_jour_au else None
        d.pop("texte", None)
        return d
