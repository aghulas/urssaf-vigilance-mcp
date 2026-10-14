"""Client de l'API Urssaf « Attestations Vérification Code Sécurité » (AVCS).

Documentation : ACOSS, API Attestations – Codes sécurité v1.2 (nov. 2020).
- Jeton : POST https://{hote}/api/oauth/v1/token (client_credentials, scope attn.codes_securite)
- Unitaire : GET  /attn/verification/v1/codes_securite/verifier?domaine=URSSAF&codeSecurite=…
- Lot      : POST /attn/verification/v1/codes_securite/verifier  {"listeCodesSecurite": [...]} (≤ 100)
"""

from __future__ import annotations

import asyncio
import re
import time
from typing import Any

import httpx

from .config import SCOPE, Settings
from .modeles import (
    ERREUR,
    INCOMPLETE,
    INCONNUE,
    NATURES,
    NATURES_VIGILANCE,
    PERIMEE,
    VALIDE,
    Etablissement,
    ResultatVerification,
)

MAX_CODES_PAR_APPEL = 100
RE_CODE = re.compile(r"^[A-Z0-9]{15}$")


class UrssafApiError(RuntimeError):
    """Erreur HTTP ou technique renvoyée par l'API (hors erreurs fonctionnelles FUNC2xx)."""

    def __init__(self, message: str, status: int | None = None, detail: Any = None):
        super().__init__(message)
        self.status = status
        self.detail = detail


def normaliser_code(code: str) -> str:
    """Nettoie un code de sécurité saisi (espaces, minuscules) et le valide."""
    c = re.sub(r"\s+", "", str(code or "")).upper()
    if not RE_CODE.match(c):
        raise ValueError(f"Code de sécurité invalide : {code!r} (15 caractères alphanumériques attendus)")
    return c


def normaliser_resultat(item: dict) -> ResultatVerification:
    """Transforme un élément de `verifierCodeSecuriteAttestationGen` en résultat normalisé."""
    code = item.get("codeSecurite", "")
    fault = item.get("functionalFaultCodeSecurite") or {}
    if fault:
        fault_code = fault.get("faultCode", "")
        fault_name = fault.get("faultName", "")
        statut = ERREUR
        perimee_depuis = None
        if fault_code == "FUNC202":
            statut = INCONNUE
        elif fault_code == "FUNC201":
            statut = PERIMEE
            m = re.search(r"(\d{2}/\d{2}/\d{4})", fault_name)
            perimee_depuis = m.group(1) if m else None
        elif fault_code == "FUNC203":
            statut = INCOMPLETE
        return ResultatVerification(
            code_securite=code,
            statut=statut,
            message=fault_name or fault_code,
            fault_code=fault_code,
            perimee_depuis=perimee_depuis,
            brut=item,
        )

    infos = item.get("infosSecurisation") or {}
    nature = infos.get("nature")
    res = ResultatVerification(
        code_securite=code,
        statut=VALIDE,
        message="Attestation authentique et valide",
        nature=nature,
        nature_libelle=NATURES.get(nature, nature),
        est_attestation_vigilance=nature in NATURES_VIGILANCE,
        denomination=infos.get("denomination"),
        organisme_emetteur=infos.get("libelleOrganismeEmetteur"),
        date_certification=infos.get("date"),
        brut=item,
    )
    for spec in infos.get("infosSecurisationSpecifiques") or []:
        for cle, bloc in spec.items():
            if not isinstance(bloc, dict):
                continue
            # AVG, AMP, CSG, CFP, EPM, FRS, CAAE, ASAA : on prend ce qui existe
            res.siren = bloc.get("siren") or res.siren
            res.derniere_periode_analysee = bloc.get("dernierePeriodeAnalysee") or res.derniere_periode_analysee
            res.masse_salariale = _str_ou_none(bloc.get("masseSalariale")) or res.masse_salariale
            res.effectif = _str_ou_none(bloc.get("effectif")) or res.effectif
            for e in bloc.get("etablissement") or []:
                siret = re.sub(r"\s+", "", str(e.get("siret", "")))
                res.etablissements.append(Etablissement(siret=siret, adresse=re.sub(r"\s+", " ", e.get("adresse") or "").strip()))
    return res


def _str_ou_none(v: Any) -> str | None:
    return None if v is None else str(v)


