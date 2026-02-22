import random
import re

def roman_planet_name(handle: str, existing_names=None, seed=None):
    if existing_names is None:
        existing_names = set()

    if seed is not None:
        random.seed(seed)

    # ----------------------------
    # Remove clan prefix
    # ----------------------------
    base = handle.strip()

    if "_" in base:
        parts = base.split("_", 1)
        if parts[0].isupper() and 2 <= len(parts[0]) <= 5:
            base = parts[1]
    else:
        def clean_non_alpha(s: str):
            return re.sub(r'[^A-Za-z]', '', s)
        def split_at_capitals(s: str):
            return re.findall(r'[A-Z][a-z]+', s)
        def has_both_cases(s: str) -> bool:
            return any(c.isupper() for c in s) and any(c.islower() for c in s)

        base = clean_non_alpha(base)
        if not base:
            return None

        if has_both_cases(base):
            parts = split_at_capitals(base)
            if len(parts) > 1:
                parts = parts[0], ''.join(parts[1:])
                if len(parts[0]) < len(parts[1]):
                    base = parts[1]

    base = base.capitalize()

    # ----------------------------
    # Latinization & declension assignment
    # ----------------------------

    def latinize(name):
        if name.endswith("a"):
            return name[:-1], "1st"
        elif name.endswith(("us", "er", "or")):
            return name.rstrip("us"), "2nd"
        elif name.endswith("o"):
            return name[:-1], "2nd"
        elif name.endswith("is"):
            return name[:-2], "3rd"
        else:
            return name, random.choice(["2nd", "3rd"])

    stem, decl = latinize(base)

    if decl == "1st":
        nominative = stem + "a"
        genitive = stem + "ae"
        adj_base = stem

    elif decl == "2nd":
        nominative = stem + "us"
        genitive = stem + "i"
        adj_base = stem

    else:  # 3rd decl
        nominative = stem
        genitive = stem + "is"
        adj_base = stem

    # ----------------------------
    # Adjective agreement
    # ----------------------------

    def adj_masc():
        return adj_base + "ianus"

    def adj_fem():
        return adj_base + "iana"

    def adj_neut():
        return adj_base + "ianum"

    # ----------------------------
    # Naming patterns
    # ----------------------------

    patterns = [
        lambda: adj_base + "ia",                     # Territory
        lambda: adj_neut(),                          # Estate
        lambda: "Colonia " + adj_fem(),              # Feminine agreement
        lambda: "Forum " + genitive,                 # Correct genitive
        lambda: "Municipium " + adj_neut(),          # Neuter agreement
    ]

    name = random.choice(patterns)()

    # ----------------------------
    # Uniqueness resolution
    # ----------------------------

    if name not in existing_names:
        return name

    ordinals = [
        "Secunda", "Tertia", "Quarta",
        "Quinta", "Sexta", "Septima",
        "Octava", "Nona", "Decima"
    ]

    variants = (
            ["Nova " + name] +
            [name + " Minor", name + " Maior"] +
            [name + " " + o for o in ordinals]
    )

    for v in variants:
        if v not in existing_names:
            return v

    i = 2
    while True:
        candidate = f"{name} {to_roman(i)}"
        if candidate not in existing_names:
            return candidate
        i += 1


def to_roman(num):
    vals = [
        (1000,"M"),(900,"CM"),(500,"D"),(400,"CD"),
        (100,"C"),(90,"XC"),(50,"L"),(40,"XL"),
        (10,"X"),(9,"IX"),(5,"V"),(4,"IV"),(1,"I")
    ]
    result = ""
    for v,s in vals:
        while num >= v:
            result += s
            num -= v
    return result
