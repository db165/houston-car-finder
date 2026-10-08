## hard rules (reject) and soft flags (warn) for every listing

import re
from .listing import countModelMentions, milesBetween

# ads that aren't really a cash price
financePatterns = [
    r"\bdown\s*payment", r"\$\s*\d[\d,]*\s*down\b", r"\bbad credit\b", r"\bno credit\b",
    r"\bin[- ]?house financ", r"\bbuy here\b", r"\bbhph\b", r"\bitin\b", r"\bweekly payments?\b",
    r"\bfinancing available\b.*\bapprov", r"\beveryone (is )?approved\b", r"\bguaranteed approval\b",
]

# "little to no work" means these are dealbreakers
mechanicalReject = [
    r"\bmechanic'?s? special\b", r"\bnot running\b", r"\bdoes(n'?t| not) run\b", r"\bwon'?t start\b",
    r"\bneeds (an? )?(engine|motor|transmission|tranny)\b", r"\bblown (head ?gasket|engine|motor)\b",
    r"\btransmission (slip|problem|issue)s?\b", r"\bparts (car|only)\b", r"\bas[- ]is,? needs\b",
    r"\bproject car\b", r"\bengine knock", r"\bthrow?n rod\b",
]

titleReject = [r"\bsalvage\b", r"\brebuilt\b", r"\breconstructed\b", r"\bbranded title\b",
               r"\blemon\b", r"\bbill of sale only\b", r"\bno title\b", r"\blost title\b"]

floodWarn = [r"\bflood", r"\bwater damage", r"\bharvey\b", r"\bberyl\b", r"\bsubmerged\b",
             r"\bwater (got )?in(side)?\b"]

mechanicalWarn = [r"\bcheck engine\b", r"\bcel\b", r"\bneeds (some )?work\b", r"\bminor issues?\b",
                  r"\bac (doesn'?t|not) (work|blow)", r"\bneeds (ac|a/c)\b", r"\boverheat",
                  r"\bleak", r"\bnoise\b", r"\bslipping\b", r"\bneeds tires\b", r"\bairbag light\b"]

paintWarn = [r"\bfad(ed|ing) paint\b", r"\bclear ?coat\b", r"\bpeeling\b", r"\bhail\b",
             r"\bdents?\b", r"\bbody damage\b", r"\bscratches\b", r"\bdings?\b", r"\boxidi[sz]"]


negators = re.compile(r"\b(no|not|never|zero|without|free of|never had any|0)\b[\w\s,/]{0,14}$", re.I)


def anyMatch(patterns, text):
    # a hit only counts if it isn't "no leaks", "never flooded", "free of dents"...
    hits = []
    for p in patterns:
        for m in re.finditer(p, text, re.I):
            if not negators.search(text[max(0, m.start() - 24):m.start()]):
                hits.append(p)
                break
    return hits


def tacomaMpgOk(lst):
    # epa combined: 2005-15 only the 2.7 4-cyl 2wd hits 21; 4x4s and v6s are 17-19.
    # 2016+ everything but some 4x4 v6 trims is 20-21
    if lst.year and lst.year <= 2015:
        if lst.cylinders == 6 or lst.drive == "4wd":
            return False, None
        if lst.cylinders == 4 and lst.drive in ("fwd", "rwd", "2wd"):
            return True, None
        return True, "verify it's the 4-cyl 2wd (only Tacoma config that gets 20+ mpg)"
    if lst.cylinders == 6 and lst.drive == "4wd":
        return True, "v6 4x4 Tacoma is right at 20 mpg"
    return True, None


def evaluate(lst, cfg):
    # returns (rejectReasons, warnFlags)
    reject, warn = [], []
    text = f"{lst.title} {lst.description}".lower()
    budget = cfg["budget"]

    if not lst.model:
        reject.append("not a target model")
    if lst.price is None or lst.price < budget["minPrice"]:
        reject.append("price missing or too low to be real")
    elif lst.price > budget["stretchMax"]:
        reject.append("over stretch budget")
    if lst.year is None:
        warn.append("year not listed")
    elif lst.year < cfg["minYear"]:
        reject.append(f"older than {cfg['minYear']}")
    if lst.miles is None:
        warn.append("mileage not listed")
    elif lst.miles > cfg["maxMiles"]:
        reject.append(f"over {cfg['maxMiles']:,} miles")
    elif lst.miles < 1000 and lst.year and lst.year < 2020:
        warn.append("mileage looks like it's in thousands or fake")

    if lst.titleStatus and lst.titleStatus not in ("clean", ""):
        reject.append(f"title: {lst.titleStatus}")
    if anyMatch(titleReject, text):
        reject.append("branded title mentioned")
    if lst.source == "craigslist" and anyMatch(financePatterns, text):
        reject.append("finance/down-payment ad")
    if countModelMentions(lst.title, cfg["models"]) >= 3:
        reject.append("keyword-stuffed dealer spam")
    if anyMatch(mechanicalReject, text):
        reject.append("needs real mechanical work")

    if lst.model == "Tacoma":
        ok, note = tacomaMpgOk(lst)
        if not ok:
            reject.append("under 20 mpg (Tacoma v6 or 4x4)")
        elif note:
            warn.append(note)
    if lst.mpg is not None and lst.mpg < cfg["minMpg"]:
        reject.append(f"{lst.mpg:.0f} mpg")

    if anyMatch(floodWarn, text):
        warn.append("flood/water mentioned in ad")
    hits = anyMatch(mechanicalWarn, text)
    if hits:
        warn.append("possible mechanical issue in ad")
    if anyMatch(paintWarn, text):
        warn.append("paint/body issue mentioned in ad")

    return reject, warn


def distanceFromHome(lst, cfg):
    if lst.lat is None or lst.lon is None:
        return None
    return round(milesBetween(cfg["home"]["lat"], cfg["home"]["lon"], lst.lat, lst.lon), 1)
