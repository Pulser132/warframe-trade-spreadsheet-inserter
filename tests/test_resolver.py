"""Unit tests for resolver.py, the pure-Python port of scripts/wf_ducat_lookup.js's
robust matcher (the former Node "Pass 2" resolver, now running everywhere — see
ocr_scanner.scan()). Stdlib only: no Tesseract, no Node, no screenshots required.

Run directly:

    python tests/test_resolver.py
"""

import json
import os
import sys
import unittest

_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _BASE_DIR)

import resolver


def _build_index():
    seed_path = os.path.join(_BASE_DIR, "assets", "seed", "ducat_lookup.json")
    with open(seed_path, "r", encoding="utf-8") as f:
        raw = json.load(f)
    lookup = {resolver.normalize(k): int(v) for k, v in raw.items()}
    return resolver.build_index(lookup)


class ResolverTests(unittest.TestCase):
    INDEX = _build_index()

    def _resolve(self, query):
        return resolver.resolve_one(query, self.INDEX)

    def assertResolvesTo(self, query, expected_name, expected_ducats):
        match = self._resolve(query)
        self.assertIsNotNone(match, f"{query!r} did not resolve")
        self.assertEqual(match["norm"], expected_name)
        self.assertEqual(match["ducats"], expected_ducats)

    # --- Real captured cases (Todo_distfix/Plan.md Phase 1) ---
    # Captured by running ocr_scanner.scan() against OCR Test Images/ with the
    # seeded cache and Node/_resolve_via_wfcd disabled, simulating the frozen
    # exe's old behavior — i.e. genuine OCR misreads, not synthetic strings.

    def test_real_leading_garbage_tokens(self):
        self.assertResolvesTo("op akbronco prime link", "akbronco prime link", 45)
        self.assertResolvesTo(
            "sss gad burston prime stock", "burston prime stock", 15
        )
        self.assertResolvesTo("go venato prime handle", "venato prime handle", 15)

    def test_real_trailing_garbage_tokens(self):
        self.assertResolvesTo(
            "op lam lavos prime blueprint laiat ppraa fi",
            "lavos prime blueprint",
            45,
        )
        self.assertResolvesTo(
            "cedo prime receiver krtla tra rr", "cedo prime receiver", 45
        )

    def test_real_leading_and_internal_misreads(self):
        self.assertResolvesTo(
            "os it stradavar prime blueprint", "stradavar prime blueprint", 100
        )
        self.assertResolvesTo("oo zakti prime blueprint", "zakti prime blueprint", 100)

    # --- Synthetic cases documented in the goal/plan ---

    def test_merged_token_recovery(self):
        # "chroma" + "prime" run together by OCR, as in goal.md's example.
        self.assertResolvesTo(
            "chromapnrrt chassis blueprint", "chroma prime chassis", 25
        )

    def test_mid_word_prime_misread(self):
        self.assertResolvesTo("wisp prini systems blueprint", "wisp prime systems", 15)
        self.assertResolvesTo(
            "gyre priftwe chassis blueprint", "gyre prime chassis", 45
        )

    def test_trailing_blueprint_stripped_for_component(self):
        # The game appends "Blueprint" to component labels @wfcd stores without
        # it; the trailing token must be dropped to match the right entry
        # instead of colliding with the unrelated main "<name> prime blueprint".
        self.assertResolvesTo(
            "chroma prime chassis blueprint", "chroma prime chassis", 25
        )

    # --- False-positive guards ---

    def test_akbolto_does_not_collide_with_zakti(self):
        # Both end in "prime blueprint"; only the leading-token anchor in
        # resolve_by_tokens (and the whole-string ratio threshold) keeps them
        # from colliding.
        match = self._resolve("akbolto prime blueprint")
        self.assertEqual(match["norm"], "akbolto prime blueprint")
        self.assertNotEqual(match["norm"], "zakti prime blueprint")

    def test_akvasto_does_not_collide_with_zakti(self):
        match = self._resolve("akvasto prime blueprint")
        self.assertEqual(match["norm"], "akvasto prime blueprint")

    def test_component_blueprint_does_not_lose_to_main_blueprint(self):
        # A genuine main blueprint query must still resolve to itself, not get
        # swallowed by the trailing-"blueprint"-stripping meant for components.
        self.assertResolvesTo("chroma prime blueprint", "chroma prime blueprint", 15)

    # --- Exact-match / clean-name sanity ---

    def test_clean_names_resolve_to_themselves(self):
        for name in (
            "braton prime receiver",
            "equinox prime chassis",
            "akarius prime blueprint",
            "caliban prime neuroptics",
        ):
            self.assertResolvesTo(name, name, self._ducats_for(name))

    def _ducats_for(self, name):
        for entry in self.INDEX:
            if entry["norm"] == name:
                return entry["ducats"]
        self.fail(f"{name!r} not found in seed index")

    def test_unresolvable_query_returns_none(self):
        self.assertIsNone(self._resolve("xyzzy totally not an item qwerty"))

    def test_empty_query_returns_none(self):
        self.assertIsNone(self._resolve(""))
        self.assertIsNone(self._resolve("   "))

    # --- Threshold kwargs: defaults are behavior-preserving ---

    def test_default_kwargs_match_no_kwarg_calls(self):
        # The new whole/token/anchor kwargs default to the historical constants,
        # so calling with the defaults must be identical to the no-kwarg call.
        queries = [
            "op akbronco prime link",
            "chromapnrrt chassis blueprint",
            "akbolto prime blueprint",
            "braton prime receiver",
            "xyzzy totally not an item qwerty",
        ]
        for q in queries:
            self.assertEqual(
                resolver.resolve_one(q, self.INDEX),
                resolver.resolve_one(q, self.INDEX, whole=0.85, token=0.80),
                msg=q,
            )
        for q in ("wisp prini systems blueprint", "gyre priftwe chassis blueprint"):
            nq = resolver.normalize(q)
            self.assertEqual(
                resolver.resolve_by_tokens(nq, self.INDEX),
                resolver.resolve_by_tokens(nq, self.INDEX, token=0.80, anchor=0.85),
                msg=q,
            )

    def test_loosened_whole_resolves_otherwise_rejected(self):
        # Rejected at the default 0.85 whole-string gate, but a loosened 0.70
        # gate clears it — proving `whole` is actually wired through.
        q = "cfdo prime rfdeiver"
        self.assertIsNone(resolver.resolve_one(q, self.INDEX))
        match = resolver.resolve_one(q, self.INDEX, whole=0.70)
        self.assertIsNotNone(match)
        self.assertEqual(match["norm"], "cedo prime receiver")

    # --- rank_candidates (debug-only candidate scoring) ---

    def test_rank_candidates_shape_and_order(self):
        cands = resolver.rank_candidates("braton prime receiver", self.INDEX, n=5)
        self.assertLessEqual(len(cands), 5)
        scores = [c["score"] for c in cands]
        self.assertEqual(scores, sorted(scores, reverse=True))
        for c in cands:
            self.assertEqual(set(c.keys()), {"norm", "ducats", "score", "metric"})
            self.assertIn(c["metric"], ("whole", "token"))

    def test_rank_candidates_exact_match_is_first_and_scores_one(self):
        cands = resolver.rank_candidates("braton prime receiver", self.INDEX)
        self.assertEqual(cands[0]["norm"], "braton prime receiver")
        self.assertAlmostEqual(cands[0]["score"], 1.0)

    def test_rank_candidates_empty_query_returns_empty(self):
        self.assertEqual(resolver.rank_candidates("", self.INDEX), [])
        self.assertEqual(resolver.rank_candidates("   ", self.INDEX), [])

    def test_rank_candidates_respects_n(self):
        self.assertLessEqual(len(resolver.rank_candidates("prime", self.INDEX, n=3)), 3)


if __name__ == "__main__":
    unittest.main()
