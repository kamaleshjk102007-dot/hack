"""
Quick classification smoke test — no external I/O required.
Run from the project root: python tests/test_query_analyzer_quick.py
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from brain.verification.query_analyzer import QueryAnalyzer

qa = QueryAnalyzer()


def check(label, query, want_verify, section):
    r = qa.analyze(query)
    ok = r.requires_verification == want_verify
    tag = "bypass" if not r.requires_verification else "VERIFY"
    status = "PASS" if ok else "FAIL"
    print(f"  {status} [{tag}] {query}")
    if not ok:
        print(f"         reason: {r.reason}")
    return ok


def run():
    results = {}

    print("=== SECTION 2: SELF-QUERY BYPASS (must NOT require verification) ===")
    self_cases = [
        "What is your capability?",
        "What are your capabilities?",
        "What can EDITH do?",
        "What is the capability of EDITH?",
        "Display current E.D.I.T.H. configuration.",
        "Show system settings.",
        "List security clearance levels.",
        "Tell me about your architecture.",
        "How does EDITH work?",
        "Check EDITH status.",
        "Show me your available tools.",
        "Explain your current configuration.",
        # Extra edge cases
        "What is your current configuration?",
        "Tell me about EDITH features.",
        "What features do you have?",
        "Describe your capabilities.",
    ]
    p = f = 0
    for q in self_cases:
        if check("self", q, False, "self"):
            p += 1
        else:
            f += 1
    results["Self-query bypass"] = (p, f)

    print()
    print("=== SECTION 3: EXTERNAL FACTUAL (must require verification) ===")
    factual_cases = [
        "What is the latest version of Python?",
        "What happened in the latest AI research?",
        "Who won the most recent major international tournament?",
        "Explain the current weather in Chennai.",
        "Find recent news about artificial intelligence.",
        # Regression: factual about a movie
        "Who directed Inception?",
        "What is the release date of Avengers Doomsday?",
        "Tell me about the Russo-Ukrainian war.",
    ]
    p = f = 0
    for q in factual_cases:
        if check("factual", q, True, "factual"):
            p += 1
        else:
            f += 1
    results["External factual"] = (p, f)

    print()
    print("=== SECTION 4: CODING / OPERATIONAL (must NOT require verification) ===")
    code_cases = [
        "Explain this Python error.",
        "Fix my code.",
        "Check whether the HUD server is running.",
        "Show the contents of a permitted project directory.",
        "Explain why my provider fallback failed.",
        # Extra coverage
        "Debug this traceback.",
        "Write a function to sort a list.",
        "Create a new Python project.",
        "Open the browser.",
        "Send an email to mom.",
    ]
    p = f = 0
    for q in code_cases:
        if check("code", q, False, "code"):
            p += 1
        else:
            f += 1
    results["Coding/operational"] = (p, f)

    print()
    print("=== SECTION 5: REGEX DIRECT TESTS ===")
    import re
    _sys = QueryAnalyzer._system_or_self

    regex_tests = [
        # (text, should_match, description)
        # Capability forms — scoped to EDITH context (bare word intentionally does NOT match)
        ("your capability",           True,  "'your capability' phrase"),
        ("your capabilities",         True,  "'your capabilities' phrase"),
        ("capability of EDITH",       True,  "'capability of EDITH' phrase"),
        ("capabilities of EDITH",     True,  "'capabilities of EDITH' phrase"),
        ("What can EDITH do",         True,  "'What can EDITH do'"),
        ("what can you do",           True,  "'what can you do'"),
        # Bare standalone words — intentionally NOT matched to avoid false positives
        # e.g. 'AI capability control proposals' from Wikipedia
        ("capability",                False, "bare 'capability' — must NOT match (false-positive guard)"),
        ("capabilities",              False, "bare 'capabilities' — must NOT match"),
        ("configuration",             False, "bare 'configuration' — must NOT match (e.g. 'network configuration')"),
        # EDITH-scoped config phrases DO match
        ("your configuration",        True,  "'your configuration' phrase"),
        ("your settings",             True,  "'your settings' phrase"),
        # Dotted E.D.I.T.H. forms
        ("E.D.I.T.H.",               True,  "standalone dotted form E.D.I.T.H."),
        ("Display E.D.I.T.H. configuration", True, "dotted form in sentence"),
        # Personal pronouns
        ("your",                      True,  "possessive 'your'"),
        ("yourself",                  True,  "reflexive 'yourself'"),
        # Plain EDITH
        ("edith",                     True,  "plain edith"),
        ("EDITH's",                   True,  "possessive EDITH's"),
        # Specific system phrases
        ("system settings",           True,  "system settings phrase"),
        ("security clearance",        True,  "security clearance phrase"),
        ("do you have",               True,  "'do you have' phrase"),
        ("what features do you",      True,  "'what features do you' phrase"),
    ]
    p = f = 0
    for text, want, desc in regex_tests:
        got = bool(_sys.search(text))
        ok = got == want
        status = "PASS" if ok else "FAIL"
        print(f"  {status} regex match={got} (want={want}): {desc!r} <- {text!r}")
        if ok:
            p += 1
        else:
            f += 1

    results["Regex unit"] = (p, f)

    # Summary
    print()
    print("=" * 60)
    total_p = total_f = 0
    for section, (p, f) in results.items():
        total_p += p
        total_f += f
        grade = "OK" if f == 0 else "FAILURES"
        print(f"  {grade:8s} {section}: {p} passed, {f} failed")
    print(f"  {'TOTAL':8s} {total_p} passed, {total_f} failed")
    print("=" * 60)
    return total_f == 0


if __name__ == "__main__":
    success = run()
    sys.exit(0 if success else 1)
