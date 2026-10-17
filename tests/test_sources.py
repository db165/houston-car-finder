## offline tests for the pi sources, ranger rules and the auction filter

import json
import yaml
from pathlib import Path

from carfinder.listing import Listing, transmissionOf, matchModel
from carfinder.sources import autolist, offerup, copart, iaa
from carfinder import filters, salvage

cfg = yaml.safe_load((Path(__file__).parent.parent / "config.yml").read_text())
ranger = next(m for m in cfg["models"] if m["model"] == "Ranger")


def rangerListing(**kw):
    base = dict(id="x", source="craigslist", url="u", title="2006 ford ranger xl", price=5500, make="Ford",
                model="Ranger", year=2006, miles=120000, cylinders=4, drive="rwd", transmission="manual")
    base.update(kw)
    return Listing(**base)


def test_ranger_rules():
    assert filters.evaluate(rangerListing(), cfg)[0] == []
    assert "automatic transmission (manual only)" in filters.evaluate(rangerListing(transmission="automatic"), cfg)[0]
    assert "transmission not stated (manual only)" in filters.evaluate(rangerListing(transmission=""), cfg)[0]
    assert "over 145,000 miles" in filters.evaluate(rangerListing(miles=150000), cfg)[0]
    assert "newer than 2008" in filters.evaluate(rangerListing(year=2010), cfg)[0]
    assert filters.evaluate(rangerListing(year=2001), cfg)[0] == []   # ranger floor is 1998, not the global 2005
    assert any("mpg" in r for r in filters.evaluate(rangerListing(cylinders=6), cfg)[0])


def test_ranger_matching_and_transmission_text():
    assert matchModel("2004 Polaris Ranger 500", cfg["models"]) is None
    assert matchModel("2004 Ford Ranger Edge", cfg["models"])["model"] == "Ranger"
    assert transmissionOf("clean truck, 5 speed manual, cold ac") == "manual"
    assert transmissionOf("automatic") == "automatic"


def test_autolist_record():
    r = {"vin": "1FTYR10D16PA00000", "year": 2006, "make_name": "Ford", "model_name": "Ranger", "trim": "XL",
         "price": 6900, "mileage": 126514, "transmission": "manual", "engine_cylinders": 4, "driveline": "RWD",
         "combined_mpg": 23.7, "lat": 29.7, "lon": -95.4, "city": "Houston", "is_salvage": False,
         "imv_expected_price": 7400, "imv_deal_rating": "GOOD_PRICE", "photo_urls": ["https://x/a.jpg"]}
    l = autolist.toListing(r, ranger, "houston")
    assert l.transmission == "manual" and l.marketValue == 7400 and l.url.endswith("#vin=1FTYR10D16PA00000")
    assert filters.evaluate(l, cfg)[0] == []


def test_offerup_parse():
    search = {"props": {"x": [{"__typename": "ModularFeedListing", "listingId": "abc", "price": "5200",
                               "title": "2007 Ford Ranger", "vehicleMiles": 128}]}}
    html = '<script id="__NEXT_DATA__" type="application/json">' + json.dumps(search) + "</script>"
    tiles = offerup.parseSearch(html)
    assert "abc" in tiles
    detail = {"a": {"__typename": "Listing", "description": "5 speed, runs great", "title": "2007 Ford Ranger",
                    "price": "5200", "locationDetails": {"latitude": "29.75", "longitude": "-95.36", "locationName": "Houston, TX"},
                    "photos": [{"detailFull": {"url": "https://img/1.jpg"}}],
                    "vehicleAttributes": {"vehicleYear": "2007", "vehicleMiles": "128000", "vehicleTitleStatus": "clean",
                                          "vehicleTransmission": "Manual", "vehicleBody": "2-Door 2.3 4-Cylinder 5-Speed Manual",
                                          "vehicleDriveTrain": "Rear-Wheel Drive", "vehicleEpaCity": "21", "vehicleEpaHighway": "26"}}}
    det = offerup.parseDetail('<script id="__NEXT_DATA__">' + json.dumps(detail) + "</script>")
    l = offerup.buildListing("abc", tiles["abc"], det, ranger, "houston")
    assert l.cylinders == 4 and l.transmission == "manual" and l.drive == "rwd" and l.miles == 128000
    assert filters.evaluate(l, cfg)[0] == []
    assert offerup.tileMiles(205) == 205000


sc = cfg["copart"]


def copartRaw(**kw):
    c = {"ln": "123", "ld": "2017 TOYOTA RAV4 LE", "lcy": 2017, "mkn": "TOYOTA", "lm": "RAV4", "lmg": "RAV4",
         "orr": 98000, "ord": "ACTUAL", "dd": "FRONT END", "sdd": "", "lcd": "RUNS AND DRIVES",
         "tgd": "CLEAN TITLE", "td": "CERTIFICATE OF TITLE", "hk": "YES", "la": 16000, "rc": 4200, "hb": 0,
         "ad": 1792684800000, "yn": "IL - WHEELING", "lat": 42.13, "long": -87.92, "tmtp": "AUTOMATIC", "cy": "4",
         "tims": "https://cs.copart.com/t.jpg", "dynamicLotDetails": {"currentBid": 350}}
    c.update(kw)
    return c


