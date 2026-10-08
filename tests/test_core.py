## offline tests: fake pages shaped like the real ones, no network

import json
import yaml
from pathlib import Path

from carfinder.listing import Listing, matchModel, countModelMentions
from carfinder.sources import craigslist, cargurus
from carfinder import filters, pricing, reliability, vision

cfg = yaml.safe_load((Path(__file__).parent.parent / "config.yml").read_text())

searchHtml = """
<ol><li class="cl-static-search-result" title="2012 Toyota Corolla LE one owner">
<a href="https://houston.craigslist.org/cto/d/houston-2012-toyota-corolla-le/7891234567.html">
<div class="title">2012 Toyota Corolla LE one owner</div><div class="details">
<div class="price">$5,400</div><div class="location">Bellaire</div></div></a></li>
<li class="cl-static-search-result" title="Check Honda CRV SUV InHouse Finance Bad / No Credit">
<a href="https://www.craigslist.org/view/d/houston-check-honda-crv-suv-inhouse/uRJYq5LAjgr">
<div class="title">x</div><div class="details"><div class="price">$2,000</div></div></a></li></ol>"""

detailHtml = """
<span id="titletextonly">2012 Toyota Corolla LE one owner</span>
<div id="map" data-latitude="29.70" data-longitude="-95.46"></div>
<div class="attrgroup"><div class="attr important"><span class="valu year">2012</span>
<span class="valu makemodel"><a href="#">toyota corolla le</a></span></div></div>
<div class="attrgroup">
<div class="attr auto_cylinders"><span class="labl">cylinders:</span><span class="valu"><a>4 cylinders</a></span></div>
<div class="attr auto_drivetrain"><span class="labl">drive:</span><span class="valu"><a>fwd</a></span></div>
<div class="attr auto_miles"><span class="labl">odometer:</span><span class="valu">158,200</span></div>
<div class="attr auto_title_status"><span class="labl">title status:</span><span class="valu"><a>clean</a></span></div>
<div class="attr auto_vin"><span class="labl">VIN:</span><span class="valu">2t1bu4ee5cc123456</span></div>
</div>
<section id="postingbody"><div class="print-information">QR Code Link to This Post</div>
Runs great, cold AC, no leaks, never flooded. Paint is clean.</section>
<script id="ld_posting_data" type="application/ld+json">{"image":["https://images.craigslist.org/a_600x450.jpg","https://images.craigslist.org/b_600x450.jpg"]}</script>
"""


def remixPage(tiles):
    ctx = {"state": {"loaderData": {"root": {}, "routes/($intl).Cars.$seoPath": {"search": {"tiles": tiles}}}}}
    return "<script>window.__remixContext = " + json.dumps(ctx) + ";</script>"


def cgTile(i, year, miles, price, imv, engine="2L I4", drive="Front-Wheel Drive", mpg=30):
    return {"type": "LISTING_USED_STANDARD", "data": {
        "id": i, "listingTitle": f"{year} Toyota Corolla", "priceData": {"current": price, "expected": imv},
        "imvPrice": imv, "mileageData": {"value": miles}, "dealRating": "GOOD_PRICE", "distance": 8.2,
        "ontologyData": {"makeName": "Toyota", "modelName": "Corolla", "carYear": year, "trimName": "LE"},
        "localizedEngineName": engine, "localizedDrivetrain": drive, "fuelData": {"combinedEconomy": mpg},
        "vin": "X", "sellerData": {"city": "Houston"}, "pictureData": {"url": "https://static.cargurus.com/p.jpg"}}}


def test_craigslist_search_and_detail():
    rows = craigslist.parseSearch(searchHtml)
    assert len(rows) == 2 and rows[0][3] == 5400 and rows[0][0] == "7891234567"
    d = craigslist.parseDetail(detailHtml)
    assert d["year"] == 2012 and d["attrs"]["auto_miles"] == "158,200"
    assert len(d["photos"]) == 2 and "QR Code" not in d["body"]
    lst = craigslist.buildListing(*rows[0], d, cfg, "houston")
    assert lst.model == "Corolla" and lst.miles == 158200 and lst.cylinders == 4 and lst.vin.startswith("2T1")
    reject, warn = filters.evaluate(lst, cfg)
    assert reject == [] and not any("flood" in w for w in warn)   # "never flooded" is not a flag


