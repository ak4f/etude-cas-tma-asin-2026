"""Tests automatisés des règles de gestion (un groupe de tests par ticket).

Lancement : python -m unittest -v
Le module testé peut être remplacé par la variable d'environnement REGLES_MODULE
(voir le README, section « Preuve que les tests rejouent les anomalies »).

Auteur : ANATO Kodjo Freddy
"""

import importlib
import os
import unittest
from datetime import datetime, timedelta

R = importlib.import_module(os.environ.get("REGLES_MODULE", "regles_rendez_vous"))

EXPORT = datetime(2026, 11, 20, 18, 0)  # instant de l'export de la base


def dt(texte):
    return datetime.strptime(texte, "%Y-%m-%d %H:%M")


class OutilsTest(unittest.TestCase):
    def assertRefus(self, res, code, message):
        self.assertFalse(res.ok, f"refus attendu, obtenu : {res}")
        self.assertEqual(res.code, code)
        self.assertEqual(res.message, message)

    def assertAccepte(self, res):
        self.assertTrue(res.ok, f"acceptation attendue, obtenu : {res}")


class TestTMA103SaisieNPI(OutilsTest):
    """TMA-103 : un NPI contenant une lettre doit être refusé en 400, jamais en 500."""

    MAINT = dt("2026-11-20 09:00")

    def prise(self, npi, service="CNI", date="2026-11-23T09:00"):
        return R.controler_prise(npi, service, date, [], self.MAINT)

    def test_trace_du_ticket_lettre_dans_le_npi(self):
        res = self.prise("06142A3647")
        self.assertRefus(res, 400, "Le NPI doit comporter exactement 10 chiffres.")

    def test_npi_de_longueur_incorrecte(self):
        for npi in ("", "123456789", "01234567890", "061425364711"):
            with self.subTest(npi=npi):
                self.assertRefus(self.prise(npi), 400, R.MSG_NPI)

    def test_npi_piegeux(self):
        pieges = (
            " 0614253647",
            "0614253647 ",
            "0614253647\n",
            "0614 253647",
            "0614-253647",
            "٠٦١٤٢٥٣٦٤٧",  # dix chiffres arabes orientaux : ce ne sont pas des 0 à 9
            "0614253647\x00",
            "+614253647",
        )
        for npi in pieges:
            with self.subTest(npi=repr(npi)):
                self.assertRefus(self.prise(npi), 400, R.MSG_NPI)

    def test_npi_non_textuel(self):
        for npi in (None, 614253647, 614253647.0, ["0614253647"], b"0614253647"):
            with self.subTest(npi=repr(npi)):
                self.assertRefus(self.prise(npi), 400, R.MSG_NPI)

    def test_npi_valide_accepte(self):
        for npi in ("0614253647", "0000000000", "9999999999"):
            with self.subTest(npi=npi):
                self.assertAccepte(self.prise(npi))

    def test_service_inconnu(self):
        for service in ("PASSPORT", "passeport", "Cni", "", " CNI", None, 3):
            with self.subTest(service=repr(service)):
                res = self.prise("0614253647", service=service)
                self.assertRefus(
                    res, 400, "Service inconnu : choisissez PASSEPORT, CNI ou PERMIS."
                )

    def test_services_connus(self):
        for service in ("PASSEPORT", "CNI", "PERMIS"):
            with self.subTest(service=service):
                self.assertAccepte(self.prise("0614253647", service=service))

    def test_date_illisible(self):
        illisibles = (
            "2026-11-23 09:00",
            "23/11/2026 09:00",
            "2026-11-23T9:00",
            "2026-11-23T09:00:00",
            "2026-11-23",
            "2026-13-01T09:00",
            "2026-02-30T09:00",
            "2026-11-23T24:00",
            "2026-11-23T09:60",
            "",
            None,
            20261123,
            "2026-11-23T09:00\n",
        )
        for date in illisibles:
            with self.subTest(date=repr(date)):
                res = self.prise("0614253647", date=date)
                self.assertRefus(
                    res,
                    400,
                    "Date et heure invalides (format attendu : AAAA-MM-JJTHH:MM).",
                )

    def test_ordre_des_controles_npi_avant_service_avant_date(self):
        self.assertRefus(self.prise("abc", service="X", date="n'importe quoi"), 400, R.MSG_NPI)
        self.assertRefus(self.prise("0614253647", service="X", date="n'importe quoi"), 400, R.MSG_SERVICE)


if __name__ == "__main__":
    unittest.main()
