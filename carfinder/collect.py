## raspberry pi side: crawl the sites that block github's servers and write one snapshot file
# no pricing or alerts here; github merges this snapshot on its next run

import argparse
import json
import time
from pathlib import Path

import yaml

from .fetch import Fetcher, Blocked
from .sources import autolist, offerup, cargurus, copart, iaa


def log(msg):
    print(time.strftime("%H:%M:%S"), msg, flush=True)


def loadJson(path, default):
    try:
        return json.loads(Path(path).read_text())
    except (FileNotFoundError, ValueError):
        return default


def guarded(status, name, fn):
    # one site failing never stops the others
    try:
        out = fn()
        status[name] = "ok"
        return out
    except Blocked as e:
        status[name] = f"blocked: {e}"
    except Exception as e:
        status[name] = f"error: {e}"[:200]
    log(f"{name}: {status[name]}")
    return []


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="config.yml")
    ap.add_argument("--state", default=str(Path.home() / "carfinder-state"), help="pi-only cache")
    ap.add_argument("--out", required=True, help="folder that gets pushed to the collected branch")
    args = ap.parse_args()

    cfg = yaml.safe_load(Path(args.config).read_text())
    st, out = Path(args.state), Path(args.out)
    st.mkdir(parents=True, exist_ok=True)
    out.mkdir(parents=True, exist_ok=True)
    cache = loadJson(st / "cache.json", {})
    ouKnown = cache.setdefault("offerup", {})
    cpKnown = cache.setdefault("copart", {})
    status, listings, lots = {}, [], []

    areas = [("houston", cfg["home"], cfg["budget"]["stretchMax"], cfg["budget"]["compsMax"])]
    if cfg["austin"]["enabled"]:
        areas.append(("austin", cfg["austin"], cfg["austinRule"]["maxPrice"], cfg["austinRule"]["maxPrice"]))

    for region, area, maxPrice, compsMax in areas:
        # each site gets its own throttle so a slow one doesn't starve the rest
        listings += guarded(status, f"autolist-{region}",
                            lambda: autolist.crawl(Fetcher(cfg["crawl"]["delaySeconds"]), cfg, region, area, compsMax, log))
        listings += guarded(status, f"cargurus-{region}",
                            lambda: cargurus.crawl(Fetcher(cfg["crawl"]["delaySeconds"]), cfg, region, area, maxPrice, log))
    houston = dict(cfg["home"], city="Houston", state="TX")
    listings += guarded(status, "offerup-houston",
                        lambda: offerup.crawl(Fetcher(cfg["crawl"]["delaySeconds"]), cfg, "houston", houston,
                                              cfg["budget"]["stretchMax"], ouKnown, log))
    comps = guarded(status, "cargurus-comps",
                    lambda: cargurus.crawlComps(Fetcher(cfg["crawl"]["delaySeconds"]), cfg, cfg["home"], log))

    sc = cfg.get("copart", {})
    if sc.get("enabled"):
        lots += guarded(status, "copart", lambda: copart.crawl(Fetcher(cfg["crawl"]["delaySeconds"]), sc, cpKnown, log))
        lots += guarded(status, "iaa", lambda: iaa.crawl(Fetcher(cfg["crawl"]["delaySeconds"]), sc, log))

    # keep the cache from growing forever: forget ids we no longer see
    seenOu = {l.id.split(":", 1)[1] for l in listings if l.source == "offerup"}
    cache["offerup"] = {k: v for k, v in ouKnown.items() if k in seenOu}
    cache["copart"] = {k: v for k, v in cpKnown.items() if k in {l["id"] for l in lots}}
    (st / "cache.json").write_text(json.dumps(cache))

    snap = {"collectedAt": int(time.time()), "status": status,
            "listings": [l.toDict() for l in listings], "comps": [l.toDict() for l in comps], "lots": lots}
    (out / "collected.json").write_text(json.dumps(snap, separators=(",", ":"), default=str))
    log(f"done: {len(listings)} listings, {len(comps)} comps, {len(lots)} auction lots, status {status}")


if __name__ == "__main__":
    main()
