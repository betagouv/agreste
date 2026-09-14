"""Agreste test runner (AI generated, a bit complicated maybe.)

 ``Since faceted_search replaces Sites Conformes search, sites_conformes.core.tests.test_search`` tests are
skipped on full suite runs (``just test``, ``just unittest``, CI). They still
run when that module is requested explicitly, and subclasses such as
``FacetedSearchResultsTestCase`` are unaffected.
"""

from django.test.runner import DiscoverRunner, iter_test_cases

SKIPPED_SEARCH_MODULES = frozenset({"sites_conformes.core.tests.test_search"})


class AgresteDiscoverRunner(DiscoverRunner):
    def load_tests_for_label(self, label, discover_kwargs):
        tests = super().load_tests_for_label(label, discover_kwargs)
        if _label_selects_skipped_search_module(label):
            return tests
        kept = [test for test in iter_test_cases(tests) if test.__class__.__module__ not in SKIPPED_SEARCH_MODULES]
        return self.test_suite(kept)


def _label_selects_skipped_search_module(label: str) -> bool:
    return any(label == module or label.startswith(f"{module}.") for module in SKIPPED_SEARCH_MODULES)
