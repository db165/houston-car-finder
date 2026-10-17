## copart + iaa lots near dad's shop: keep clean-title, drivable cars with a mild front hit

import re


def norm(s):
    return re.sub(r"[^A-Z0-9]", "", (s or "").upper())


def evaluate(lot, cfg):
    # returns (rejectReasons, warnFlags) using the salvage section of config.yml
    sc = cfg["copart"]
    reject, warn = [], []
    dmg = (lot.get("damage") or "").upper()
    sec = (lot.get("secondaryDamage") or "").upper()
    cond = (lot.get("condition") or "").upper()
    title = (lot.get("titleType") or "").upper()
    okPrimary = {d.upper() for d in sc["damage"]} | ({"LEFT FRONT", "RIGHT FRONT"} if "FRONT END" in sc["damage"] else set()) \
        | ({"NORMAL WEAR & TEAR"} if "MINOR DENT/SCRATCHES" in sc["damage"] else set())
    okSecondary = {d.upper() for d in sc["okSecondary"]} | {"", "NONE", "NORMAL WEAR & TEAR", "LEFT FRONT", "RIGHT FRONT"}

    if lot.get("year") and lot["year"] < sc["minYear"]:
        reject.append(f"older than {sc['minYear']}")
    key = norm(f"{lot.get('make')} {lot.get('model')}")
    maxMiles = next((v for k, v in (sc.get("maxMilesByModel") or {}).items() if key.startswith(norm(k))), sc["maxMiles"])
    if lot.get("miles") and lot["miles"] > maxMiles:
        reject.append(f"over {maxMiles:,} miles")
    if dmg not in okPrimary:
        reject.append(f"damage: {dmg.title() or 'unknown'}")
    if sec not in okSecondary:
        reject.append(f"secondary damage: {sec.title()}")
    # copart says "RUNS AND DRIVES"/"ENHANCED VEHICLES", iaa says "Run & Drive"
    drives = cond in {c.upper() for c in sc["conditions"]} or cond == "RUN & DRIVE"
    if not drives:
        reject.append(f"not verified to run and drive ({cond.title() or 'unknown'})")
    if sc.get("cleanTitleOnly", True) and title and not ("CLEAN" in title or title == "CLEAR"
                                                          or title.startswith("CERTIFICATE OF TITLE")):
        reject.append(f"title: {title.title()}")
    if not title:
        warn.append("title type not shown yet")
    if "DEPLOYED" in (lot.get("airbags") or "").upper():
        reject.append("airbags deployed")
    rv, rc = lot.get("retailValue") or 0, lot.get("repairCost") or 0
    if rv and rv > sc["maxRetailValue"]:
        reject.append(f"retail value ${rv:,} over ${sc['maxRetailValue']:,}")
    if rv > 0 and rc > 0 and rc / rv > sc["maxRepairRatio"]:
        reject.append(f"repair estimate is {rc / rv:.0%} of value")
    if lot.get("distance") is not None and lot["distance"] > sc["radiusMiles"]:
        reject.append(f"{lot['distance']} mi from the shop")
    if "MISSING" in (lot.get("keys") or "").upper() or (lot.get("keys") or "").upper() == "NO":
        warn.append("no keys")
    if lot.get("odometerNote") and any(w in lot["odometerNote"].upper() for w in ("NOT ACTUAL", "EXCEEDS", "INOPERABLE")):
        warn.append(f"odometer: {lot['odometerNote']}")
    return reject, warn


def repairRatio(lot):
    rv, rc = lot.get("retailValue") or 0, lot.get("repairCost") or 0
    return rc / rv if rv > 0 and rc > 0 else None
