"""Pure-Python port of scripts/wf_ducat_lookup.js's robust name matcher.

This is the runtime replacement for the Node "Pass 2" resolver: the frozen
exe never bundles Node/scripts/node_modules, so the old `_resolve_via_wfcd`
subprocess call never ran in the distributed build, leaving messy OCR reads
(typos, merged tokens, mid-word misreads) unresolved. Porting the matcher to
stdlib Python makes it available everywhere, against the same lookup data
the app already loads (`ocr_scanner._load_lookup()` / the seeded
`assets/seed/ducat_lookup.json`) — no new bundled data needed.

Ported 1:1 from scripts/wf_ducat_lookup.js (normalize/levenshtein/ratio/
tokenSim/bestTokenRatio/resolveByTokens/resolveOne) — same thresholds
(0.85 / 0.85 / 0.8), same ordering, same "prime"-token stripping and trailing-
"Blueprint" handling. Do not substitute difflib.SequenceMatcher here; it's a
different similarity metric and would silently shift every threshold.
"""

import re


def normalize(s):
    """1:1 with the JS `normalize` and ocr_scanner._normalize: lowercase, strip
    non [a-z0-9\\s], collapse whitespace."""
    s = str(s).lower()
    s = re.sub(r"[^a-z0-9\s]", "", s)
    return re.sub(r"\s+", " ", s).strip()


def _levenshtein(a, b):
    m, n = len(a), len(b)
    if m == 0:
        return n
    if n == 0:
        return m
    prev = list(range(n + 1))
    curr = [0] * (n + 1)
    for i in range(1, m + 1):
        curr[0] = i
        for j in range(1, n + 1):
            cost = 0 if a[i - 1] == b[j - 1] else 1
            curr[j] = min(prev[j] + 1, curr[j - 1] + 1, prev[j - 1] + cost)
        prev, curr = curr, prev
    return prev[n]


def _ratio(a, b):
    max_len = max(len(a), len(b)) or 1
    return 1 - _levenshtein(a, b) / max_len


def _token_sim(a, b):
    """Edit-ratio, with a containment boost for a merged OCR token (e.g.
    "chromapnrrt" embedding "chroma") so it still anchors on the embedded name."""
    r = _ratio(a, b)
    short, long_ = (a, b) if len(a) <= len(b) else (b, a)
    if len(short) >= 4 and short in long_:
        return max(r, 0.9)
    return r


def _best_token_ratio(token, pool):
    best = 0
    for p in pool:
        r = _token_sim(token, p)
        if r > best:
            best = r
    return best


def _strip_trailing_blueprint(q_toks):
    """Drop a trailing "blueprint" on a >=3-token query when the preceding
    token isn't "prime" — mirrors the game appending "Blueprint" to component
    labels that @wfcd/items stores without it (only a main blueprint keeps
    "...prime blueprint")."""
    n = len(q_toks)
    if n >= 3 and q_toks[-1] == "blueprint" and q_toks[-2] != "prime":
        return q_toks[:-1]
    return q_toks


def resolve_by_tokens(q, index, *, token=0.80, anchor=None):
    """Token-overlap fallback for labels with a mid-word OCR misread. Anchors
    on the distinctive leading name token, then scores each candidate by how
    well its tokens align with the query's.

    `anchor` is the leading-token gate (defaults to 0.85, the historical value);
    `token` is the final token-overlap score gate (defaults to 0.80). The defaults
    reproduce the original hardcoded behavior exactly.
    """
    if anchor is None:
        anchor = 0.85
    q_toks = [t for t in q.split(" ") if t]
    q_toks = _strip_trailing_blueprint(q_toks)

    def discriminative(toks):
        return [t for t in toks if t != "prime"]

    q_toks = discriminative(q_toks)
    if not q_toks:
        return None

    best = None
    best_score = 0
    for it in index:
        c_toks = discriminative([t for t in it["norm"].split(" ") if t])
        if not c_toks:
            continue
        if _best_token_ratio(c_toks[0], q_toks) < anchor:
            continue
        total = sum(_best_token_ratio(ct, q_toks) for ct in c_toks)
        score = total / len(c_toks)
        if score > best_score:
            best_score = score
            best = it
    return best if best and best_score >= token else None


def resolve_one(query, index, *, whole=0.85, token=0.80):
    """Hybrid resolve: exact normalized match, substring, whole-string fuzzy
    >= `whole`, then the token-overlap fallback for mid-word misreads.

    `whole` is the whole-string fuzzy gate (default 0.85) and is also forwarded
    as the Pass-2 leading-token anchor (the two were historically coupled at
    0.85). `token` is the token-overlap gate (default 0.80). Defaults reproduce
    the original hardcoded behavior exactly.
    """
    q = normalize(query)
    if not q:
        return None

    for it in index:
        if it["norm"] == q:
            return it

    if len(q) >= 6:
        best = None
        for it in index:
            if q in it["norm"] or it["norm"] in q:
                if best is None or len(it["norm"]) < len(best["norm"]):
                    best = it
        if best:
            return best

    best = None
    best_score = 0
    for it in index:
        score = _ratio(q, it["norm"])
        if score > best_score:
            best_score = score
            best = it
    if best and best_score >= whole:
        return best

    return resolve_by_tokens(q, index, token=token, anchor=whole)


def _token_score(q, norm):
    """The token-overlap alignment score of a candidate `norm` against query `q`,
    using the same discriminative-token / leading-anchor logic as
    resolve_by_tokens (but without any gate) — for debug ranking only."""
    def discriminative(toks):
        return [t for t in toks if t != "prime"]

    q_toks = _strip_trailing_blueprint([t for t in q.split(" ") if t])
    q_toks = discriminative(q_toks)
    c_toks = discriminative([t for t in norm.split(" ") if t])
    if not q_toks or not c_toks:
        return 0.0
    total = sum(_best_token_ratio(ct, q_toks) for ct in c_toks)
    return total / len(c_toks)


def rank_candidates(query, index, n=5):
    """Score every candidate by BOTH the whole-string ratio and the token-overlap
    score, taking the max as `score` and recording which metric won as `metric`.

    Debug-only: this does not touch the resolve hot path. Returns the top-`n`
    candidates as `[{"norm", "ducats", "score", "metric"}, ...]` sorted best-first.
    An empty (post-normalize) query returns `[]`.
    """
    q = normalize(query)
    if not q:
        return []

    ranked = []
    for it in index:
        r_whole = _ratio(q, it["norm"])
        r_token = _token_score(q, it["norm"])
        if r_token > r_whole:
            score, metric = r_token, "token"
        else:
            score, metric = r_whole, "whole"
        ranked.append({
            "norm": it["norm"],
            "ducats": it["ducats"],
            "score": score,
            "metric": metric,
        })
    ranked.sort(key=lambda c: c["score"], reverse=True)
    return ranked[:n]


def build_index(lookup):
    """Build the candidate list resolve_one/resolve_by_tokens scan over, from
    the normalized {name: ducats} dict ocr_scanner._load_lookup() returns."""
    return [{"norm": k, "ducats": v} for k, v in lookup.items()]
