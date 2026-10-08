## one-off: which listing sites answer requests from github's servers?

import json
import requests

ua = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36")
htmlHeaders = {"User-Agent": ua, "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
               "Accept-Language": "en-US,en;q=0.9"}
jsonHeaders = {"User-Agent": ua, "Accept": "application/json", "Accept-Language": "en-US,en;q=0.9"}
houston = json.dumps({"city": "Houston", "state": "TX", "zipCode": "77005", "longitude": -95.4018,
                      "latitude": 29.7174, "source": "manual"})

checks = [
    ("autolist", "https://www.autolist.com/api/v3/search?ads=false&search_engine=cgsp&latitude=29.7174&longitude=-95.4018"
                 "&limit=50&make_models[Honda][]=CR-V&makes[]=Honda&mileage_max=170000&page=1&price_max=15000&radius=50"
                 "&sort_filter=price:asc&year_min=2005", jsonHeaders, None, "records"),
    ("offerup", "https://offerup.com/search?q=honda%20crv", htmlHeaders, {"ou.location": houston}, "ModularFeedListing"),
    ("cars.com", "https://www.cars.com/shopping/results/?makes[]=honda&models[]=honda-cr_v&stock_type=used"
                 "&maximum_distance=50&zip=77005&list_price_max=7500&sort=list_price", htmlHeaders, None, "data-vehicle-array"),
    ("autotrader", "https://www.autotrader.com/cars-for-sale/used-cars/honda/cr-v/houston-tx?zip=77005&searchRadius=50"
                   "&maxPrice=7500", htmlHeaders, None, "listingId"),
    ("truecar", "https://www.truecar.com/used-cars-for-sale/listings/honda/cr-v/location-houston-tx/?priceHigh=7500",
     htmlHeaders, None, "__NEXT_DATA__"),
    ("edmunds", "https://www.edmunds.com/inventory/srp.html?make=honda&model=honda%7Ccr-v&zip=77005&radius=50"
                "&inventorytype=used", htmlHeaders, None, "vin"),
    ("cargurus", "https://www.cargurus.com/Cars/l-Used-Honda-CR-V-d589?zip=77005&distance=50", htmlHeaders, None,
     "__remixContext"),
    ("facebook", "https://www.facebook.com/marketplace/houston/vehicles?maxPrice=7500", htmlHeaders, None, "marketplace"),
]

for name, url, headers, cookies, marker in checks:
    try:
        r = requests.get(url, headers=headers, cookies=cookies, timeout=30)
        body = r.text
        extra = ""
        if name == "autolist" and r.ok:
            extra = f" total={r.json().get('total_count')}"
        if name == "offerup":
            extra = f" houstonTiles={body.count('Houston, TX')}"
        print(f"{name:11} status={r.status_code} bytes={len(body)} marker={'yes' if marker in body else 'no'}{extra}")
    except Exception as e:
        print(f"{name:11} error={e}")
