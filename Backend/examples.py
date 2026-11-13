"""Few-shot example bank for the GeoMind query interpreter.

Each request gets the anchor examples plus the examples most similar to the user's question
(see select_examples). Add new examples at the bottom of EXAMPLES, then run:  python examples.py
"""
import math
import re
from collections import namedtuple

DEFAULT_NEAR_M = 1500   # default for "near" / "around" / "close to"; used by the prompt rules too


# ----------------------------------------------------------------------------
# Tiny builders, so every example has the same shape as the GISQuery schema
# ----------------------------------------------------------------------------
def F(column, operator, value):
    return {"column": column, "operator": operator, "value": value}


def NAME(value):
    return F("name", "ilike", value)


def cat(*values):
    """fclass filter: one value -> '=', several -> 'in'."""
    return F("fclass", "=", values[0]) if len(values) == 1 else F("fclass", "in", list(values))

def here(meters=DEFAULT_NEAR_M, negate=False):
    """Within a distance of the point the user clicked on the map."""
    return S("within_distance", "point", [], meters, negate)

def S(operation, layer, filters, distance=None, negate=False):
    return {
        "operation": operation,
        "reference_layer": layer,
        "distance_m": distance,
        "reference_filters": filters,
        "negate": negate,
    }


def inside(name, layer="place", negate=False, district=None):
    """Features located inside a named boundary. layer='place' lets the backend search all boundary layers."""
    filters = [NAME(name)]
    if district:
        filters.append(F("district", "ilike", district))
    return S("intersects", layer, filters, negate=negate)


def near(landmark, meters=DEFAULT_NEAR_M, layer="poi", negate=False):
    """Within a distance of something found by NAME (a landmark, or a town/city when layer says so)."""
    return S("within_distance", layer, [NAME(landmark)], meters, negate)


def near_cat(*values, meters=DEFAULT_NEAR_M, layer="poi", negate=False):
    """Within a distance of ANY feature of a category (e.g. any hospital)."""
    return S("within_distance", layer, [cat(*values)], meters, negate)


def Q(target, filters=None, spatial=None, limit=None):
    return {
        "target_layer": target,
        "filters": filters or [],
        "spatial": spatial or [],
        "limit": limit,
        "requires_clarification": False,
        "clarification_message": None,
    }


def ASK(message):
    return {
        "target_layer": None,
        "filters": [],
        "spatial": [],
        "limit": None,
        "requires_clarification": True,
        "clarification_message": message,
    }


Example = namedtuple("Example", "question query anchor")


def ex(question, query, anchor=False):
    return Example(question, query, anchor)


