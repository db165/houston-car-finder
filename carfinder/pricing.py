## market value model: per model, log(value) ~ age + miles, fit on every comp we've seen
#
# why a regression instead of "average of cars like it": at $4-7k there are only a
# handful of exact year/mileage matches near houston, so a bucket median is noisy.
# a per-model curve uses every listing of that model to learn how fast value drops
# per year and per 10k miles, then predicts the value of this exact car.

import numpy as np

refYear = 2015


def compValue(c):
    # prefer cargurus' own market estimate; fall back to asking price
    return c.get("marketValue") or c.get("price")


def fitModel(comps):
    rows = [(c["year"], c["miles"], compValue(c)) for c in comps
            if c.get("year") and c.get("miles") and compValue(c) and compValue(c) > 1000]
    if len(rows) < 3:
        return None
    yr = np.array([r[0] for r in rows], float)
    mi = np.array([r[1] for r in rows], float)
    val = np.array([r[2] for r in rows], float)
    X = np.column_stack([np.ones(len(rows)), yr - refYear, mi / 10000.0])
    y = np.log(val)
    # light ridge so a few comps can't produce a crazy slope
    lam = np.diag([0.0, 0.5, 0.5])
    coef = np.linalg.solve(X.T @ X + lam, X.T @ y)
    resid = y - X @ coef
    spread = float(np.std(resid)) if len(rows) > 3 else 0.25
    return {"coef": coef.tolist(), "n": len(rows), "spread": spread,
            "yearRange": [int(yr.min()), int(yr.max())],
            "milesRange": [int(mi.min()), int(mi.max())]}


def predict(fit, year, miles):
    a, b, c = fit["coef"]
    return float(np.exp(a + b * (year - refYear) + c * miles / 10000.0))


def buildFits(compsByModel):
    return {model: fitModel(rows) for model, rows in compsByModel.items()}


def appraise(lst, fits, cfg):
    # returns dict: marketValue, dealPct, confidence, basis
    dealCfg = cfg["deal"]
    fit = fits.get(lst["model"])
    est, basis, conf = None, "", "low"

    if lst.get("year") and lst.get("miles") and fit:
        est = predict(fit, lst["year"], lst["miles"])
        inside = (fit["yearRange"][0] - 1 <= lst["year"] <= fit["yearRange"][1] + 1)
        conf = "high" if fit["n"] >= dealCfg["minComps"] * 2 and inside else \
               "medium" if fit["n"] >= dealCfg["minComps"] and inside else "low"
        basis = f"{fit['n']} comps"

    # cargurus already appraised dealer cars against its whole national dataset
    if lst.get("source") == "cargurus" and lst.get("marketValue"):
        site = lst["marketValue"]
        est = site if est is None else 0.6 * site + 0.4 * est
        basis = "cargurus value" + (f" + {fit['n']} comps" if fit else "")
        conf = "high"

    if est is None:
        return {"marketValue": None, "dealPct": None, "confidence": "none", "basis": "not enough data"}

    if lst.get("sellerType") == "private":
        est *= dealCfg["privateDiscount"]

    pct = (est - lst["price"]) / est if lst.get("price") else None
    return {"marketValue": round(est), "dealPct": round(pct, 3) if pct is not None else None,
            "confidence": conf, "basis": basis}
