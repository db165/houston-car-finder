## copart: the site's own json search api, filtered to clean-title japanese cars with front/minor damage

import json
import re

from ..fetch import Blocked
from ..listing import milesBetween

home = "https://www.copart.com"
damageCodes = {"FRONT END": "DAMAGECODE_FR", "MINOR DENT/SCRATCHES": "DAMAGECODE_MN", "NORMAL WEAR": "DAMAGECODE_NW",
               "REAR END": "DAMAGECODE_RR", "SIDE": "DAMAGECODE_SD", "HAIL": "DAMAGECODE_HL"}


def norm(s):
    return re.sub(r"[^A-Z0-9]", "", (s or "").upper())


def wantedModel(make, model, cfg):
    key = norm(f"{make} {model}")
    return any(key.startswith(norm(p)) for p in cfg["models"])


def searchBody(cfg, start=0, size=100):
    f = {
        "LOC": [f'yard_name:"{y}"' for y in cfg["yards"]],
        "MAKE": [f'search_lot_make_desc:"{m}"' for m in cfg["makes"]],
        "PRID": [f"damage_type_code:{damageCodes[d]}" for d in cfg["damage"] if d in damageCodes],
        "YEAR": [f"lot_year:[{cfg['minYear']} TO 2100]"],
        "VEHT": ["vehicle_type_code:VEHTYPE_V"],
    }
    if cfg.get("cleanTitleOnly", True):
        f["TITL"] = ["title_group_code:TITLEGROUP_C"]
    return {"query": ["*"], "filter": f, "sort": ["auction_date_utc asc"], "page": start // size, "size": size,
            "start": start, "watchListOnly": False, "freeFormSearch": False, "hideImages": False,
            "defaultSort": False, "specificRowProvided": False, "displayName": "", "searchName": "",
            "backUrl": "", "includeTagByField": {}, "rawParams": {}}


def toLot(c, cfg):
    lat, lon = c.get("lat"), c.get("long")
    dist = None
    if lat and lon:
        dist = round(milesBetween(cfg["center"]["lat"], cfg["center"]["lon"], float(lat), float(lon)), 1)
    dyn = c.get("dynamicLotDetails") or {}
    return {
        "id": f"cp:{c['ln']}",
        "source": "copart",
        "url": f"{home}/lot/{c['ln']}",
        "title": c.get("ld") or f"{c.get('lcy')} {c.get('mkn')} {c.get('lm')}",
        "year": c.get("lcy"),
        "make": (c.get("mkn") or "").title(),
        "model": c.get("lm") or "",
        "trim": c.get("ltd") or "",
        "miles": int(c["orr"]) if c.get("orr") is not None else None,
        "odometerNote": c.get("ord") or "",
        "damage": c.get("dd") or "",
        "secondaryDamage": c.get("sdd") or "",
        "condition": c.get("lcd") or "",
        "titleType": c.get("tgd") or c.get("td") or "",
        "titleDetail": c.get("td") or "",
        "keys": c.get("hk") or "",
        "retailValue": int(c["la"]) if (c.get("la") or 0) > 0 else None,   # copart sends -1 when unknown
        "repairCost": int(c["rc"]) if (c.get("rc") or 0) > 0 else None,
        "currentBid": dyn.get("currentBid") if dyn.get("currentBid") is not None else c.get("hb"),
        "buyNow": c.get("bnp") or 0,
        "saleDate": c.get("ad"),
        "yard": c.get("yn") or "",
        "lat": lat, "lon": lon, "distance": dist,
        "transmission": (c.get("tmtp") or "").lower(),
        "cylinders": int(c["cy"]) if str(c.get("cy") or "").isdigit() else None,
        "engine": c.get("egn") or "",
        "drive": c.get("drv") or "",
        "photos": [c["tims"]] if c.get("tims") else [],
        "crDamages": [],
    }


def session(fetcher):
    # the home page hands out the xsrf cookie the search api wants back as a header
    fetcher.get(home + "/")
    token = fetcher.session.cookies.get("XSRF-TOKEN") or ""
    return {"Content-Type": "application/json", "Accept": "application/json, text/plain, */*",
            "X-Requested-With": "XMLHttpRequest", "X-XSRF-TOKEN": token,
            "Origin": home, "Referer": home + "/lotSearchResults"}


def fetchDetails(fetcher, lot, maxPhotos=6):
    n = lot["id"].split(":")[1]
    try:
        imgs = fetcher.get(f"{home}/public/data/lotdetails/solr/lotImages/{n}/USA",
                           headers={"Accept": "application/json"}).json()
        content = ((imgs.get("data") or {}).get("imagesList") or {}).get("content") or []
        lot["photos"] = [i.get("fullUrl") or i.get("highResUrl") for i in content if i.get("fullUrl") or i.get("highResUrl")][:maxPhotos] or lot["photos"]
        det = fetcher.get(f"{home}/public/data/lotdetails/solr/{n}", headers={"Accept": "application/json"}).json()
        ld = (det.get("data") or {}).get("lotDetails") or {}
        lot["crDamages"] = [f"{d.get('aasc_item_description')}: {d.get('aasc_damage_description')}"
                            for d in (ld.get("cr_damages") or [])][:12]
    except Blocked:
        raise
    except Exception:
        pass
    return lot


def crawl(fetcher, cfg, known, log, maxDetails=25):
    headers = session(fetcher)
    lots, start = {}, 0
    while True:
        r = fetcher.session.post(home + "/public/lots/search-results", data=json.dumps(searchBody(cfg, start)),
                                 headers=headers, timeout=30)
        fetcher.requestCount += 1
        if r.status_code in (403, 406, 429) or "json" not in r.headers.get("content-type", ""):
            raise Blocked(f"{r.status_code} from copart search")
        res = (r.json().get("data") or {}).get("results") or {}
        content = res.get("content") or []
        for c in content:
            if not wantedModel(c.get("mkn"), c.get("lmg") or c.get("lm"), cfg):
                continue
            lot = toLot(c, cfg)
            if lot["distance"] is not None and lot["distance"] > cfg["radiusMiles"]:
                continue
            lots[lot["id"]] = lot
        start += len(content)
        if not content or start >= (res.get("totalElements") or 0) or start >= 1000:
            break

    budget = maxDetails
    for lid, lot in lots.items():
        cached = known.get(lid)
        if cached:
            lot["photos"], lot["crDamages"] = cached["photos"], cached["crDamages"]
        elif budget > 0:
            budget -= 1
            fetchDetails(fetcher, lot)
            known[lid] = {"photos": lot["photos"], "crDamages": lot["crDamages"]}
    log(f"copart: {len(lots)} lots in range")
    return list(lots.values())
