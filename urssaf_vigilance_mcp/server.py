"""Serveur MCP « urssaf-vigilance » : vérification des attestations de vigilance Urssaf.

Outils :
- verifier_attestation(code, domaine)            : un code de sécurité → résultat Urssaf normalisé
- verifier_attestations(codes)                   : jusqu'à 100 codes par appel API
- lire_attestation_pdf(fichier)                  : données du PDF (code, SIREN, SIRET, période, effectif…)
- controler_attestation(fichier, siret_attendu…) : PDF + API + cohérence + fin de validité
- suivi_lister(fichier)                          : lignes du tableau Excel de suivi
- suivi_creer_modele(fichier)                    : classeur de suivi vierge
- suivi_verifier(fichier, tous, ecrire)          : vérifie les codes du tableau et (option) écrit les résultats

Variables d'environnement : URSSAF_CLIENT_ID, URSSAF_CLIENT_SECRET, URSSAF_ENV (sandbox|production),
URSSAF_MOCK=1 (simulation sans réseau), URSSAF_DOMAINE (URSSAF|ISU), URSSAF_FICHIER_SUIVI (xlsx par défaut),
URSSAF_FEUILLE_SUIVI (nom de la feuille, sinon détection automatique),
URSSAF_ECRITURE=1 (autorise la mise à jour du fichier Excel).
"""

from __future__ import annotations

import os
from datetime import date
from pathlib import Path
from typing import Any

try:  # mcp >= 2
    from mcp.server.mcpserver import MCPServer as _Server
except ImportError:  # mcp 1.x
    from mcp.server.fastmcp import FastMCP as _Server

from . import __version__
from .client import ClientAVCS, UrssafApiError, normaliser_code
from .config import Settings
from .controle import controler
from .modeles import VALIDE
from .pdf import lire_attestation
from .suivi import Suivi, creer_modele, texte_resultat

mcp = _Server(
    "urssaf-vigilance",
    instructions=(
        "Vérifie l'authenticité et la validité des attestations de vigilance Urssaf à partir de leur code de "
        "sécurité (API Urssaf AVCS), contrôle la cohérence avec le PDF reçu et tient le tableau Excel de suivi. "
        "Un code valide prouve que le document existe chez l'Urssaf ; il faut aussi vérifier que le SIRET est "
        "celui du cocontractant et que la période analysée date de moins de 6 mois."
    ),
)

_settings: Settings | None = None
_client: ClientAVCS | None = None


def settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings.depuis_env()
    return _settings


def client() -> ClientAVCS:
    global _client
    if _client is None:
        _client = ClientAVCS(settings())
    return _client


def _ecriture_autorisee() -> bool:
    return os.environ.get("URSSAF_ECRITURE", "").strip() in ("1", "true", "oui")


def _fichier_suivi(fichier: str | None) -> Path:
    p = Path(fichier).expanduser() if fichier else settings().fichier_suivi
    if not p:
        raise ValueError("Aucun fichier de suivi : passer `fichier` ou définir URSSAF_FICHIER_SUIVI")
    if not p.exists():
        raise FileNotFoundError(f"Fichier de suivi introuvable : {p}")
    return p


def _erreur(e: Exception) -> dict[str, Any]:
    d: dict[str, Any] = {"erreur": type(e).__name__, "message": str(e)}
    if isinstance(e, UrssafApiError):
        d["http_status"] = e.status
        d["detail"] = e.detail
    return d


@mcp.tool()
async def verifier_attestation(code: str, domaine: str | None = None) -> dict:
    """Vérifie un code de sécurité (15 caractères) auprès de l'Urssaf.

    Renvoie le statut normalisé : valide | perimee (avec perimee_depuis) | inconnue (fraude possible) |
    incomplete | erreur, et pour une attestation valide : nature, dénomination, organisme, date de
    certification, SIREN, SIRET des établissements, dernière période analysée, effectif, masse salariale.
    `domaine` : URSSAF (défaut, employeurs) ou ISU (artisans / commerçants / indépendants).
    """
    try:
        res = await client().verifier(code, domaine)
        return res.to_dict()
    except Exception as e:  # noqa: BLE001
        return _erreur(e)


@mcp.tool()
async def verifier_attestations(codes: list[str]) -> dict:
    """Vérifie plusieurs codes de sécurité (lots de 100 par appel API). Renvoie un résultat par code."""
    try:
        resultats = await client().verifier_lot(codes)
        return {
            "nombre": len(resultats),
            "valides": sum(r.statut == VALIDE for r in resultats),
            "resultats": [r.to_dict() for r in resultats],
        }
    except Exception as e:  # noqa: BLE001
        return _erreur(e)


@mcp.tool()
def lire_attestation_pdf(fichier: str) -> dict:
    """Extrait les données d'un PDF d'attestation de vigilance Urssaf (sans appel réseau).

    Renvoie code de sécurité, SIREN, raison sociale, organisme émetteur, date de délivrance,
    date « à jour au » (fin de période analysée), effectif, masse salariale, SIRET des établissements.
    """
    try:
        p = Path(fichier).expanduser()
        if not p.exists():
            raise FileNotFoundError(f"PDF introuvable : {p}")
        att = lire_attestation(p)
        d = att.to_dict()
        if not att.code_securite:
            d["avertissement"] = "Code de sécurité introuvable dans le texte du PDF : document scanné ou non Urssaf ? Demander le PDF original téléchargé depuis urssaf.fr."
        return d
    except Exception as e:  # noqa: BLE001
        return _erreur(e)