# ----------------------------------------------------------------------------
# THE EXAMPLE BANK
# ----------------------------------------------------------------------------
EXAMPLES = [
    # ---- anchors: always included in every prompt --------------------------
    ex("Show all hospitals", Q("poi", [cat("hospital")]), anchor=True),
    ex("Find schools in Kalamassery", Q("poi", [cat("school")], [inside("Kalamassery")]), anchor=True),
    ex("Restaurants near cusat", Q("poi", [cat("restaurant")], [near("cusat")]), anchor=True),
    ex("Find schools near hospital",
       ASK(f"Which hospital do you mean? Or I can search near all hospitals using a {DEFAULT_NEAR_M / 1000:g} km buffer."),
       anchor=True),

    # ---- category + bare place name (backend searches towns/city/districts/state) ----
    ex("Medical stores in Vaikom", Q("poi", [cat("pharmacy", "chemist")], [inside("Vaikom")])),
    ex("Banks in Angamaly", Q("poi", [cat("bank")], [inside("Angamaly")])),
    ex("Where can I find ATMs in Pala?", Q("poi", [cat("atm")], [inside("Pala")])),
    ex("List all police stations in Muvattupuzha", Q("poi", [cat("police")], [inside("Muvattupuzha")])),
    ex("Hotels in Munnar", Q("poi", [cat("hotel")], [inside("Munnar")])),
    ex("Places to stay in Munnar", Q("poi", [cat("hotel", "guesthouse", "hostel")], [inside("Munnar")])),
    ex("Show me cafes in Alappuzha", Q("poi", [cat("cafe")], [inside("Alappuzha")])),
    ex("hosptals in vaikom", Q("poi", [cat("hospital")], [inside("Vaikom")])),
    ex("Colleges in Thrissur", Q("poi", [cat("college")], [inside("Thrissur")])),
    ex("Doctors in Kayamkulam", Q("poi", [cat("doctors", "clinic")], [inside("Kayamkulam")])),
    ex("How many schools are there in Aluva?", Q("poi", [cat("school")], [inside("Aluva")])),
    ex("Eateries in Changanassery", Q("poi", [cat("restaurant", "cafe", "fast_food")], [inside("Changanassery")])),
    ex("Supermarkets in Perumbavoor", Q("poi", [cat("supermarket")], [inside("Perumbavoor")])),
    ex("Parks in Kochi", Q("poi", [cat("park")], [inside("Kochi")])),
    ex("Libraries in Kottayam", Q("poi", [cat("library")], [inside("Kottayam")])),
    ex("Post offices in Thodupuzha", Q("poi", [cat("post_office")], [inside("Thodupuzha")])),
    ex("Top 10 restaurants in Kochi", Q("poi", [cat("restaurant")], [inside("Kochi")], limit=10)),
    ex("Give me the first 50 pharmacies in Ernakulam", Q("poi", [cat("pharmacy")], [inside("Ernakulam")], limit=50)),
    ex("Show the first 100 banks", Q("poi", [cat("bank")], limit=100)),

    # ---- the user NAMES the boundary type: use that layer directly ----------
    ex("Hospitals in Kochi city", Q("poi", [cat("hospital")], [inside("Kochi", "city")])),
    ex("Supermarkets in Kochi corporation", Q("poi", [cat("supermarket")], [inside("Kochi", "city")])),
    ex("Banks in Muvattupuzha municipality", Q("poi", [cat("bank")], [inside("Muvattupuzha", "city")])),
    ex("Restaurants in Aluva town", Q("poi", [cat("restaurant")], [inside("Aluva", "towns")])),
    ex("Show all ATMs and banks in Ernakulam district", Q("poi", [cat("atm", "bank")], [inside("Ernakulam", "districts")])),
    ex("Schools in Kottayam district", Q("poi", [cat("school")], [inside("Kottayam", "districts")])),
    ex("Pharmacies in Vaikom town, Kottayam district",
       Q("poi", [cat("pharmacy", "chemist")], [inside("Vaikom", "towns", district="Kottayam")])),
    ex("Universities in Kerala state", Q("poi", [cat("university")], [inside("Kerala", "state")])),

    # ---- negation ------------------------------------------------------------
    ex("Banks that are not in Thrissur", Q("poi", [cat("bank")], [inside("Thrissur", negate=True)])),
    ex("Schools outside Kochi city", Q("poi", [cat("school")], [inside("Kochi", "city", negate=True)])),
    ex("Hotels not in Munnar town", Q("poi", [cat("hotel")], [inside("Munnar", "towns", negate=True)])),

    # ---- proximity to a named landmark --------------------------------------
    ex("Find pharmacies within 500 meters of Aster Medcity", Q("poi", [cat("pharmacy")], [near("Aster Medcity", 500)])),
    ex("ATMs near Lulu Mall", Q("poi", [cat("atm")], [near("Lulu Mall")])),
    ex("Cafes within 2 km of infopark", Q("poi", [cat("cafe")], [near("infopark", 2000)])),
    ex("Restaurants close to Lisie Hospital", Q("poi", [cat("restaurant")], [near("Lisie Hospital")])),
    ex("Hotels around Kochi airport", Q("poi", [cat("hotel")], [near("Kochi airport")])),
    ex("Find banks within half a kilometer of the railway station", Q("poi", [cat("bank")], [near("railway station", 500)])),

    # ---- proximity to a CATEGORY (any hospital, any primary road) ----------
    ex("Schools within 1 km of a hospital", Q("poi", [cat("school")], [near_cat("hospital", meters=1000)])),
    ex("Schools near any hospital", Q("poi", [cat("school")], [near_cat("hospital")])),
    ex("Find buildings within 300 meters of a hospital", Q("buildings", None, [near_cat("hospital", meters=300)])),
    ex("Schools that are not within 1 km of a primary road",
       Q("poi", [cat("school")], [near_cat("primary", layer="roads", meters=1000, negate=True)])),

    # ---- proximity to a boundary: ONLY when the user says town / city ------
    ex("Hospitals within 5 km of Vaikom town", Q("poi", [cat("hospital")], [near("Vaikom", 5000, layer="towns")])),
    ex("Pharmacies within 3 km of Kochi city", Q("poi", [cat("pharmacy")], [near("Kochi", 3000, layer="city")])),

    # ---- buildings -----------------------------------------------------------
    ex("Show all temples in Thrissur", Q("buildings", [F("type", "ilike", "temple")], [inside("Thrissur")])),
    ex("Mosques in Kozhikode", Q("buildings", [F("type", "ilike", "mosque")], [inside("Kozhikode")])),
    ex("Churches in Kottayam", Q("buildings", [F("type", "ilike", "church")], [inside("Kottayam")])),
    ex("Buildings in Kalamassery", Q("buildings", None, [inside("Kalamassery")])),

    # ---- boundaries themselves -----------------------------------------------
    ex("Show all towns in Ernakulam district", Q("towns", [F("district", "ilike", "Ernakulam")])),
    ex("List the towns of Kottayam", Q("towns", [F("district", "ilike", "Kottayam")])),
    ex("Show all towns in Kerala", Q("towns", [F("state", "ilike", "Kerala")])),
    ex("Show all districts in Kerala", Q("districts", None, [inside("Kerala", "state")])),
    ex("Show the boundary of Kalamassery", Q("place", [NAME("Kalamassery")])),
    ex("Show Idukki district", Q("districts", [NAME("Idukki")])),
    ex("Show Kochi city boundary", Q("city", [NAME("Kochi")])),
    ex("Show Aluva town", Q("towns", [NAME("Aluva")])),
    ex("Show the state boundary", Q("state")),
    ex("Which district is Vaikom in?", Q("towns", [NAME("Vaikom")])),

    # ---- roads -----------------------------------------------------------------
    ex("Show NH-66 road segments", Q("roads", [F("ref", "ilike", "NH-66")])),
    ex("Primary roads with bridges in Ernakulam district",
       Q("roads", [F("fclass", "ilike", "primary"), F("bridge", "=", "T")], [inside("Ernakulam", "districts")])),
    ex("Show tunnel roads", Q("roads", [F("tunnel", "=", "T")])),
    ex("Secondary roads in Kottayam", Q("roads", [F("fclass", "=", "secondary")], [inside("Kottayam")])),
    ex("Bridges in Alappuzha", Q("roads", [F("bridge", "=", "T")], [inside("Alappuzha")])),
    ex("Show MG Road", Q("roads", [NAME("MG Road")])),
    ex("Highways in Thrissur", Q("roads", [cat("motorway", "trunk")], [inside("Thrissur")])),
    ex("Show NH-544 in Thrissur district", Q("roads", [F("ref", "ilike", "NH-544")], [inside("Thrissur", "districts")])),

    # ---- cannot be answered from map data: ask instead of guessing ----------
    ex("What is the population of Kochi?",
       ASK("I don't have population data. I can search places, buildings, roads and boundaries, for example 'hospitals in Kochi'.")),
    ex("Hospitals near me",
       ASK("I don't know your location. Name a place or landmark, or use 'Select on map' and click the spot.")),
    ex("Show me something interesting",
       ASK("What would you like to see? For example: 'schools in Aluva' or 'roads with bridges in Kottayam'.")),
    ex("Route from Aluva to Kochi",
       ASK("I can't plan routes. I can show roads or places, for example 'primary roads in Ernakulam district'.")),
    ex("Compare Kochi and Thrissur",
       ASK("I can show one search at a time. Try 'hospitals in Kochi', then 'hospitals in Thrissur'.")),
]
POINT_EXAMPLES = [
    ex("Schools near the selected location", Q("poi", [cat("school")], [here()]), anchor=True),
    ex("Hospitals within 2 km of this location", Q("poi", [cat("hospital")], [here(2000)]), anchor=True),
    ex("Banks in this town", Q("poi", [cat("bank")], [S("intersects", "towns", [])]), anchor=True),
    ex("restaurants", Q("poi", [cat("restaurant")], [here()])),
    ex("ATMs nearby", Q("poi", [cat("atm")], [here()])),
    ex("Pharmacies within 500 m", Q("poi", [cat("pharmacy")], [here(500)])),
    ex("Medical stores here", Q("poi", [cat("pharmacy", "chemist")], [here()])),
    ex("Cafes and restaurants within 1 km of this spot", Q("poi", [cat("cafe", "restaurant")], [here(1000)])),
    ex("Buildings within 300 meters of this location", Q("buildings", None, [here(300)])),
    ex("Roads near here", Q("roads", None, [here()])),
    ex("Show hotels in this district", Q("poi", [cat("hotel")], [S("intersects", "districts", [])])),
    ex("Schools in this city", Q("poi", [cat("school")], [S("intersects", "city", [])])),
    ex("Which district is this?", Q("districts", None, [S("intersects", "point", [])])),
    ex("Which town is this location in?", Q("towns", None, [S("intersects", "point", [])])),
    ex("Hospitals in Thrissur", Q("poi", [cat("hospital")], [inside("Thrissur")])),   # a named place wins
    ex("Show all hospitals", Q("poi", [cat("hospital")])),                            # "all" ignores the point
]


