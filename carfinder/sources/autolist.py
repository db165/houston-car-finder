## autolist: json search api (dealer cars with accident/salvage history and a market value)

from urllib.parse import urlencode

from ..listing import Listing, transmissionOf

apiUrl = "https://www.autolist.com/api/v3/search"


def searchUrl(m, area, cfg, maxPrice):
    params = [
        ("ads", "false"), ("search_engine", "cgsp"), ("include_relative_price_difference", "true"),
        ("latitude", area["lat"]), ("longitude", area["lon"]), ("radius", area["radiusMiles"]),
        ("limit", 50), ("page", 1), ("sort_filter", "price:asc"),
        (f"make_models[{m['make']}][]", m["model"]), ("makes[]", m["make"]),
        ("price_max", maxPrice), ("year_min", m.get("minYear", cfg["minYear"])),
        ("mileage_max", m.get("maxMiles", cfg["maxMiles"])),
    ]
    if m.get("maxYear"):
        params.append(("year_max", m["maxYear"]))
    return apiUrl + "?" + urlencode(params)


def toListing(r, m, region):
    vin = r.get("vin") or ""
    photos = r.get("photo_urls") or ([r["primary_photo_url"]] if r.get("primary_photo_url") else [])
    bad = []
    if r.get("is_salvage"):
        bad.append("salvage")
    if r.get("has_frame_damage"):
        bad.append("frame damage")
    if r.get("is_buy_here_pay_here"):
        bad.append("buy here pay here")
    return Listing(
        id=f"al:{vin or r.get('id')}",
        source="autolist",
        url=f"https://www.autolist.com/listings#vin={vin}",
        title=f"{r.get('year')} {r.get('make_name')} {r.get('model_name')} {r.get('trim') or ''}".strip(),
        price=r.get("price"),
        make=m["make"],
        model=m["model"],
        year=r.get("year"),
        miles=r.get("mileage"),
        trim=r.get("trim") or "",
        sellerType="dealer",
        # anything other than "clean" gets rejected by filters.evaluate
        titleStatus="salvage" if r.get("is_salvage") else "frame damage reported" if r.get("has_frame_damage") else "clean",
        cylinders=r.get("engine_cylinders"),
        drive=(r.get("driveline") or "").lower().replace("4x4", "4wd").replace("awd", "4wd"),
        transmission=transmissionOf(r.get("transmission")),
        mpg=r.get("combined_mpg"),
        vin=vin,
        lat=r.get("lat"),
        lon=r.get("lon"),
        city=r.get("city") or "",
        region=region,
        description=("history: " + ", ".join(bad)) if bad else
                    f"{r.get('accident_count') or 0} accidents, {r.get('owner_count') or '?'} owners",
        photos=photos[:12],
        marketValue=r.get("imv_expected_price"),
        siteRating=r.get("imv_deal_rating") or "",
    )


def crawl(fetcher, cfg, region, area, maxPrice, log):
    out = {}
    for m in cfg["models"]:
        resp = fetcher.get(searchUrl(m, area, cfg, maxPrice), headers={"Accept": "application/json"})
        for r in resp.json().get("records", []):
            try:
                lst = toListing(r, m, region)
            except (KeyError, TypeError, ValueError):
                continue
            out[lst.id] = lst
    log(f"autolist {region}: {len(out)} listings")
    return list(out.values())
