## one crawl cycle: fetch -> merge into history -> price -> filter -> photo check -> alert -> dashboard data

import argparse
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

import yaml

from .fetch import Fetcher, Blocked
from .sources import craigslist, cargurus
from . import filters, pricing, reliability, vision, notify

day = 86400


def log(msg):
    print(time.strftime("%H:%M:%S"), msg, flush=True)


def loadJson(path, default):
    try:
        return json.loads(Path(path).read_text())
    except (FileNotFoundError, ValueError):
        return default


def saveJson(path, obj):
    Path(path).write_text(json.dumps(obj, separators=(",", ":"), default=str))


## crawling

def crawlAll(cfg, fetcher, recs, meta):
    found, touched, status = [], [], {}
    known = {k: v["price"] for k, v in recs.items()}
    areas = [("houston", cfg["home"], cfg["budget"]["stretchMax"])]
    if cfg["austin"]["enabled"]:
        areas.append(("austin", cfg["austin"], cfg["austinRule"]["maxPrice"]))

    for region, area, maxPrice in areas:
        try:
            found += cargurus.crawl(fetcher, cfg, region, area, maxPrice, log)
            status[f"cargurus-{region}"] = "ok"
        except Blocked as e:
            status[f"cargurus-{region}"] = f"blocked: {e}"
            log(f"cargurus {region} blocked: {e}")
        except Exception as e:
            status[f"cargurus-{region}"] = f"error: {e}"[:200]
            log(f"cargurus {region} error: {e}")
        try:
            new, same = craigslist.crawl(fetcher, cfg, region, area, maxPrice, known, log)
            found += new
            touched += same
            status[f"craigslist-{region}"] = "ok"
        except Blocked as e:
            status[f"craigslist-{region}"] = f"blocked: {e}"
            log(f"craigslist {region} blocked: {e}")
        except Exception as e:
            status[f"craigslist-{region}"] = f"error: {e}"[:200]
            log(f"craigslist {region} error: {e}")
    return found, touched, status


def mergeListings(recs, found, touched, now):
    for lst in found:
        d = lst.toDict()
        old = recs.get(lst.id)
        if old:
            if old["price"] != d["price"] and d["price"]:
                old.setdefault("priceHistory", []).append([now, d["price"]])
            keep = {k: old[k] for k in ("firstSeen", "priceHistory", "alerted", "vision", "visionPhotos") if k in old}
            old.clear()
            old.update(d)
            old.update(keep)
        else:
            d.update(firstSeen=now, priceHistory=[[now, d["price"]]], alerted=[])
            recs[lst.id] = d
        recs[lst.id]["lastSeen"] = now
    for lid in touched:
        if lid in recs:
            recs[lid]["lastSeen"] = now


def updateComps(comps, listings, now, maxAgeDays=45):
    for l in listings:
        if l.source != "cargurus" or not l.model:
            continue
        comps.setdefault(l.model, {})[l.id] = {
            "year": l.year, "miles": l.miles, "price": l.price, "marketValue": l.marketValue, "ts": now}
    for model in comps:
        comps[model] = {k: v for k, v in comps[model].items() if now - v["ts"] < maxAgeDays * day}


## deciding what each car is

def classify(rec, cfg):
    b, dealCfg = cfg["budget"], cfg["deal"]
    a = rec["appraisal"]
    pct, conf = a.get("dealPct"), a.get("confidence")
    trusted = conf in ("high", "medium") and pct is not None
    priority = next((m["priority"] for m in cfg["models"] if m["model"] == rec.get("model")), 9)

    if rec["region"] == "austin":
        r = cfg["austinRule"]
        ok = (trusted and pct >= r["minPct"] and rec["price"] <= r["maxPrice"]
              and (rec.get("miles") or 10 ** 9) <= r["maxMiles"] and not rec["flags"])
        return "austin" if ok else "austin-skip"

    greatOnSite = rec.get("siteRating") in ("GREAT_PRICE",)
    if rec["price"] <= b["alertMax"]:
        if (trusted and pct >= dealCfg["alertPct"]) or (greatOnSite and pct is None):
            return "steal"
        return "budget"
    if trusted and priority == 1 and pct >= dealCfg["stretchAlertPct"]:
        return "stretch-deal"
    return "stretch"


def evaluateAll(recs, fits, nhtsa, cfg, now):
    for rec in recs.values():
        rec["active"] = now - rec["lastSeen"] < 2 * day
        if not rec["active"]:
            continue

        class L:  # filters expects attribute access
            pass
        obj = L()
        obj.__dict__.update(rec)
        reject, warn = filters.evaluate(obj, cfg)
        rec["distance"] = filters.distanceFromHome(obj, cfg)
        if rec["region"] == "houston" and rec["distance"] and rec["distance"] > cfg["home"]["radiusMiles"] + 5:
            reject.append("outside 50 miles")
        if rec.get("model") and rec.get("year"):
            warn += reliability.knownFlags(rec["model"], rec["year"])
            c = reliability.complaintFlag(nhtsa, rec["model"], rec["year"])
            if c:
                warn.append(c)
        if rec.get("vision") and vision.isDealbreaker(rec["vision"]):
            reject.append("photos: " + (rec["vision"].get("notes") or "looks rough"))
        rec["rejected"], rec["flags"] = reject, warn
        rec["appraisal"] = pricing.appraise(rec, fits, cfg) if rec.get("model") and rec.get("price") else \
            {"marketValue": None, "dealPct": None, "confidence": "none", "basis": ""}
        rec["tier"] = "rejected" if reject else classify(rec, cfg)
        if rec["tier"] == "austin-skip":
            rec["rejected"] = ["Austin, not worth the drive"]
            rec["tier"] = "rejected"


