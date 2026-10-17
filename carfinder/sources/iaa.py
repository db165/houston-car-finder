## iaa (insurance auto auctions): the search page posts json and gets back html rows

import json
import re

from bs4 import BeautifulSoup

from ..fetch import Blocked
from .copart import wantedModel

home = "https://www.iaai.com"
iaaDamage = {"FRONT END": ["Front End", "Left Front", "Right Front"],
             "MINOR DENT/SCRATCHES": ["Normal Wear & Tear"],
             "NORMAL WEAR": ["Normal Wear & Tear"]}
saleRe = re.compile(r"\b(Mon|Tue|Wed|Thu|Fri|Sat|Sun) (Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec) (\d{1,2}), (\d{1,2}:\d{2}[ap]m) ([A-Z]{3})")


def searchBody(cfg, page=1):
    damages = sorted({d for k in cfg["damage"] for d in iaaDamage.get(k, [])})
    searches = [
        {"Facets": [{"Group": "Make", "Value": m.title()} for m in cfg["makes"]], "FullSearch": None, "LongRanges": None},
        {"Facets": [{"Group": "PrimaryDamageDesc", "Value": d} for d in damages], "FullSearch": None, "LongRanges": None},
    ]
    if cfg.get("cleanTitleOnly", True):
        searches.append({"Facets": [{"Group": "SaleDocument", "Value": "Clear"}], "FullSearch": None, "LongRanges": None})
    return {"Searches": searches, "ZipCode": cfg["center"]["zip"], "miles": cfg["radiusMiles"], "PageSize": 100,
            "CurrentPage": page, "Sort": [{"IsGeoSort": False, "SortField": "AuctionDateTime", "IsDescending": False}],
            "ShowRecommendations": False, "SaleStatusFilters": [{"SaleStatus": 1, "IsSelected": True}],
            "BidStatusFilters": [{"BidStatus": 6, "IsSelected": True}]}


def num(s):
    d = re.sub(r"[^\d]", "", s or "")
    return int(d) if d else None


def parseRows(html, cfg):
    soup = BeautifulSoup(html, "html.parser")
    lots = []
    for row in soup.select(".table-row"):
        text = row.get_text(" ", strip=True)
        if "Stock #" not in text:
            continue
        items = [i.get_text(" ", strip=True) for i in row.select(".data-list__item")]
        si = next((k for k, t in enumerate(items) if t.startswith("Stock #")), None)
        heading = row.select_one("h4") or row.select_one("a[href*=VehicleDetail]")
        link = row.select_one("a[href*=VehicleDetail]")
        if si is None or not heading or not link:
            continue
        name = heading.get_text(" ", strip=True)
        ym = re.match(r"(\d{4})\s+(\S+)\s+(.*)", name)
        if not ym:
            continue
        year, make, rest = int(ym.group(1)), ym.group(2), ym.group(3).strip()
        model = rest.split(" ")[0] if rest else ""
        if not wantedModel(make, rest, cfg):
            continue
        get = lambda k: items[k] if 0 <= k < len(items) else ""
        odo = next((t for t in items if re.match(r"^[\d,]+ mi\b", t)), "")
        cond = next((t for t in items if t in ("Run & Drive", "Starts", "Stationary")), "")
        bags = next((t for t in items if re.search(r"\b(Intact|Deployed)\b", t)), "")
        keys = next((t for t in items if t.startswith("Key")), "")
        cyl = next((num(t) for t in items if re.match(r"^\d+ Cyl$", t)), None)
        trans = next((t.lower() for t in items if t in ("Automatic", "Manual")), "")
        branch = next((t for t in items if re.search(r"\((Illinois|Wisconsin|Indiana)\)", t)), "")
        acv = re.search(r"ACV:\s*\$([\d,]+)", text)
        dist = re.search(r"(\d+)\s*mi away", text)
        # the date inside the item list is when iaa added the car; a second date, if any, is the auction
        listed = get(si + 6)
        sales = [" ".join(m) for m in saleRe.findall(text)]
        sales = [x for x in sales if x.replace(",", "") != listed.replace(",", "")]
        img = row.select_one("img[data-src]") or row.select_one("img")
        imgUrl = (img.get("data-src") or img.get("src") or "") if img else ""
        stock = num(get(si))
        vid = re.search(r"/VehicleDetail/(\d+)", link["href"])
        lots.append({
            "id": f"iaa:{stock}",
            "source": "iaa",
            "url": home + link["href"],
            "title": name,
            "year": year,
            "make": make.title(),
            "model": model.title(),
            "trim": rest[len(model):].strip(),
            "miles": num(odo.split(" mi")[0]) if odo else None,
            "odometerNote": odo,
            "damage": get(si + 3),
            "secondaryDamage": get(si + 4),
            "condition": cond,
            "titleType": get(si + 1),
            "titleDetail": get(si + 1),
            "airbags": bags,
            "keys": keys,
            "retailValue": num(acv.group(1)) if acv else None,
            "repairCost": None,
            "currentBid": None,
            "buyNow": num((re.search(r"Buy Now\s*\$([\d,]+)", text) or [None, ""])[1]),
            "saleDate": sales[-1] if sales else "TBD",
            "listedDate": listed,
            "yard": branch,
            "distance": int(dist.group(1)) if dist else None,
            "transmission": trans,
            "cylinders": cyl,
            "photos": [imgUrl] if imgUrl.startswith("http") else [],
            "stock": stock,
            "itemId": vid.group(1) if vid else None,
            "publicOk": "Public" in text,
            "crDamages": [],
        })
    return lots


def photoUrls(itemId, n=6):
    return [f"https://vis.iaai.com/resizer?imageKeys={itemId}~SID~I{i}&width=800&height=600" for i in range(1, n + 1)]


def crawl(fetcher, cfg, log, maxPages=3):
    fetcher.get(home + "/Search")
    headers = {"Content-Type": "application/json; charset=utf-8", "X-Requested-With": "XMLHttpRequest",
               "Accept": "*/*", "Origin": home, "Referer": home + "/Search"}
    lots = {}
    for page in range(1, maxPages + 1):
        r = fetcher.session.post(home + "/Search", data=json.dumps(searchBody(cfg, page)), headers=headers, timeout=60)
        fetcher.requestCount += 1
        if r.status_code in (403, 406, 429) or "_Incapsula_Resource" in r.text[:3000]:
            raise Blocked(f"{r.status_code} from iaa search")
        if "table-row" not in r.text:
            raise ValueError("iaa returned no results table (layout changed or challenge page)")
        rows = parseRows(r.text, cfg)
        for lot in rows:
            if lot["distance"] is None or lot["distance"] <= cfg["radiusMiles"]:
                # image keys use the vehicle detail id, not the stock number
                lot["photos"] = photoUrls(lot["itemId"]) if lot["itemId"] else lot["photos"]
                lots[lot["id"]] = lot
        if r.text.count("Stock #") < 90:
            break
    log(f"iaa: {len(lots)} lots in range")
    return list(lots.values())