# ----------------------------------------------------------------------------
# Picking the examples that look most like the user's question
# ----------------------------------------------------------------------------
_WORD = re.compile(r"[a-z0-9]+")
_STOP = {
    "a", "an", "the", "me", "my", "show", "find", "list", "give", "get", "all", "any", "are", "is", "there",
    "what", "where", "can", "i", "to", "how", "many", "of", "and", "please", "that", "with", "have", "has",
}
_SYNONYMS = {  # normalize wording so "medical shop" matches the pharmacy examples
    "medical": "pharmacy", "chemist": "pharmacy", "drug": "pharmacy", "drugstore": "pharmacy",
    "eatery": "restaurant", "eat": "restaurant", "food": "restaurant",
    "lodging": "stay", "accommodation": "stay", "guesthouse": "stay", "hostel": "stay",
    "municipality": "city", "corporation": "city",
    "kilometer": "km", "kilometre": "km", "kilometers": "km", "kilometres": "km", "kms": "km",
    "meter": "m", "metre": "m", "meters": "m", "metres": "m",
    "around": "near", "close": "near", "nearby": "near",
    "outside": "not", "without": "not", "far": "not",
}


def _tokens(text):
    out = set()
    for w in _WORD.findall(text.lower()):
        if w in _STOP:
            continue
        w = _SYNONYMS.get(w, w)
        if len(w) > 3 and w.endswith("s") and not w.endswith("ss"):
            w = w[:-1]                      # hospitals -> hospital
        out.add(_SYNONYMS.get(w, w))
    return out


