"""Scores the interpreter against questions it has NOT seen as examples.

Run from the backend folder (Ollama and the database must be running):
    python eval_prompts.py

Add a line to TESTS whenever a real question goes wrong. Only the keys you list are checked.
"""
import json

import db
from ai_service import interpret

# (question, expected). Keys: target, fclass (set), refs (set of reference layers), negate, clarify, limit
TESTS = [
    ("schools in Edappally",                      {"target": "poi", "fclass": {"school"}, "refs": {"place"}}),
    ("medical shops in Piravom",                  {"target": "poi", "fclass": {"pharmacy", "chemist"}, "refs": {"place"}}),
    ("list banks in Kothamangalam",               {"target": "poi", "fclass": {"bank"}, "refs": {"place"}}),
    ("cafes in Wayanad district",                 {"target": "poi", "fclass": {"cafe"}, "refs": {"districts"}}),
    ("hospitals in Kannur city",                  {"target": "poi", "fclass": {"hospital"}, "refs": {"city"}}),
    ("restaurants in Chengannur town",            {"target": "poi", "fclass": {"restaurant"}, "refs": {"towns"}}),
    ("pharmacies in Pala town, Kottayam district", {"target": "poi", "fclass": {"pharmacy", "chemist"}, "refs": {"towns"}}),
    ("schools not in Kollam",                     {"target": "poi", "fclass": {"school"}, "refs": {"place"}, "negate": True}),
    ("banks near Technopark",                     {"target": "poi", "fclass": {"bank"}, "refs": {"poi"}}),
    ("atms within 300 m of Medical College",      {"target": "poi", "fclass": {"atm"}, "refs": {"poi"}}),
    ("colleges within 2 km of any hospital",      {"target": "poi", "fclass": {"college"}, "refs": {"poi"}}),
    ("show all towns in Palakkad district",       {"target": "towns", "refs": set()}),
    ("show the boundary of Angamaly",             {"target": "place", "refs": set()}),
    ("show Wayanad district",                     {"target": "districts", "refs": set()}),
    ("list all districts in Kerala",              {"target": "districts", "refs": {"state"}}),
    ("churches in Changanassery",                 {"target": "buildings", "refs": {"place"}}),
    ("roads with bridges in Kollam",              {"target": "roads", "refs": {"place"}}),
    ("show NH-66 in Kannur district",             {"target": "roads", "refs": {"districts"}}),
    ("top 20 hotels in Munnar",                   {"target": "poi", "fclass": {"hotel"}, "refs": {"place"}, "limit": 20}),
    ("how many hospitals are there in Aluva",     {"target": "poi", "fclass": {"hospital"}, "refs": {"place"}}),
    ("what is the population of Thrissur",        {"clarify": True}),
    ("find a route from Kochi to Kottayam",       {"clarify": True}),
    ("parks near hospital",                       {"clarify": True}),
]


def summarize(q):
    fclass = set()
    for f in q.filters:
        if f.column.lower() == "fclass":
            fclass |= set(f.value) if isinstance(f.value, list) else {str(f.value)}
    return {
        "target": q.target_layer,
        "fclass": fclass,
        "refs": {s.reference_layer for s in q.spatial},
        "negate": any(s.negate for s in q.spatial),
        "clarify": q.requires_clarification,
        "limit": q.limit,
    }


def main():
    db.init_pool()
    schema = db.load_schema_info()
    failures = 0
    for question, expected in TESTS:
        got = summarize(interpret(question, schema))
        wrong = {k: (v, got[k]) for k, v in expected.items() if got[k] != v}
        if wrong:
            failures += 1
            print(f"\nFAIL  {question}")
            for k, (want, have) in wrong.items():
                print(f"      {k}: expected {want!r}, got {have!r}")
        else:
            print(f"ok    {question}")
    total = len(TESTS)
    print(f"\n{total - failures}/{total} passed")
    db.close_pool()


if __name__ == "__main__":
    main()
