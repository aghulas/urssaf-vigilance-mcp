from __future__ import annotations

import httpx
import pytest
import respx

from urssaf_vigilance_mcp.client import ClientAVCS, UrssafApiError, normaliser_code, normaliser_resultat, reponse_mock
from urssaf_vigilance_mcp.config import Settings

TOKEN_URL = "https://api-edi.urssaf.fr/api/oauth/v1/token"
VERIF_URL = "https://api-edi.urssaf.fr/attn/verification/v1/codes_securite/verifier"

# Exemple de la documentation ACOSS (CSG_RSI) + un exemple AVG construit d'après le schéma
EXEMPLE_DOC = {
    "verifierCodeSecuriteAttestationGen": [
        {
            "codeSecurite": "42TROLLQU3DT999",
            "infosSecurisation": {
                "hashKey": "42TROLLQU3DT999",
                "nature": "CSG_RSI",
                "denomination": "Cooper Sheldon",
                "codeOrganismeEmetteur": "837",
                "libelleOrganismeEmetteur": "Urssaf AUVERGNE",
                "date": "02/10/2020",
                "infosSecurisationSpecifiques": [
                    {"infosSecurisationSpecifiquesCSG": {"numExt": "837000000022444999",
                     "etablissement": [{"adresse": "45 Boulevard Pasteur 63000 Clermont-Ferrand", "siret": "314569725 00097"}]}}
                ],
            },
        }
    ]
}


def settings_sandbox(**kw) -> Settings:
    return Settings(client_id="id", client_secret="secret", environnement="sandbox", **kw)


def test_normaliser_code():
    assert normaliser_code(" 8dzg jcmq6u9dzqv ") == "8DZGJCMQ6U9DZQV"
    with pytest.raises(ValueError):
        normaliser_code("TROPCOURT")


def test_normaliser_resultat_doc_csg():
    r = normaliser_resultat(EXEMPLE_DOC["verifierCodeSecuriteAttestationGen"][0])
    assert r.statut == "valide"
    assert r.nature == "CSG_RSI" and not r.est_attestation_vigilance
    assert r.sirets == ["31456972500097"]  # espace retiré
    assert r.organisme_emetteur == "Urssaf AUVERGNE"


def test_normaliser_resultat_avg_et_fautes():
    items = reponse_mock(["MOCKVALIDE00001", "MOCKPERIMEE0001", "MOCKMANQUANT001", "ZZZZZZZZZZZZZZZ"])["verifierCodeSecuriteAttestationGen"]
    ok, per, manq, inc = (normaliser_resultat(i) for i in items)
    assert ok.statut == "valide" and ok.est_attestation_vigilance and ok.siren == "123456789"
    assert ok.effectif == "20" and ok.masse_salariale == "53575.0" and ok.derniere_periode_analysee == "mois de août 2026"
    assert per.statut == "perimee" and per.perimee_depuis == "30/09/2026" and per.fault_code == "FUNC201"
    assert manq.statut == "incomplete"
    assert inc.statut == "inconnue" and inc.fault_code == "FUNC202"


@respx.mock
async def test_verifier_unitaire_avec_jeton():
    token_route = respx.post(TOKEN_URL).mock(return_value=httpx.Response(200, json={"access_token": "tok", "token_type": "Bearer", "expires_in": 3600}))
    verif_route = respx.get(VERIF_URL).mock(return_value=httpx.Response(200, json=EXEMPLE_DOC))
    c = ClientAVCS(settings_sandbox())
    r1 = await c.verifier("42TROLLQU3DT999")
    r2 = await c.verifier("42TROLLQU3DT999", domaine="isu")
    assert r1.statut == "valide" and r2.statut == "valide"
    assert token_route.call_count == 1  # jeton mis en cache
    req = verif_route.calls[0].request
    assert req.headers["Authorization"] == "Bearer tok"
    assert req.url.params["domaine"] == "URSSAF" and req.url.params["codeSecurite"] == "42TROLLQU3DT999"
    assert verif_route.calls[1].request.url.params["domaine"] == "ISU"
    body = token_route.calls[0].request.content.decode()
    assert "grant_type=client_credentials" in body and "scope=attn.codes_securite" in body
    await c.aclose()


@respx.mock
async def test_verifier_lot_decoupe_par_100():
    respx.post(TOKEN_URL).mock(return_value=httpx.Response(200, json={"access_token": "tok", "expires_in": 3600}))

    def repondre(request: httpx.Request) -> httpx.Response:
        import json

        codes = json.loads(request.content)["listeCodesSecurite"]
        assert len(codes) <= 100
        return httpx.Response(200, json=reponse_mock(codes))

    route = respx.post(VERIF_URL).mock(side_effect=repondre)
    c = ClientAVCS(settings_sandbox())
    codes = [f"MOCKVALIDE00001"] * 150
    res = await c.verifier_lot(codes)
    assert len(res) == 150 and route.call_count == 2
    await c.aclose()


@respx.mock
async def test_erreurs_http():
    respx.post(TOKEN_URL).mock(return_value=httpx.Response(200, json={"access_token": "tok", "expires_in": 3600}))
    respx.get(VERIF_URL).mock(return_value=httpx.Response(429, json={"code": "QUOTA"}))
    c = ClientAVCS(settings_sandbox())
    with pytest.raises(UrssafApiError) as e:
        await c.verifier("42TROLLQU3DT999")
    assert e.value.status == 429
    await c.aclose()


@respx.mock
async def test_jeton_refuse():
    respx.post(TOKEN_URL).mock(return_value=httpx.Response(401, json={"error": "invalid_client"}))
    c = ClientAVCS(settings_sandbox())
    with pytest.raises(UrssafApiError) as e:
        await c.verifier("42TROLLQU3DT999")
    assert e.value.status == 401


async def test_identifiants_manquants():
    c = ClientAVCS(Settings(environnement="production"))
    with pytest.raises(UrssafApiError, match="URSSAF_CLIENT_ID"):
        await c.verifier("42TROLLQU3DT999")


async def test_mode_mock_sans_reseau():
    c = ClientAVCS(Settings(mock=True))
    r = await c.verifier("MOCKVALIDE00001")
    assert r.statut == "valide" and r.sirets == ["12345678900012"]
    lot = await c.verifier_lot(["MOCKVALIDE00001", "MOCKPERIMEE0001"])
    assert [x.statut for x in lot] == ["valide", "perimee"]


def test_settings_hotes():
    assert Settings(environnement="production").url_token == "https://api.urssaf.fr/api/oauth/v1/token"
    assert Settings(environnement="sandbox").url_verifier.startswith("https://api-edi.urssaf.fr/attn/verification/v1/")
    with pytest.raises(ValueError):
        Settings(environnement="prod")
