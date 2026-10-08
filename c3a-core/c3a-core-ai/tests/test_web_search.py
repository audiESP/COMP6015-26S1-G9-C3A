import unittest

from web_search import WebSearchResult, _interleave, _is_excluded_url, build_task_queries


class BuildTaskQueriesTest(unittest.TestCase):
    def test_nutrition_check_uses_symptom_queries_for_first_two_topics(self):
        queries = build_task_queries(
            "Wellbeing and nutrition check",
            "Check comfort, hydration, appetite, and orientation.",
            "wellbeing",
        )

        self.assertEqual(
            queries,
            [
                "signs of dehydration and malnutrition in older people",
                "eating difficulties and loss of appetite in older people tips",
            ],
        )

    def test_mobility_detail_matches_falls_topic(self):
        queries = build_task_queries(
            "Observe mobility and falls risk",
            "Check walker use and whether gait is steady today.",
            "mobility",
        )

        self.assertEqual(queries, ["preventing falls in older people at home walking aids"])

    def test_documentation_ignores_topics_mentioned_in_passing(self):
        queries = build_task_queries(
            "Complete visit summary",
            "Record nutrition, transfer support, and family communication needs.",
            "documentation",
        )

        self.assertEqual(queries, ["recognising and reporting deterioration in older people"])

    def test_unmatched_task_falls_back_to_type_query(self):
        queries = build_task_queries("Personal care", "Assist with grooming.", "wellbeing")

        self.assertEqual(queries, ["signs of dehydration and malnutrition in older people"])

    def test_unmatched_task_without_type_uses_label(self):
        queries = build_task_queries("Garden walk", None, None)

        self.assertEqual(queries, ["Garden walk older people at home"])


class UrlFilterTest(unittest.TestCase):
    def test_policy_pages_are_excluded(self):
        for url in (
            "https://www.health.gov.au/our-work/improving-food-nutrition-aged-care/regulation-compliance",
            "https://www.health.gov.au/ministers/senator/media/welfare-checks",
            "https://www.agedcarequality.gov.au/providers/food-nutrition-dining-information-providers/why-meals-matter",
            "https://www.agedcarequality.gov.au/strengthened-quality-standards/food-and-nutrition",
        ):
            self.assertTrue(_is_excluded_url(url), url)

    def test_practical_pages_are_kept(self):
        for url in (
            "https://www.healthdirect.gov.au/dehydration",
            "https://www.agedcarequality.gov.au/news-publications/clinical-alerts-and-advice/preventing-and-responding-dehydration-older-people-receiving-aged-care-services",
            "https://www.health.vic.gov.au/older-people-in-hospital/nutrition-and-swallowing-in-older-people/swallowing",
        ):
            self.assertFalse(_is_excluded_url(url), url)


class InterleaveTest(unittest.TestCase):
    def test_alternates_between_query_results(self):
        a1, a2, b1 = (WebSearchResult(title=name, url=name, snippet="") for name in ("a1", "a2", "b1"))

        self.assertEqual(_interleave([[a1, a2], [b1]]), [a1, b1, a2])


if __name__ == "__main__":
    unittest.main()