@mcp.tool()
async def controler_attestation(
    fichier: str,
    siret_attendu: str | None = None,
    siren_attendu: str | None = None,
    domaine: str | None = None,
) -> dict:
    """Contrôle complet d'une attestation reçue : lecture du PDF, vérification du code auprès de l'Urssaf,
    cohérence champ à champ (SIREN, SIRET, période, effectif, masse salariale), cocontractant attendu
    (siret_attendu / siren_attendu) et fin de validité (6 mois après la période analysée, fin de mois).

    Renvoie verdict OK | ALERTE (échéance < 30 j ou écarts mineurs) | REFUS (code inconnu, périmée, SIRET absent…).
    """
    try:
        p = Path(fichier).expanduser()
        att = lire_attestation(p)
        if not att.code_securite:
            return {"verdict": "REFUS", "anomalies": ["Code de sécurité introuvable dans le PDF"], "pdf": att.to_dict()}
        res = await client().verifier(att.code_securite, domaine)
        ctl = controler(att, res, siret_attendu=siret_attendu, siren_attendu=siren_attendu)
        return {"controle": ctl.to_dict(), "pdf": att.to_dict(), "urssaf": res.to_dict(), "texte_suivi": texte_resultat(res, ctl)}
    except Exception as e:  # noqa: BLE001
        return _erreur(e)


@mcp.tool()
def suivi_lister(fichier: str | None = None, seulement_a_verifier: bool = False) -> dict:
    """Lit le tableau Excel « Suivi des attestations par entreprise » : une entrée par ligne (opération, lot,
    entreprise, date d'attestation, échéance, statut, code de sécurité, texte de vérification) et la liste des
    codes uniques. `seulement_a_verifier` ne garde que les codes dont la vérification n'est pas tracée.
    """
    try:
        s = Suivi(_fichier_suivi(fichier), settings().feuille_suivi)
        lignes = s.lignes()
        if seulement_a_verifier:
            lignes = [l for l in lignes if l.code_a_verifier]
        codes = s.codes_uniques(seulement_a_verifier=seulement_a_verifier)
        aujourdhui = date.today()
        perimees = [l.to_dict() for l in s.lignes() if l.echeance and l.echeance < aujourdhui]
        return {
            "fichier": str(s.fichier),
            "colonnes": s.colonnes,
            "lignes": [l.to_dict() for l in lignes],
            "codes_uniques": {c: [l.entreprise for l in ls] for c, ls in codes.items()},
            "perimees_au_tableau": perimees,
        }
    except Exception as e:  # noqa: BLE001
        return _erreur(e)


@mcp.tool()
async def suivi_verifier(fichier: str | None = None, tous: bool = False, ecrire: bool = False) -> dict:
    """Vérifie auprès de l'Urssaf les codes du tableau de suivi (par défaut seulement ceux non encore
    vérifiés ; `tous=True` pour re-contrôler l'ensemble, utile pour la revue mensuelle) et, si `ecrire=True`
    et URSSAF_ECRITURE=1, écrit le résultat dans la colonne « Vérification » de chaque ligne concernée
    (et l'échéance si périmée). Sans `ecrire`, aucune modification du fichier : simulation.
    """
    try:
        p = _fichier_suivi(fichier)
        s = Suivi(p, settings().feuille_suivi)
        par_code = s.codes_uniques(seulement_a_verifier=not tous)
        if not par_code:
            return {"fichier": str(p), "message": "Aucun code à vérifier", "resultats": []}
        resultats = await client().verifier_lot(list(par_code))
        aujourdhui = date.today()
        sortie = []
        for res in resultats:
            lignes = par_code.get(res.code_securite, [])
            txt = texte_resultat(res, aujourdhui=aujourdhui)
            entree = {
                "code": res.code_securite,
                "entreprises": sorted({l.entreprise for l in lignes}),
                "lignes": [l.ligne for l in lignes],
                "statut": res.statut,
                "sirets": res.sirets,
                "derniere_periode_analysee": res.derniere_periode_analysee,
                "perimee_depuis": res.perimee_depuis,
                "texte_suivi": txt,
            }
            if ecrire:
                if not _ecriture_autorisee():
                    entree["ecriture"] = "refusée : URSSAF_ECRITURE=1 requis"
                else:
                    for l in lignes:
                        s.ecrire_verification(l.ligne, txt)
                    entree["ecriture"] = "faite"
            sortie.append(entree)
        resume = {"fichier": str(p), "verifies": len(resultats), "valides": sum(r.statut == VALIDE for r in resultats), "resultats": sortie}
        if ecrire and _ecriture_autorisee():
            s.enregistrer()
            resume["fichier_enregistre"] = True
        return resume
    except Exception as e:  # noqa: BLE001
        return _erreur(e)


@mcp.tool()
def suivi_creer_modele(fichier: str) -> dict:
    """Crée un classeur Excel de suivi vierge (colonnes Opération, Lot, Entreprise, SIRET attendu, dates,
    statut, contact, code de sécurité, vérification) à l'emplacement indiqué. Refuse d'écraser un fichier existant.
    """
    try:
        return {"fichier": str(creer_modele(Path(fichier).expanduser()))}
    except Exception as e:  # noqa: BLE001
        return _erreur(e)


@mcp.tool()
def etat_connecteur() -> dict:
    """Configuration courante (sans secrets) : environnement, mode mock, fichier de suivi, écriture, version."""
    st = settings()
    return {
        "version": __version__,
        "environnement": st.environnement,
        "hote": st.hote,
        "mock": st.mock,
        "identifiants_presents": bool(st.client_id and st.client_secret),
        "domaine_defaut": st.domaine_defaut,
        "fichier_suivi": str(st.fichier_suivi) if st.fichier_suivi else None,
        "feuille_suivi": st.feuille_suivi,
        "ecriture_excel": _ecriture_autorisee(),
    }


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