class ClientAVCS:
    """Client asynchrone avec cache de jeton OAuth2."""

    def __init__(self, settings: Settings, http: httpx.AsyncClient | None = None):
        self.settings = settings
        self._http = http
        self._token: str | None = None
        self._token_expire: float = 0.0
        self._lock = asyncio.Lock()

    @property
    def http(self) -> httpx.AsyncClient:
        if self._http is None:
            self._http = httpx.AsyncClient(timeout=self.settings.timeout)
        return self._http

    async def aclose(self) -> None:
        if self._http is not None:
            await self._http.aclose()
            self._http = None

    # --- jeton -----------------------------------------------------------
    async def jeton(self) -> str:
        async with self._lock:
            if self._token and time.monotonic() < self._token_expire - 120:
                return self._token
            if not self.settings.client_id or not self.settings.client_secret:
                raise UrssafApiError(
                    "Identifiants manquants : définir URSSAF_CLIENT_ID et URSSAF_CLIENT_SECRET "
                    "(ou URSSAF_MOCK=1 pour le mode simulé)."
                )
            r = await self.http.post(
                self.settings.url_token,
                data={
                    "grant_type": "client_credentials",
                    "client_id": self.settings.client_id,
                    "client_secret": self.settings.client_secret,
                    "scope": SCOPE,
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            if r.status_code != 200:
                raise UrssafApiError(f"Obtention du jeton refusée (HTTP {r.status_code})", r.status_code, _corps(r))
            data = r.json()
            self._token = data["access_token"]
            self._token_expire = time.monotonic() + float(data.get("expires_in", 3600))
            return self._token

    # --- appels ----------------------------------------------------------
    async def verifier(self, code: str, domaine: str | None = None) -> ResultatVerification:
        code = normaliser_code(code)
        if self.settings.mock:
            return normaliser_resultat(reponse_mock([code])["verifierCodeSecuriteAttestationGen"][0])
        tok = await self.jeton()
        r = await self.http.get(
            self.settings.url_verifier,
            params={"domaine": (domaine or self.settings.domaine_defaut).upper(), "codeSecurite": code},
            headers={"Authorization": f"Bearer {tok}", "Accept": "application/json"},
        )
        items = self._extraire(r)
        if not items:
            raise UrssafApiError("Réponse vide de l'API", r.status_code, _corps(r))
        return normaliser_resultat(items[0])

    async def verifier_lot(self, codes: list[str]) -> list[ResultatVerification]:
        codes_n = [normaliser_code(c) for c in codes]
        if not codes_n:
            return []
        resultats: list[ResultatVerification] = []
        for i in range(0, len(codes_n), MAX_CODES_PAR_APPEL):
            tranche = codes_n[i : i + MAX_CODES_PAR_APPEL]
            if self.settings.mock:
                items = reponse_mock(tranche)["verifierCodeSecuriteAttestationGen"]
            else:
                tok = await self.jeton()
                r = await self.http.post(
                    self.settings.url_verifier,
                    json={"listeCodesSecurite": tranche},
                    headers={"Authorization": f"Bearer {tok}", "Accept": "application/json"},
                )
                items = self._extraire(r)
            resultats.extend(normaliser_resultat(it) for it in items)
        return resultats

    def _extraire(self, r: httpx.Response) -> list[dict]:
        if r.status_code == 429:
            raise UrssafApiError("Quota d'appels dépassé (HTTP 429) : réessayer plus tard", 429, _corps(r))
        if r.status_code in (401, 403):
            self._token = None
            raise UrssafApiError(f"Accès refusé (HTTP {r.status_code}) : jeton ou habilitation invalide", r.status_code, _corps(r))
        if r.status_code >= 400:
            raise UrssafApiError(f"Erreur de l'API (HTTP {r.status_code})", r.status_code, _corps(r))
        data = r.json()
        return list(data.get("verifierCodeSecuriteAttestationGen") or [])


def _corps(r: httpx.Response) -> Any:
    try:
        return r.json()
    except Exception:  # noqa: BLE001
        return r.text[:500]


# --- Mode simulé ---------------------------------------------------------
# Jeu de données fictif, inspiré de l'exemple de la documentation ACOSS. Permet de
# développer et tester le connecteur avant réception des identifiants.
MOCK_VALIDES: dict[str, dict] = {
    "MOCKVALIDE00001": {
        "nature": "AVG_UR",
        "denomination": "SAS EXEMPLE BTP",
        "codeOrganismeEmetteur": "117",
        "libelleOrganismeEmetteur": "URSSAF ILE DE FRANCE",
        "date": "05/10/2026",
        "infosSecurisationSpecifiques": [
            {
                "infosSecurisationSpecifiquesAVG": {
                    "siren": "123456789",
                    "nir": None,
                    "etablissement": [{"adresse": "1 RUE DE L'EXEMPLE 77300 FONTAINEBLEAU", "siret": "12345678900012"}],
                    "dernierePeriodeAnalysee": "mois de août 2026",
                    "masseSalariale": "53575.0",
                    "effectif": "20",
                }
            }
        ],
    },
    "MOCKCSG00000001": {
        "nature": "CSG_RSI",
        "denomination": "Cooper Sheldon",
        "codeOrganismeEmetteur": "837",
        "libelleOrganismeEmetteur": "Urssaf AUVERGNE",
        "date": "02/10/2020",
        "infosSecurisationSpecifiques": [
            {
                "infosSecurisationSpecifiquesCSG": {
                    "numExt": "837000000022444999",
                    "etablissement": [{"adresse": "45 Boulevard Pasteur 63000 Clermont-Ferrand", "siret": "31456972500097"}],
                }
            }
        ],
    },
}
MOCK_FAUTES: dict[str, dict] = {
    "MOCKPERIMEE0001": {"faultName": "Attestation perimée depuis le 30/09/2026", "faultCode": "FUNC201"},
    "MOCKMANQUANT001": {"faultName": "Donnée de sécurisation manquante", "faultCode": "FUNC203"},
}


def reponse_mock(codes: list[str]) -> dict:
    items = []
    for c in codes:
        if c in MOCK_VALIDES:
            infos = dict(MOCK_VALIDES[c])
            infos["hashKey"] = c
            items.append({"codeSecurite": c, "infosSecurisation": infos})
        elif c in MOCK_FAUTES:
            items.append({"codeSecurite": c, "functionalFaultCodeSecurite": MOCK_FAUTES[c]})
        else:
            items.append({"codeSecurite": c, "functionalFaultCodeSecurite": {"faultName": "Attestation inconnue", "faultCode": "FUNC202"}})
    return {"verifierCodeSecuriteAttestationGen": items}
