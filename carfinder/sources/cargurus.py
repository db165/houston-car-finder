## cargurus: every search page ships its results as json inside window.__remixContext

import json
from urllib.parse import urlencode

from ..listing import Listing

marker = "window.__remixContext = "


def searchUrl(m, area, cfg, maxPrice, sortType="PRICE"):
    params = {
        "zip": area["zip"],
        "distance": area["radiusMiles"],
        "maxPrice": maxPrice,
        "startYear": cfg["minYear"],
        "maxMileage": cfg["maxMiles"],
        "sortType": sortType,
        "sortDirection": "ASC",
    }
    slug = f"l-Used-{m['make']}-{m['model'].replace(' ', '-')}-{m['cargurus'].split('/')[-1]}"
    return f"https://www.cargurus.com/Cars/{slug}?" + urlencode(params)


def extractTiles(html):
    i = html.find(marker)
    if i < 0:
        raise ValueError("cargurus page layout changed: no remix context")
    data, _ = json.JSONDecoder().raw_decode(html[i + len(marker):])
    loaders = data["state"]["loaderData"]
    for v in loaders.values():
        if isinstance(v, dict) and isinstance(v.get("search"), dict):
            return [t["data"] for t in v["search"].get("tiles", [])
                    if str(t.get("type", "")).startswith("LISTING") and "data" in t]
    raise ValueError("cargurus page layout changed: no search block")


def engineCylinders(name):
    # "2.7L I4" -> 4, "3.5L V6" -> 6
    import re
    hit = re.search(r"[IV](\d+)", name or "")
    return int(hit.group(1)) if hit else None


def driveCode(text):
    t = (text or "").lower()
    if "four" in t or "4wd" in t or "all" in t or "awd" in t:
        return "4wd"
    if "rear" in t:
        return "rwd"
    if "front" in t:
        return "fwd"
    return ""


def toListing(d, m, region):
    onto = d.get("ontologyData") or {}
    price = (d.get("priceData") or {}).get("current")
    seller = d.get("sellerData") or {}
    fuel = d.get("fuelData") or {}
    pic = (d.get("pictureData") or {}).get("url")
    imv = d.get("imvPrice") or (d.get("priceData") or {}).get("expected")
    return Listing(
        id=f"cg:{d['id']}",
        source="cargurus",
        url=f"https://www.cargurus.com/details/{d['id']}",
        title=d.get("listingTitle") or f"{onto.get('carYear')} {m['make']} {m['model']}",
        price=int(price) if price else None,
        make=m["make"],
        model=m["model"],
        year=onto.get("carYear"),
        miles=(d.get("mileageData") or {}).get("value"),
        trim=onto.get("trimName") or "",
        sellerType="dealer",
        titleStatus="clean",
        cylinders=engineCylinders(d.get("localizedEngineName")),
        drive=driveCode(d.get("localizedDrivetrain")),
        mpg=fuel.get("combinedEconomy"),
        vin=d.get("vin") or "",
        city=seller.get("city") or "",
        region=region,
        photos=[pic] if pic else [],
        marketValue=float(imv) if imv else None,
        siteRating=d.get("dealRating") or "",
        daysOnMarket=d.get("daysOnMarket"),
    ), d.get("distance")


def crawl(fetcher, cfg, region, area, maxPrice, log):
    out = []
    for m in cfg["models"]:
        tiles = extractTiles(fetcher.get(searchUrl(m, area, cfg, maxPrice)).text)
        for d in tiles:
            try:
                lst, dist = toListing(d, m, region)
            except (KeyError, TypeError, ValueError):
                continue
            # cargurus mixes in delivery cars from far away; keep our radius honest
            if dist is not None and dist > area["radiusMiles"] + 5:
                continue
            out.append(lst)
    uniq = {l.id: l for l in out}
    log(f"cargurus {region}: {len(uniq)} listings")
    return list(uniq.values())


def crawlComps(fetcher, cfg, area, log, maxPrice=14000):
    # wider price window just to learn what each model/year/mileage is worth
    out = []
    for m in cfg["models"]:
        try:
            tiles = extractTiles(fetcher.get(searchUrl(m, area, cfg, maxPrice, "BEST_MATCH")).text)
        except ValueError as e:
            log(f"comps {m['model']}: {e}")
            continue
        for d in tiles:
            try:
                lst, _ = toListing(d, m, "comp")
                out.append(lst)
            except (KeyError, TypeError, ValueError):
                continue
    log(f"cargurus comps: {len(out)}")
    return out
