## offerup: private sellers. search page json for the list, item page json for title/vin/transmission
# location comes from the ou.location cookie, so the pi can search houston from anywhere

import json
import re
from urllib.parse import quote

from ..listing import Listing, matchModel, parseInt, transmissionOf
from ..fetch import Blocked

nextData = re.compile(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', re.S)


def setLocation(fetcher, area):
    loc = {"city": area.get("city", "Houston"), "state": area.get("state", "TX"), "zipCode": area["zip"],
           "longitude": area["lon"], "latitude": area["lat"], "source": "manual"}
    fetcher.session.cookies.set("ou.location", quote(json.dumps(loc, separators=(",", ":"))), domain="offerup.com")


def walk(o, typename, out):
    if isinstance(o, dict):
        if o.get("__typename") == typename:
            out.append(o)
        for v in o.values():
            walk(v, typename, out)
    elif isinstance(o, list):
        for v in o:
            walk(v, typename, out)
    return out


def parseSearch(html):
    hit = nextData.search(html)
    if not hit:
        raise ValueError("offerup page layout changed: no __NEXT_DATA__")
    tiles = walk(json.loads(hit.group(1)), "ModularFeedListing", [])
    return {t["listingId"]: t for t in tiles if t.get("listingId")}


def parseDetail(html):
    hit = nextData.search(html)
    if not hit:
        return None
    found = [x for x in walk(json.loads(hit.group(1)), "Listing", []) if isinstance(x.get("description"), str)]
    if not found:
        return None
    d = found[0]
    va = d.get("vehicleAttributes") or {}
    loc = d.get("locationDetails") or {}
    photos = []
    for ph in d.get("photos") or []:
        u = ((ph.get("detailFull") or ph.get("detail") or {}).get("url"))
        if u:
            photos.append(u)
    return {
        "description": d.get("description") or "",
        "title": d.get("title") or "",
        "price": parseInt(d.get("price")),
        "year": parseInt(va.get("vehicleYear")),
        "miles": parseInt(va.get("vehicleMiles")),
        "titleStatus": (va.get("vehicleTitleStatus") or "").lower(),
        "transmission": va.get("vehicleTransmission") or "",
        "drive": va.get("vehicleDriveTrain") or "",
        "body": va.get("vehicleBody") or "",
        "vin": va.get("vehicleVin") or "",
        "epaCity": parseInt(va.get("vehicleEpaCity")),
        "epaHwy": parseInt(va.get("vehicleEpaHighway")),
        "lat": float(loc["latitude"]) if loc.get("latitude") else None,
        "lon": float(loc["longitude"]) if loc.get("longitude") else None,
        "city": loc.get("locationName") or "",
        "photos": photos[:12],
    }


def tileMiles(v):
    # sellers often type 205 meaning 205k
    if v is None:
        return None
    v = int(v)
    return v * 1000 if 0 < v < 1000 else v


def buildListing(lid, tile, det, m, region):
    body = det.get("body", "")
    cyl = re.search(r"(\d)-Cylinder", body)
    drive = det.get("drive", "").lower()
    mpg = None
    if det.get("epaCity") and det.get("epaHwy"):
        mpg = round(1 / (0.55 / det["epaCity"] + 0.45 / det["epaHwy"]), 1)
    return Listing(
        id=f"ou:{lid}",
        source="offerup",
        url=f"https://offerup.com/item/detail/{lid}",
        title=det.get("title") or tile.get("title") or "",
        price=det.get("price") or parseInt(tile.get("price")),
        make=m["make"],
        model=m["model"],
        year=det.get("year"),
        miles=tileMiles(det.get("miles") or tile.get("vehicleMiles")),
        sellerType="private",
        titleStatus=det.get("titleStatus", ""),
        cylinders=int(cyl.group(1)) if cyl else None,
        drive="4wd" if ("four" in drive or "all" in drive) else "rwd" if "rear" in drive else "fwd" if "front" in drive else "",
        transmission=transmissionOf(det.get("transmission")) or transmissionOf(det.get("title"), det.get("description")),
        mpg=mpg,
        vin=det.get("vin", ""),
        lat=det.get("lat"),
        lon=det.get("lon"),
        city=det.get("city", ""),
        region=region,
        description=det.get("description", "")[:3000],
        photos=det.get("photos", []),
    )


def crawl(fetcher, cfg, region, area, maxPrice, known, log, maxDetails=40):
    # known: {listingId: {"price": p, "detail": {...}}} cached on the pi so item pages are fetched once
    setLocation(fetcher, area)
    tiles = {}
    for m in cfg["models"]:
        for word in m["words"][:1]:
            q = f"{m['make']} {word}"
            html = fetcher.get(f"https://offerup.com/search?q={quote(q)}&PRICE_MAX={maxPrice}").text
            for lid, t in parseSearch(html).items():
                mm = matchModel(t.get("title", ""), [m])
                if mm:
                    tiles[lid] = (t, m)
    log(f"offerup {region}: {len(tiles)} matching tiles")

    out, budget, detailsBlocked = [], maxDetails, False
    for lid, (t, m) in tiles.items():
        price = parseInt(t.get("price"))
        if price and price > maxPrice:
            continue
        cached = known.get(lid)
        if (not cached or cached.get("price") != price) and budget > 0 and not detailsBlocked:
            budget -= 1
            try:
                det = parseDetail(fetcher.get(f"https://offerup.com/item/detail/{lid}").text)
                if det:
                    known[lid] = cached = {"price": price, "detail": det}
            except Blocked as e:
                # item pages refuse us; stop asking and keep what the search page showed
                detailsBlocked = True
                log(f"  offerup item pages blocked ({e}), using search results only")
            except Exception as e:
                log(f"  offerup detail {lid}: {e}")
        if cached and cached.get("detail"):
            out.append(buildListing(lid, t, cached["detail"], m, region))
        else:
            out.append(buildListing(lid, t, tileDetail(t), m, region))
    return out


def tileDetail(t):
    # just what the search tile shows; title status and transmission stay unknown
    title = t.get("title") or ""
    yr = re.search(r"\b(19[89]\d|20[0-3]\d)\b", title)
    img = t.get("image") or {}
    return {"title": title, "price": parseInt(t.get("price")), "year": int(yr.group(1)) if yr else None,
            "miles": parseInt(t.get("vehicleMiles")), "city": t.get("locationName") or "",
            "photos": [img["url"]] if isinstance(img, dict) and img.get("url") else [],
            "description": "OfferUp listing page not read: ask the seller about title status and transmission"}