def test_finance_spam_rejected():
    rows = craigslist.parseSearch(searchHtml)
    lst = Listing(id="cl:x", source="craigslist", url=rows[1][1], title=rows[1][2], price=rows[1][3],
                  make="Honda", model="CR-V", year=2012, miles=120000)
    reject, _ = filters.evaluate(lst, cfg)
    assert "finance/down-payment ad" in reject


def test_model_matching():
    assert matchModel("2011 Honda CRV EX AWD", cfg["models"])["model"] == "CR-V"
    assert matchModel("Toyota Camry or Corolla", cfg["models"]) is None
    assert countModelMentions("tacoma camry corolla civic accord", cfg["models"]) >= 3


def test_tacoma_mpg_rule():
    base = dict(id="x", source="craigslist", url="u", title="2012 tacoma", price=5900, make="Toyota",
                model="Tacoma", year=2012, miles=160000)
    v6 = Listing(**base, cylinders=6, drive="rwd")
    i4 = Listing(**base, cylinders=4, drive="rwd")
    assert any("mpg" in r for r in filters.evaluate(v6, cfg)[0])
    assert not filters.evaluate(i4, cfg)[0]


def test_mechanical_reject_and_negation():
    l = Listing(id="x", source="craigslist", url="u", title="2013 civic mechanic special", price=3000,
                make="Honda", model="Civic", year=2013, miles=150000)
    assert "needs real mechanical work" in filters.evaluate(l, cfg)[0]
    l2 = Listing(id="y", source="craigslist", url="u", title="2013 civic", price=4500, make="Honda",
                 model="Civic", year=2013, miles=150000, description="no dents, no leaks, no check engine light")
    assert filters.evaluate(l2, cfg)[1] == []


def test_cargurus_extract_and_pricing():
    tiles = [cgTile(i, 2010 + i % 8, 90000 + (i * 7919) % 80000, 0, 0) for i in range(30)]
    # synthetic market: value drops ~9%/yr older and ~4%/10k miles
    for t in tiles:
        d = t["data"]
        v = 9000 * (1.09 ** (d["ontologyData"]["carYear"] - 2015)) * (0.96 ** ((d["mileageData"]["value"] - 120000) / 10000))
        d["imvPrice"] = round(v)
        d["priceData"]["current"] = round(v * 1.02)
    data = cargurus.extractTiles(remixPage(tiles))
    lists = [cargurus.toListing(d, cfg["models"][5], "comp")[0] for d in data]
    assert lists[0].cylinders == 4 and lists[0].drive == "fwd" and lists[0].mpg == 30
    fit = pricing.fitModel([l.toDict() for l in lists])
    est = pricing.predict(fit, 2015, 120000)
    assert abs(est - 9000) / 9000 < 0.03

    priv = {"model": "Corolla", "source": "craigslist", "sellerType": "private", "year": 2015,
            "miles": 120000, "price": 6000}
    a = pricing.appraise(priv, {"Corolla": fit}, cfg)
    assert a["confidence"] == "high" and 0.20 < a["dealPct"] < 0.30  # 9000*0.92=8280 -> 27.5% under


def test_complaint_flag():
    cache = {"CR-V": {"counts": {"2010": 300, "2011": 900, "2012": 280, "2013": 250, "2014": 320}}}
    assert reliability.complaintFlag(cache, "CR-V", 2011) is not None
    assert reliability.complaintFlag(cache, "CR-V", 2013) is None


def test_vision_dealbreaker():
    assert vision.isDealbreaker({"paint": "poor", "photosUseful": True})
    assert not vision.isDealbreaker({"paint": "good", "body": "good", "rust": "none", "verdict": "looks good"})
    assert not vision.isDealbreaker({"error": "timeout"})
