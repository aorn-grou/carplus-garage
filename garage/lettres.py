"""Écrire un montant en toutes lettres (français), pour les factures : 2050000 -> « deux millions cinquante mille »."""

UNITES = ["zéro", "un", "deux", "trois", "quatre", "cinq", "six", "sept", "huit", "neuf", "dix", "onze", "douze",
          "treize", "quatorze", "quinze", "seize", "dix-sept", "dix-huit", "dix-neuf"]
DIZAINES = {2: "vingt", 3: "trente", 4: "quarante", 5: "cinquante", 6: "soixante"}


def _moins_de_100(n):
    if n < 20:
        return UNITES[n]
    d, u = divmod(n, 10)
    if d in (7, 9):                       # 70-79 : soixante-dix… ; 90-99 : quatre-vingt-dix…
        base = "soixante" if d == 7 else "quatre-vingt"
        if d == 7 and u == 1:
            return "soixante et onze"
        return f"{base}-{UNITES[10 + u]}"
    if d == 8:
        return "quatre-vingts" if u == 0 else f"quatre-vingt-{UNITES[u]}"
    if u == 0:
        return DIZAINES[d]
    if u == 1:
        return f"{DIZAINES[d]} et un"
    return f"{DIZAINES[d]}-{UNITES[u]}"


def _moins_de_1000(n, final=True):
    c, r = divmod(n, 100)
    if c == 0:
        return _moins_de_100(r)
    debut = "cent" if c == 1 else f"{UNITES[c]} cent"
    if r == 0:
        return debut + ("s" if c > 1 and final else "")
    return f"{debut} {_moins_de_100(r)}"


def en_lettres(n):
    n = int(n)
    if n == 0:
        return "zéro"
    if n < 0:
        return "moins " + en_lettres(-n)
    morceaux = []
    for valeur, sing, plur in ((10 ** 9, "milliard", "milliards"), (10 ** 6, "million", "millions")):
        q, n = divmod(n, valeur)
        if q:
            morceaux.append(f"{en_lettres(q)} {sing if q == 1 else plur}")
    q, n = divmod(n, 1000)
    if q:
        morceaux.append("mille" if q == 1 else f"{_moins_de_1000(q, final=False)} mille")
    if n:
        morceaux.append(_moins_de_1000(n))
    texte = " ".join(morceaux)
    # « quatre-vingts » et « cents » perdent leur s devant « mille »
    return texte.replace("quatre-vingts mille", "quatre-vingt mille")


def montant_en_lettres(n, devise="ariary"):
    t = en_lettres(n)
    return f"{t[0].upper()}{t[1:]} {devise}"
