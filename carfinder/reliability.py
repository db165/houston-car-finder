## model-year red flags: a short known-issues list plus nhtsa complaint counts

import time
import statistics
import requests

# well documented issues worth asking the seller about (model, firstYear, lastYear, note)
knownIssues = [
    ("Tacoma", 2005, 2010, "2005-10 Tacoma frame rust program: ask if the frame was inspected or replaced"),
    ("CR-V", 2007, 2011, "2007-11 CR-V door lock actuators and AC compressor failures: test every lock and the AC"),
    ("CR-V", 2010, 2011, "2010-11 CR-V oil consumption (Honda program): check oil level, ask about burning"),
    ("Accord", 2008, 2010, "2008-10 Accord 4-cyl oil consumption: check oil level"),
    ("Camry", 2007, 2009, "2007-09 Camry 2.4L oil consumption is common: check oil level, ask if piston/ring work was done"),
    ("Corolla", 2009, 2010, "2009-10 Corolla 1.8L oil consumption on some engines: check oil level"),
    ("Civic", 2006, 2009, "2006-09 Civic engine block cracks (coolant loss) and AC failures: check coolant level"),
    ("RAV4", 2006, 2009, "2006-09 RAV4 2.4L oil consumption: check oil level"),
    ("CR-V", 2012, 2014, "2012-14 CR-V VTC actuator rattle on cold start: listen at first start"),
    ("CR-V", 2015, 2016, "2015-16 CR-V idle vibration complaints: feel for shake at stoplights"),
    ("CR-V", 2017, 2018, "2017-18 CR-V 1.5T oil dilution: check dipstick for gas smell"),
    ("Accord", 2008, 2012, "2008-12 Accord V6 cylinder deactivation issues: prefer the 4-cyl"),
    ("Accord", 2013, 2015, "2013-15 Accord: some early CVT judder reports, check for smooth takeoff"),
    ("Camry", 2010, 2011, "2010-11 Camry 2.4L oil consumption: check oil level"),
    ("Civic", 2016, 2018, "2016-18 Civic 1.5T oil dilution and AC condenser failures"),
    ("RAV4", 2010, 2011, "2010-11 RAV4 2.4L oil consumption on some engines: check oil level"),
]

nhtsaUrl = "https://api.nhtsa.gov/complaints/complaintsByVehicle"
nhtsaNames = {"CR-V": "cr-v", "RAV4": "rav4"}


def knownFlags(model, year):
    return [note for (m, a, b, note) in knownIssues if m == model and year and a <= year <= b]


def refreshComplaints(cache, cfg, log, maxAgeDays=7):
    # cache: {"Tacoma": {"fetched": ts, "counts": {"2012": 120, ...}}}
    now = time.time()
    for m in cfg["models"]:
        entry = cache.get(m["model"])
        if entry and now - entry.get("fetched", 0) < maxAgeDays * 86400:
            continue
        counts = {}
        for year in range(cfg["minYear"], time.gmtime().tm_year):
            try:
                r = requests.get(nhtsaUrl, timeout=30, params={
                    "make": m["make"].lower(), "model": nhtsaNames.get(m["model"], m["model"].lower()),
                    "modelYear": year})
                counts[str(year)] = r.json().get("count", 0)
            except Exception:
                counts[str(year)] = None
            time.sleep(0.3)
        cache[m["model"]] = {"fetched": now, "counts": counts}
        log(f"nhtsa {m['model']}: refreshed")
    return cache


def complaintFlag(cache, model, year, ratio=2.0):
    # flag a year whose complaint count is >2x the median of neighbouring years
    counts = (cache.get(model) or {}).get("counts", {})
    here = counts.get(str(year))
    if not here:
        return None
    near = [v for y, v in counts.items() if v and y != str(year) and abs(int(y) - year) <= 3]
    if len(near) < 3:
        return None
    med = statistics.median(near)
    if med and here > ratio * med:
        return f"{year} {model} has {here} NHTSA complaints, {here / med:.1f}x nearby years"
    return None