def test_copart_lot_and_filter():
    assert copart.wantedModel("HONDA", "CRV", sc) and copart.wantedModel("MAZDA", "3", sc)
    assert copart.wantedModel("LEXUS", "RX350", sc) and not copart.wantedModel("TOYOTA", "SIENNA", sc)
    lot = copart.toLot(copartRaw(), sc)
    assert lot["distance"] < 10 and lot["currentBid"] == 350
    assert salvage.evaluate(lot, cfg)[0] == []
    bad = copart.toLot(copartRaw(dd="SIDE", lcd="ENGINE START PROGRAM", tgd="SALVAGE TITLE", rc=12000), sc)
    reasons = salvage.evaluate(bad, cfg)[0]
    assert any(r.startswith("damage") for r in reasons) and any("run and drive" in r for r in reasons)
    assert any(r.startswith("title") for r in reasons) and any("repair estimate" in r for r in reasons)
    body = copart.searchBody(sc)
    assert body["filter"]["TITL"] == ["title_group_code:TITLEGROUP_C"]


iaaRow = """<div class="table-row table-row-border"><div class="table-row-inner">
<div class="table-cell"><h4><a href="/VehicleDetail/45964662~US">2018 TOYOTA RAV4 LIMITED</a></h4><span>14 mi away</span></div>
<ul>
<li class="data-list__item">Stock #: 45466525</li><li class="data-list__item">Clear</li><li class="data-list__item"></li>
<li class="data-list__item">Front End</li><li class="data-list__item"></li><li class="data-list__item">Collision</li>
<li class="data-list__item">Thu Oct 15, 1:28am CDT</li><li class="data-list__item">SUVs</li><li class="data-list__item"></li>
<li class="data-list__item">67,120 mi</li><li class="data-list__item">Run &amp; Drive</li><li class="data-list__item">Intact</li>
<li class="data-list__item">Key Available</li><li class="data-list__item">Silver</li><li class="data-list__item"></li>
<li class="data-list__item">2.5L I-4 DOHC, VVT, 176HP</li><li class="data-list__item">Gasoline</li><li class="data-list__item">4 Cyl</li>
<li class="data-list__item">VIN: 2T3DFREV1JW******</li><li class="data-list__item">Automatic</li>
<li class="data-list__item">Chicago-North (Illinois)</li><li class="data-list__item">ACV: $22,590 USD</li>
</ul><span>Mon Oct 19, 8:30am CDT</span>
<img data-src="https://vis.iaai.com/resizer?imageKeys=45964662~SID~I1"></div></div>"""


def test_iaa_rows():
    lots = iaa.parseRows(iaaRow, sc)
    assert len(lots) == 1
    l = lots[0]
    assert l["titleType"] == "Clear" and l["damage"] == "Front End" and l["condition"] == "Run & Drive"
    assert l["miles"] == 67120 and l["retailValue"] == 22590 and l["distance"] == 14 and l["cylinders"] == 4
    assert l["saleDate"] == "Mon Oct 19 8:30am CDT" and l["listedDate"].startswith("Thu Oct 15")
    assert l["itemId"] == "45964662"
    reasons = salvage.evaluate(l, cfg)[0]
    assert reasons == [f"retail value $22,590 over ${sc['maxRetailValue']:,}"] or reasons == []
    deployed = dict(l, airbags="Deployed")
    assert "airbags deployed" in salvage.evaluate(deployed, cfg)[0]


def test_rav4_auction_miles_and_tacoma_years():
    lot = copart.toLot(copartRaw(orr=155000), sc)
    assert salvage.evaluate(lot, cfg)[0] == []                     # rav4 allowed to 160k
    assert "over 160,000 miles" in salvage.evaluate(copart.toLot(copartRaw(orr=165000), sc), cfg)[0]
    civic = copart.toLot(copartRaw(mkn="HONDA", lm="CIVIC", lmg="CIVIC", orr=155000), sc)
    assert "over 150,000 miles" in salvage.evaluate(civic, cfg)[0]
    taco = Listing(id="t", source="craigslist", url="u", title="2009 toyota tacoma", price=7000, make="Toyota",
                   model="Tacoma", year=2009, miles=150000, cylinders=4, drive="rwd")
    assert "older than 2011" in filters.evaluate(taco, cfg)[0]


def test_offerup_tile_only():
    t = {"listingId": "z", "title": "2012 Honda CR-V EX", "price": "5800", "vehicleMiles": 141,
         "locationName": "Houston, TX", "image": {"url": "https://img/z.jpg"}}
    crv = next(m for m in cfg["models"] if m["model"] == "CR-V")
    l = offerup.buildListing("z", t, offerup.tileDetail(t), crv, "houston")
    assert l.year == 2012 and l.miles == 141000 and l.price == 5800 and l.photos == ["https://img/z.jpg"]
    assert filters.evaluate(l, cfg)[0] == []