## photos + alerts

def visionPass(recs, cfg, meta):
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    if meta.get("visionDay") != today:
        meta["visionDay"], meta["visionCount"] = today, 0
    order = {"steal": 0, "austin": 0, "stretch-deal": 1, "budget": 2, "stretch": 3}
    queue = sorted((r for r in recs.values() if r.get("active") and r["tier"] in order
                    and r.get("photos") and r.get("visionPhotos") != r["photos"][:4]),
                   key=lambda r: order[r["tier"]])
    for rec in queue:
        if meta["visionCount"] >= cfg["vision"]["maxPerDay"]:
            break
        v = vision.check(rec["photos"], cfg)
        if v is None:
            return  # no api key set
        meta["visionCount"] += 1
        rec["vision"], rec["visionPhotos"] = v, rec["photos"][:4]
        if vision.isDealbreaker(v):
            rec["rejected"] = ["photos: " + (v.get("notes") or "looks rough")]
            rec["tier"] = "rejected"


def alertPass(recs, meta, quiet):
    kinds = {"steal": "steal", "stretch-deal": "stretch", "austin": "austin"}
    sent = 0
    for rec in recs.values():
        kind = kinds.get(rec.get("tier"))
        if not kind or not rec.get("active") or rec["price"] in rec.get("alerted", []):
            continue
        if not quiet and notify.send(rec, kind):
            sent += 1
        rec.setdefault("alerted", []).append(rec["price"])
    return sent


## dashboard export

dashFields = ["id", "source", "url", "title", "price", "make", "model", "year", "miles", "trim", "sellerType",
              "cylinders", "drive", "mpg", "vin", "city", "region", "distance", "photos", "siteRating",
              "firstSeen", "lastSeen", "priceHistory", "appraisal", "flags", "rejected", "tier", "vision", "active"]


def exportDashboard(recs, fits, status, outDir, now):
    rows = []
    for r in recs.values():
        if not r.get("model") or (r.get("rejected") or [""])[0] == "over stretch budget":
            continue
        if now - r["lastSeen"] > 3 * day:
            continue
        row = {k: r.get(k) for k in dashFields}
        row["photos"] = (r.get("photos") or [])[:1]
        row["description"] = (r.get("description") or "")[:600]
        rows.append(row)
    saveJson(Path(outDir) / "data.json", {
        "updatedAt": now, "sources": status, "listings": rows,
        "fits": {m: f and {"n": f["n"], "spread": round(f["spread"], 3)} for m, f in fits.items()},
    })


## main

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="config.yml")
    ap.add_argument("--state", default="state", help="folder holding history + dashboard data")
    ap.add_argument("--quiet", action="store_true", help="never send phone alerts")
    args = ap.parse_args()

    cfg = yaml.safe_load(Path(args.config).read_text())
    st = Path(args.state)
    st.mkdir(parents=True, exist_ok=True)
    recs = loadJson(st / "listings.json", {})
    comps = loadJson(st / "comps.json", {})
    nhtsa = loadJson(st / "nhtsa.json", {})
    meta = loadJson(st / "meta.json", {})
    now = int(time.time())
    fetcher = Fetcher(cfg["crawl"]["delaySeconds"])

    nhtsa = reliability.refreshComplaints(nhtsa, cfg, log)

    if now - meta.get("compsAt", 0) > 6 * 3600:
        try:
            compList = cargurus.crawlComps(fetcher, cfg, cfg["home"], log)
            updateComps(comps, compList, now)
            meta["compsAt"] = now
        except Exception as e:
            log(f"comps skipped: {e}")

    found, touched, status = crawlAll(cfg, fetcher, recs, meta)
    mergeListings(recs, found, touched, now)
    updateComps(comps, found, now)
    fits = pricing.buildFits({m: list(v.values()) for m, v in comps.items()})
    evaluateAll(recs, fits, nhtsa, cfg, now)
    visionPass(recs, cfg, meta)

    # first ever run: record everything as already seen so your phone doesn't get 40 pings
    firstRun = not meta.get("initialized")
    sent = alertPass(recs, meta, quiet=args.quiet or firstRun)
    meta["initialized"] = True
    if firstRun and os.environ.get("NTFY_TOPIC") and not args.quiet:
        notify.sendText("Car finder is live",
                        f"Tracking {sum(1 for r in recs.values() if r.get('tier') not in (None, 'rejected'))} cars. "
                        "Alerts start with the next new deal.")

    recs = {k: v for k, v in recs.items() if now - v["lastSeen"] < cfg["crawl"]["dropAfterDays"] * day}
    saveJson(st / "listings.json", recs)
    saveJson(st / "comps.json", comps)
    saveJson(st / "nhtsa.json", nhtsa)
    saveJson(st / "meta.json", meta)
    exportDashboard(recs, fits, status, st, now)

    tiers = {}
    for r in recs.values():
        if r.get("active"):
            tiers[r.get("tier")] = tiers.get(r.get("tier"), 0) + 1
    log(f"done: {fetcher.requestCount} requests, {sent} alerts, tiers {tiers}, sources {status}")


if __name__ == "__main__":
    main()
