## craigslist: search page for ids/prices, listing page for year/miles/title/vin

import json
import re
from urllib.parse import urlencode
from bs4 import BeautifulSoup

from ..listing import Listing, parseInt, matchModel
from ..fetch import Blocked

siteHosts = {"houston": "houston", "austin": "austin"}

dealerCues = re.compile(r"\b(dealer(ship)?|stock ?(#|no|number)|we finance|financing available|"
                        r"warranty available|trade[- ]ins? (welcome|accepted)|tx dealer|dealer fees?)\b", re.I)


def searchUrl(region, area, cfg, word, maxPrice):
    params = {
        "query": word,
        "postal": area["zip"],
        "search_distance": area["radiusMiles"],
        "min_auto_year": cfg["minYear"],
        "max_auto_miles": cfg["maxMiles"],
        "auto_title_status": 1,          # clean title only
        "min_price": cfg["budget"]["minPrice"],
        "max_price": maxPrice,
    }
    return f"https://{siteHosts[region]}.craigslist.org/search/cta?" + urlencode(params)


def parseSearch(html):
    # returns [(postId, url, title, price)]
    soup = BeautifulSoup(html, "html.parser")
    out = []
    for li in soup.select("li.cl-static-search-result"):
        a = li.find("a")
        if not a or not a.get("href"):
            continue
        url = a["href"]
        title = li.get("title") or li.select_one(".title").get_text(strip=True)
        priceEl = li.select_one(".price")
        price = parseInt(priceEl.get_text()) if priceEl else None
        postId = url.rstrip("/").split("/")[-1].replace(".html", "")
        out.append((postId, url, title, price))
    return out


def parseDetail(html):
    soup = BeautifulSoup(html, "html.parser")
    d = {"attrs": {}}
    for div in soup.select(".attrgroup .attr"):
        classes = [c for c in div.get("class", []) if c not in ("attr", "important")]
        valu = div.select_one(".valu")
        if not valu:
            continue
        if "important" in div.get("class", []):
            yr = div.select_one(".valu.year")
            mm = div.select_one(".valu.makemodel")
            if yr:
                d["year"] = parseInt(yr.get_text())
            if mm:
                d["makemodel"] = mm.get_text(" ", strip=True)
            continue
        if classes:
            d["attrs"][classes[0]] = valu.get_text(" ", strip=True).lower()

    body = soup.select_one("#postingbody")
    if body:
        for junk in body.select(".print-information, .print-qrcode-container"):
            junk.decompose()
        d["body"] = body.get_text(" ", strip=True).replace("QR Code Link to This Post", "").strip()

    mapEl = soup.select_one("#map")
    if mapEl and mapEl.get("data-latitude"):
        d["lat"] = float(mapEl["data-latitude"])
        d["lon"] = float(mapEl["data-longitude"])

    # photos: structured data first, then gallery links
    photos = []
    ld = soup.select_one("#ld_posting_data")
    if ld:
        try:
            img = json.loads(ld.get_text()).get("image") or []
            photos = img if isinstance(img, list) else [img]
        except ValueError:
            pass
    if not photos:
        photos = [a["href"] for a in soup.select("a[href*='images.craigslist.org']")]
    if not photos:
        photos = [i["src"] for i in soup.select("img[src*='images.craigslist.org']")]
    d["photos"] = list(dict.fromkeys(photos))[:12]

    titleEl = soup.select_one("#titletextonly")
    if titleEl:
        d["title"] = titleEl.get_text(strip=True)
    return d


def buildListing(postId, url, title, price, detail, cfg, region):
    attrs = detail.get("attrs", {})
    text = " ".join([title, detail.get("makemodel", "")])
    m = matchModel(text, cfg["models"])
    cyl = parseInt(attrs.get("auto_cylinders"))
    return Listing(
        id="cl:" + postId,
        source="craigslist",
        url=url,
        title=title,
        price=price,
        make=m["make"] if m else None,
        model=m["model"] if m else None,
        year=detail.get("year"),
        miles=parseInt(attrs.get("auto_miles")),
        trim=detail.get("makemodel", ""),
        sellerType="dealer" if "/ctd/" in url or dealerCues.search(title + " " + detail.get("body", "")) else "private",
        titleStatus=attrs.get("auto_title_status", ""),
        cylinders=cyl,
        drive=attrs.get("auto_drivetrain", ""),
        vin=(attrs.get("auto_vin") or "").upper(),
        lat=detail.get("lat"),
        lon=detail.get("lon"),
        region=region,
        description=detail.get("body", "")[:3000],
        photos=detail.get("photos", []),
    )


def crawl(fetcher, cfg, region, area, maxPrice, known, log):
    # known: {id: price} already stored; only open listing pages for new or repriced ads
    seen, out = {}, []
    for m in cfg["models"]:
        word = m["words"][0]
        html = fetcher.get(searchUrl(region, area, cfg, word, maxPrice)).text
        for row in parseSearch(html):
            seen.setdefault(row[0], row)
    log(f"craigslist {region}: {len(seen)} search hits")

    budgetLeft = cfg["crawl"]["maxDetailFetchesPerRun"]
    unchanged = []
    # cheapest first so in-budget cars get opened before comps-only ones
    for postId, (pid, url, title, price) in sorted(seen.items(), key=lambda kv: kv[1][3] or 10 ** 9):
        lid = "cl:" + postId
        if lid in known and known[lid] == price:
            unchanged.append(lid)
            continue
        if budgetLeft <= 0:
            continue
        budgetLeft -= 1
        try:
            detail = parseDetail(fetcher.get(url).text)
        except Blocked:
            raise
        except Exception as e:
            log(f"  skip {url}: {e}")
            continue
        out.append(buildListing(postId, url, detail.get("title", title), price, detail, cfg, region))
    return out, unchanged
