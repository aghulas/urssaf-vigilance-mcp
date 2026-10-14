"""Contrôle de cohérence PDF ↔ résultat Urssaf et calcul de la fin de validité.

Règle de validité (art. L.243-15 CSS, reprise par API Entreprise) : l'attestation est valable
6 mois à compter de la date de fin de la période analysée, arrondi à la fin du mois.
Ex. : à jour au 31/08/2026 → échéance 28/02/2027.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from datetime import date

from .modeles import PERIMEE, VALIDE, AttestationPdf, ResultatVerification
from .pdf import fin_de_mois, fin_de_mois_depuis_libelle

ALERTE_JOURS = 30


def fin_de_validite(a_jour_au: date) -> date:
    """6 mois après la date de situation, en fin de mois."""
    mois = a_jour_au.month + 6
    annee = a_jour_au.year + (mois - 1) // 12
    mois = (mois - 1) % 12 + 1
    return fin_de_mois(date(annee, mois, 1))


def _date_fr(s: str | None) -> date | None:
    if not s:
        return None
    m = re.search(r"(\d{2})/(\d{2})/(\d{4})", s)
    return date(int(m.group(3)), int(m.group(2)), int(m.group(1))) if m else None


def _periode_api_vers_date(libelle: str | None) -> date | None:
    """'mois de août 2026' → 31/08/2026 ; '31/08/2026' → idem."""
    if not libelle:
        return None
    if d := _date_fr(libelle):
        return d
    m = re.search(r"([a-zéû]+\s+\d{4})", libelle, re.I)
    return fin_de_mois_depuis_libelle(m.group(1)) if m else None


@dataclass
class Controle:
    code_securite: str | None
    statut_urssaf: str
    conforme: bool
    verdict: str  # OK | ALERTE | REFUS
    fin_de_validite: date | None = None
    jours_restants: int | None = None
    verifications: list[dict] = field(default_factory=list)
    anomalies: list[str] = field(default_factory=list)
    avertissements: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["fin_de_validite"] = self.fin_de_validite.isoformat() if self.fin_de_validite else None
        return d


def controler(
    pdf: AttestationPdf | None,
    api: ResultatVerification,
    siret_attendu: str | None = None,
    siren_attendu: str | None = None,
    aujourdhui: date | None = None,
) -> Controle:
    aujourdhui = aujourdhui or date.today()
    c = Controle(code_securite=api.code_securite, statut_urssaf=api.statut, conforme=True, verdict="OK")

    def check(libelle: str, attendu, obtenu, ok: bool, bloquant: bool = True) -> None:
        c.verifications.append({"controle": libelle, "attendu": attendu, "obtenu": obtenu, "ok": ok})
        if not ok:
            msg = f"{libelle} : attendu {attendu!r}, obtenu {obtenu!r}"
            (c.anomalies if bloquant else c.avertissements).append(msg)

    # 1. Authenticité
    if api.statut != VALIDE:
        c.conforme = False
        c.verdict = "REFUS"
        if api.statut == PERIMEE:
            c.anomalies.append(f"Attestation périmée selon l'Urssaf (depuis le {api.perimee_depuis or '?'})")
            c.fin_de_validite = _date_fr(api.perimee_depuis)
        else:
            c.anomalies.append(f"Code non reconnu par l'Urssaf ({api.fault_code or api.statut}) : {api.message}")
        return c

    check("Nature = attestation de vigilance", "AVG_UR / AVG_RSI", api.nature, api.est_attestation_vigilance)

    # 2. Cohérence avec le PDF
    if pdf is not None:
        if pdf.code_securite:
            check("Code de sécurité du PDF", pdf.code_securite, api.code_securite, pdf.code_securite == api.code_securite)
        if pdf.siren and api.siren:
            check("SIREN", pdf.siren, api.siren, pdf.siren == api.siren)
        elif pdf.siren and api.sirets:
            check("SIREN (via SIRET Urssaf)", pdf.siren, api.sirets[0][:9], all(s.startswith(pdf.siren) for s in api.sirets))
        if pdf.date_delivrance and api.date_certification:
            check("Date de certification", pdf.date_delivrance.strftime("%d/%m/%Y"), api.date_certification,
                  _date_fr(api.date_certification) == pdf.date_delivrance, bloquant=False)
        if pdf.effectif is not None and api.effectif is not None:
            check("Effectif", pdf.effectif, api.effectif, _num(api.effectif) == pdf.effectif, bloquant=False)
        if pdf.masse_salariale is not None and api.masse_salariale is not None:
            check("Masse salariale", pdf.masse_salariale, api.masse_salariale, _num(api.masse_salariale) == pdf.masse_salariale, bloquant=False)
        if pdf.sirets and api.sirets:
            manquants = sorted(set(pdf.sirets) - set(api.sirets))
            check("SIRET du PDF présents chez l'Urssaf", pdf.sirets, api.sirets, not manquants)
        if pdf.a_jour_au and api.derniere_periode_analysee:
            d_api = _periode_api_vers_date(api.derniere_periode_analysee)
            if d_api:
                check("Dernière période analysée", pdf.a_jour_au.strftime("%d/%m/%Y"), d_api.strftime("%d/%m/%Y"), d_api == pdf.a_jour_au, bloquant=False)
        if pdf.raison_sociale and api.denomination:
            ok = _normaliser_nom(api.denomination) in _normaliser_nom(pdf.raison_sociale) or _normaliser_nom(pdf.raison_sociale) in _normaliser_nom(api.denomination)
            check("Raison sociale", pdf.raison_sociale, api.denomination, ok, bloquant=False)

    # 3. Cocontractant attendu
    if siren_attendu:
        siren_obs = api.siren or (api.sirets[0][:9] if api.sirets else None) or (pdf.siren if pdf else None)
        check("SIREN du cocontractant", siren_attendu, siren_obs, siren_obs == siren_attendu)
    if siret_attendu:
        sirets_obs = api.sirets or (pdf.sirets if pdf else [])
        check("SIRET de l'établissement prestataire", siret_attendu, sirets_obs, siret_attendu in sirets_obs)

    # 4. Validité dans le temps
    base = (pdf.a_jour_au if pdf and pdf.a_jour_au else None) or _periode_api_vers_date(api.derniere_periode_analysee)
    if base:
        c.fin_de_validite = fin_de_validite(base)
        c.jours_restants = (c.fin_de_validite - aujourdhui).days
        if c.jours_restants < 0:
            c.anomalies.append(f"Attestation périmée depuis le {c.fin_de_validite.strftime('%d/%m/%Y')} (6 mois après le {base.strftime('%d/%m/%Y')})")
        elif c.jours_restants <= ALERTE_JOURS:
            c.avertissements.append(f"Échéance proche : {c.fin_de_validite.strftime('%d/%m/%Y')} ({c.jours_restants} j) — nouvelle attestation à demander")
    else:
        c.avertissements.append("Période analysée introuvable : fin de validité non calculable")

    if c.anomalies:
        c.conforme = False
        c.verdict = "REFUS"
    elif c.avertissements:
        c.verdict = "ALERTE"
    return c


def _num(s: str | None) -> int | None:
    try:
        return int(float(str(s).replace(",", ".").replace(" ", "")))
    except Exception:  # noqa: BLE001
        return None


def _normaliser_nom(s: str) -> str:
    s = re.sub(r"\b(SAS|SASU|SARL|EURL|SA|SCI|SNC|SCOP|SELARL|STE|SOCIETE)\b", " ", s.upper())
    return re.sub(r"[^A-Z0-9]", "", s)
