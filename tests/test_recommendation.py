"""Run with:  python -m unittest discover tests   (no database needed)"""
import os, sys, unittest
from datetime import date
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import ai_recommendation as ai

TODAY = date(2026, 9, 18)
STUDENT = {"cgpa": 8.2, "family_income": 200000, "degree": "B.E.", "community": "BC",
           "gender": "Female", "state": "Tamil Nadu"}


def sch(**kw):
    base = dict(scholarship_name="T", amount=1000, minimum_cgpa=0, maximum_income=0, degree="ALL",
                community="ALL", gender="All", state="ALL", required_documents="Aadhaar",
                last_date="2026-10-30")
    base.update(kw)
    return base


class RecommendationTests(unittest.TestCase):
    def test_open_scholarship_is_full_match(self):
        m = ai.evaluate(STUDENT, sch(), TODAY)
        self.assertEqual(m["percentage"], 100)
        self.assertTrue(m["is_eligible"])

    def test_cgpa_and_income_fail(self):
        m = ai.evaluate(STUDENT, sch(minimum_cgpa=9.0, maximum_income=100000), TODAY)
        self.assertEqual(m["percentage"], 55)          # loses 20 + 25
        self.assertEqual(m["status"], "Not Eligible")
        self.assertEqual(m["failed"], ["CGPA", "Family income"])

    def test_partial_status(self):
        m = ai.evaluate(STUDENT, sch(minimum_cgpa=9.0), TODAY)   # loses only 20 -> 80
        self.assertEqual(m["status"], "Partially Eligible")
        self.assertFalse(m["is_eligible"])

    def test_list_matching_is_case_insensitive(self):
        m = ai.evaluate(STUDENT, sch(community="sc, bc", degree="B.Tech,B.E."), TODAY)
        self.assertTrue(m["is_eligible"])

    def test_gender_and_state(self):
        m = ai.evaluate(STUDENT, sch(gender="Male", state="Kerala"), TODAY)
        self.assertEqual(m["percentage"], 80)

    def test_closed_scholarship(self):
        m = ai.evaluate(STUDENT, sch(last_date="2026-09-10"), TODAY)
        self.assertTrue(m["is_closed"])
        self.assertFalse(m["is_eligible"])
        self.assertEqual(m["status"], "Closed")

    def test_sorting_and_closed_hidden(self):
        items = [sch(scholarship_name="low", minimum_cgpa=9.5),
                 sch(scholarship_name="full"),
                 sch(scholarship_name="old", last_date="2026-01-01")]
        r = ai.recommend(STUDENT, items, TODAY)
        self.assertEqual([x["s"]["scholarship_name"] for x in r], ["full", "low"])

    def test_deadlines(self):
        items = [sch(scholarship_name="a", last_date="2026-09-25"),
                 sch(scholarship_name="b", last_date="2026-12-31"),
                 sch(scholarship_name="c", last_date="2026-09-01")]
        d = ai.upcoming_deadlines(items, TODAY, 30)
        self.assertEqual(len(d), 1)
        self.assertTrue(d[0]["urgent"])

    def test_documents(self):
        self.assertEqual(ai.required_document_fields("Aadhaar, Income Certificate, Marksheet"),
                         ["aadhaar", "income_certificate", "marksheet"])
        st = ai.document_status("Aadhaar,Marksheet", {"aadhaar": "x"})
        self.assertEqual([d["uploaded"] for d in st], [True, False])

    def test_inr_format(self):
        self.assertEqual(ai.format_inr(25000), "\u20b925,000")
        self.assertEqual(ai.format_inr(1200000), "\u20b912,00,000")

    def test_normalize_choice_list(self):
        self.assertEqual(ai.normalize_choice_list("sc, st", ai.COMMUNITIES, "Community"), "SC,ST")
        with self.assertRaises(ValueError):
            ai.normalize_choice_list("xyz", ai.COMMUNITIES, "Community")

    def test_career_plan(self):
        p = ai.build_career_plan("B.Sc.", "Data Science & AI")
        self.assertEqual(p["roadmap"][0], "B.Sc.")
        self.assertIn("Data Scientist", p["roadmap"])
        self.assertEqual(ai.build_career_plan("MCA", "Software Development")["level"], "PG")

if __name__ == "__main__":
    unittest.main()