ALL = EXAMPLES + POINT_EXAMPLES
_TOKENS = {e.question: _tokens(e.question) for e in ALL}
_DF = {}
for _t in _TOKENS.values():
    for _w in _t:
        _DF[_w] = _DF.get(_w, 0) + 1
_IDF = {w: math.log((len(ALL) + 1) / (n + 1)) + 1 for w, n in _DF.items()}


def select_examples(user_text, k=8, with_location=False):
    """Anchors first, then the k most similar examples (most similar LAST, closest to the real question)."""
    pool = ALL if with_location else EXAMPLES      # point examples only when a location is selected
    wanted = _tokens(user_text)
    scored = []
    for i, e in enumerate(pool):
        if e.anchor or e.question.strip().lower() == user_text.strip().lower():
            continue
        shared = wanted & _TOKENS[e.question]
        if shared:
            score = sum(_IDF[w] for w in shared) / math.sqrt(len(_TOKENS[e.question]) or 1)
            scored.append((score, i))
    top = [i for _, i in sorted(scored, reverse=True)[:k]]
    anchors = [e for e in pool if e.anchor]
    return anchors + [pool[i] for i in reversed(top)]


# ----------------------------------------------------------------------------
# Self-check:  python examples.py
# ----------------------------------------------------------------------------
if __name__ == "__main__":
    from schemas import GISQuery

    seen, problems = set(), 0
    for e in ALL:
        key = e.question.strip().lower()
        if key in seen:
            print("DUPLICATE QUESTION:", e.question)
            problems += 1
        seen.add(key)
        try:
            GISQuery(**e.query)
        except Exception as err:
            print("INVALID:", e.question, "->", err)
            problems += 1
    print(f"{len(ALL)} examples checked, {problems} problem(s)")
    print("\nSample selection for 'pharmacies in piravom':")
    for e in select_examples("pharmacies in piravom"):
        print("  -", e.question)
