from __future__ import annotations

from datetime import date

import pytest

from urssaf_vigilance_mcp import server
from urssaf_vigilance_mcp.suivi import Suivi


def test_suivi_lecture(classeur_suivi):
    s = Suivi(classeur_suivi)
    assert s.ligne_entetes == 4
    lignes = s.lignes()
    assert [l.entreprise for l in lignes] == ["REVALECO", "REVALECO", "REUX", "INCONNU SARL", "(non attribué)"]
    assert lignes[0].echeance == date(2027, 2, 28)
    codes = s.codes_uniques()
    assert set(codes) == {"MOCKVALIDE00001", "MOCKPERIMEE0001", "MOCKINCONNU0001"}
    assert len(codes["MOCKVALIDE00001"]) == 2  # même code sur deux lots
    a_verifier = s.codes_uniques(seulement_a_verifier=True)
    assert set(a_verifier) == {"MOCKVALIDE00001", "MOCKINCONNU0001"}  # REUX déjà « authentique »


def test_suivi_ecriture_conserve_historique(classeur_suivi):
    s = Suivi(classeur_suivi)
    s.ecrire_verification(5, "Authentique et valide - SIRET 12345678900012 (verifie par API Urssaf le 13/10/2026)")
    s.ecrire_verification(8, "CODE INCONNU", echeance=date(2026, 9, 30))
    s.enregistrer()
    s2 = Suivi(classeur_suivi)
    l5 = [l for l in s2.lignes() if l.ligne == 5][0]
    assert l5.verification.startswith("Attestation du 05/10/2026 - SIRET 12345678900012 - Authentique et valide")
    assert "code à vérifier" not in l5.verification and not l5.code_a_verifier
    l8 = [l for l in s2.lignes() if l.ligne == 8][0]
    assert l8.verification == "CODE INCONNU" and l8.echeance == date(2026, 9, 30)


@pytest.fixture
def env_mock(monkeypatch, classeur_suivi):
    monkeypatch.setenv("URSSAF_MOCK", "1")
    monkeypatch.setenv("URSSAF_FICHIER_SUIVI", str(classeur_suivi))
    monkeypatch.delenv("URSSAF_ECRITURE", raising=False)
    server._settings = None
    server._client = None
    yield
    server._settings = None
    server._client = None


async def test_outils_mcp_mock(env_mock, classeur_suivi, pdf_exemple):
    etat = server.etat_connecteur()
    assert etat["mock"] is True and etat["ecriture_excel"] is False

    r = await server.verifier_attestation("MOCKVALIDE00001")
    assert r["statut"] == "valide" and r["sirets"] == ["12345678900012"]

    r = await server.verifier_attestation("court")
    assert r["erreur"] == "ValueError"

    lot = await server.verifier_attestations(["MOCKVALIDE00001", "MOCKPERIMEE0001"])
    assert lot["nombre"] == 2 and lot["valides"] == 1

    pdf = server.lire_attestation_pdf(str(pdf_exemple))
    assert pdf["code_securite"] == "MOCKVALIDE00001"

    # le PDF fictif porte le code MOCKVALIDE00001 connu du mock : contrôle complet OK de bout en bout
    ctl = await server.controler_attestation(str(pdf_exemple), siret_attendu="12345678900012")
    assert ctl["controle"]["verdict"] == "OK" and ctl["urssaf"]["statut"] == "valide", ctl
    assert ctl["controle"]["fin_de_validite"] == "2027-02-28"
    assert "Authentique et valide - SIRET 12345678900012" in ctl["texte_suivi"]
    refus = await server.controler_attestation(str(pdf_exemple), siret_attendu="12345678900099")
    assert refus["controle"]["verdict"] == "REFUS"

    liste = server.suivi_lister()
    assert len(liste["lignes"]) == 5 and set(liste["codes_uniques"]) == {"MOCKVALIDE00001", "MOCKPERIMEE0001", "MOCKINCONNU0001"}
    assert [p["entreprise"] for p in liste["perimees_au_tableau"]] == ["REUX"]


async def test_suivi_verifier_simulation_puis_ecriture(env_mock, monkeypatch, classeur_suivi):
    sim = await server.suivi_verifier()
    assert sim["verifies"] == 2 and "fichier_enregistre" not in sim
    assert {r["code"]: r["statut"] for r in sim["resultats"]} == {"MOCKVALIDE00001": "valide", "MOCKINCONNU0001": "inconnue"}

    refus = await server.suivi_verifier(ecrire=True)
    assert all(r["ecriture"].startswith("refusée") for r in refus["resultats"])
    assert Suivi(classeur_suivi).lignes()[0].code_a_verifier  # rien écrit

    monkeypatch.setenv("URSSAF_ECRITURE", "1")
    fait = await server.suivi_verifier(tous=True, ecrire=True)
    assert fait["verifies"] == 3 and fait["fichier_enregistre"]
    s = Suivi(classeur_suivi)
    assert not any(l.code_a_verifier for l in s.lignes() if l.code_securite)
    reux = [l for l in s.lignes() if l.entreprise == "REUX"][0]
    assert "PERIMEE selon l'Urssaf depuis le 30/09/2026" in reux.verification
