## one car ad, same shape no matter which site it came from

import math
import re
from dataclasses import dataclass, field, asdict
from typing import Optional


@dataclass
class Listing:
    id: str                       # "cl:abc123" or "cg:458963612"
    source: str                   # craigslist | cargurus
    url: str
    title: str
    price: Optional[int]
    make: Optional[str] = None
    model: Optional[str] = None
    year: Optional[int] = None
    miles: Optional[int] = None
    trim: str = ""
    sellerType: str = "private"   # private | dealer
    titleStatus: str = ""         # clean, salvage, rebuilt...
    cylinders: Optional[int] = None
    drive: str = ""               # fwd, 4wd, rwd
    mpg: Optional[float] = None
    vin: str = ""
    lat: Optional[float] = None
    lon: Optional[float] = None
    city: str = ""
    region: str = "houston"       # houston | austin
    description: str = ""
    photos: list = field(default_factory=list)
    marketValue: Optional[float] = None   # site's own estimate (cargurus imv)
    siteRating: str = ""                  # cargurus deal rating
    daysOnMarket: Optional[int] = None

    def toDict(self):
        return asdict(self)


def milesBetween(lat1, lon1, lat2, lon2):
    # haversine, earth radius in miles
    r = 3958.8
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def parseInt(text):
    if text is None:
        return None
    digits = re.sub(r"[^\d]", "", str(text))
    return int(digits) if digits else None


def matchModel(text, models):
    # find which target model a free-text title is about; None if zero or several
    low = " " + (text or "").lower() + " "
    hits = []
    for m in models:
        for w in m["words"]:
            if re.search(r"(?<![a-z0-9])" + re.escape(w) + r"(?![a-z0-9])", low):
                hits.append(m)
                break
    return hits[0] if len(hits) == 1 else None


def countModelMentions(text, models):
    low = (text or "").lower()
    return sum(1 for m in models if any(w in low for w in m["words"]))
