"""Extraction des données d'une attestation de vigilance Urssaf (PDF texte natif).

Les attestations Urssaf sont des PDF générés (pas des scans) : l'extraction est déterministe.
Si le texte est vide (scan), `AttestationPdf.code_securite` reste None et l'appelant doit
demander le PDF original téléchargé depuis urssaf.fr.
"""

from __future__ import annotations

import calendar
import re
from datetime import date
from pathlib import Path

from pypdf import PdfReader

from .modeles import AttestationPdf

MOIS = {
    "janvier": 1, "fevrier": 2, "février": 2, "mars": 3, "avril": 4, "mai": 5, "juin": 6,
    "juillet": 7, "aout": 8, "août": 8, "septembre": 9, "octobre": 10, "novembre": 11,
    "decembre": 12, "décembre": 12,
}

RE_CODE = re.compile(r"CODE DE S[ÉE]CURIT[ÉE]\s*\n\s*([A-Z0-9]{15})\b")
RE_SIREN = re.compile(r"N°\s*SIREN\s*(\d{3}\s?\d{3}\s?\d{3})")
RE_EFFECTIF = re.compile(r"effectif moyen mensuel de\s*(\d[\d\s]*)\s*salari", re.I)
RE_MASSE = re.compile(r"masse salariale de\s*(\d[\d\s]*)\s*euros", re.I)
RE_MOIS = re.compile(r"au titre du mois de\s+([a-zéû]+\s+\d{4})", re.I)
RE_A_JOUR = re.compile(r"à la date du\s+(\d{2}/\d{2}/\d{4})")
RE_FAIT_LE = re.compile(r"le\s*:\s*(\d{2}/\d{2}/\d{4})")
RE_DATE_LETTRE = re.compile(r",\s*le\s+(\d{1,2})(?:er)?\s+([A-Za-zéû]+)\s+(\d{4})")
RE_SIRET = re.compile(r"\b(\d{3}\s?\d{3}\s?\d{3}\s?\d{5})\b")
RE_ORGANISME = re.compile(r"^(URSSAF [A-ZÉÈ' \-]+?)\s*$", re.M)


def _date_fr(s: str) -> date | None:
    try:
        j, m, a = s.split("/")
        return date(int(a), int(m), int(j))
    except Exception:  # noqa: BLE001
        return None


def _entier(s: str) -> int | None:
    try:
        return int(re.sub(r"\s+", "", s))
    except Exception:  # noqa: BLE001
        return None


def extraire_texte(fichier: str | Path) -> str:
    reader = PdfReader(str(fichier))
    return "\n".join((p.extract_text() or "") for p in reader.pages)


def lire_attestation(fichier: str | Path) -> AttestationPdf:
    fichier = Path(fichier)
    texte = extraire_texte(fichier)
    att = AttestationPdf(fichier=str(fichier), texte=texte)

    if m := RE_CODE.search(texte):
        att.code_securite = m.group(1)
    if m := RE_SIREN.search(texte):
        att.siren = re.sub(r"\s+", "", m.group(1))
    if m := RE_ORGANISME.search(texte):
        att.organisme_emetteur = m.group(1).strip()
    if m := RE_EFFECTIF.search(texte):
        att.effectif = _entier(m.group(1))
    if m := RE_MASSE.search(texte):
        att.masse_salariale = _entier(m.group(1))
    if m := RE_MOIS.search(texte):
        att.mois_analyse = m.group(1).strip().lower()
    if m := RE_A_JOUR.search(texte):
        att.a_jour_au = _date_fr(m.group(1))
    elif att.mois_analyse:
        att.a_jour_au = fin_de_mois_depuis_libelle(att.mois_analyse)
    if m := RE_FAIT_LE.search(texte):
        att.date_delivrance = _date_fr(m.group(1))
    elif m := RE_DATE_LETTRE.search(texte):
        mois = MOIS.get(m.group(2).lower())
        if mois:
            att.date_delivrance = date(int(m.group(3)), mois, int(m.group(1)))

    # Raison sociale : première ligne après le bloc d'en-tête, juste avant l'adresse (page 1).
    # Heuristique : ligne en majuscules commençant par une forme juridique ou suivant "Page 1/2".
    att.raison_sociale = _raison_sociale(texte)

    # SIRET des établissements concernés : après "NUMÉRO SIRET", ou tout SIRET du SIREN.
    bloc = texte.split("NUMÉRO SIRET", 1)[1] if "NUMÉRO SIRET" in texte else texte
    sirets = [re.sub(r"\s+", "", s) for s in RE_SIRET.findall(bloc)]
    if att.siren:
        sirets = [s for s in sirets if s.startswith(att.siren)]
    att.sirets = list(dict.fromkeys(sirets))
    return att


def _raison_sociale(texte: str) -> str | None:
    lignes = [l.strip() for l in texte.splitlines()]
    for i, l in enumerate(lignes):
        if l.startswith("Page 1/"):
            # saute la ligne de date ("MONTREUIL, le 5 Octobre 2026") puis prend la 1re ligne en majuscules
            for cand in lignes[i + 1 : i + 5]:
                if cand and ", le " not in cand and cand == cand.upper() and not cand.startswith("OBJET"):
                    return cand
    m = re.search(r"^((?:SAS|SASU|SARL|EURL|SA|SCI|SNC|SCOP|EI|ASSOCIATION|SELARL)\s+[A-Z0-9'&\- ]+)$", texte, re.M)
    return m.group(1).strip() if m else None


def fin_de_mois_depuis_libelle(libelle: str) -> date | None:
    """'août 2026' → 31/08/2026."""
    try:
        mois_txt, annee = libelle.split()
        mois = MOIS[mois_txt.lower()]
        return fin_de_mois(date(int(annee), mois, 1))
    except Exception:  # noqa: BLE001
        return None


def fin_de_mois(d: date) -> date:
    """Dernier jour du mois de `d`."""
    return date(d.year, d.month, calendar.monthrange(d.year, d.month)[1])
