"""Phase 4: analysis. Computes all metrics, baselines, paired bootstrap comparisons,
and the Brier-vs-K curve. Emits results/metrics.csv and results/comparisons.csv.

Bootstrap resamples QUESTIONS (not calls) per spec section 7 — calls within a
question are correlated. 10,000 resamples, seed fixed.
"""
import json
import sys
from collections import defaultdict

import numpy as np
import pandas as pd

sys.path.insert(0, ".")
from src.metrics import auc, brier, ece, log_loss, mean_abs_from_half, murphy_decomposition

SEED = 20260903
N_BOOT = 10_000
AGGREGATORS = {
    "median": lambda v: float(np.median(v)),
    "mean": lambda v: float(np.mean(v)),
    "trimmed_mean": lambda v: float(np.mean(sorted(v)[1:-1])) if len(v) > 2 else float(np.mean(v)),
}


def load(path="data/parsed/parsed.jsonl"):
    return pd.DataFrame([json.loads(l) for l in open(path)])


def per_question_frame(df):
    """Collapse to one row per (qid, condition, aggregator) with a point forecast."""
    qs = [json.loads(l) for l in open("data/questions.jsonl")]
    qmeta = pd.DataFrame(qs).set_index("qid")
    rows = []
    for (qid, cond), grp in df[df.parse_status == "ok"].groupby(["qid", "condition"]):
        probs = grp.sort_values("sample_idx").probability.values
        outcome = int(qmeta.loc[qid, "outcome"])
        stratum = qmeta.loc[qid, "stratum"]
        crowd = float(qmeta.loc[qid, "baseline_crowd_prob"])
        row = {"qid": qid, "condition": cond, "outcome": outcome,
               "stratum": stratum, "crowd": crowd, "n_samples": len(probs)}
        if cond in ("D", "E") or len(probs) > 1:
            for name, fn in AGGREGATORS.items():
                row[name] = fn(probs)
            row["k1_first"] = float(probs[0])  # sample-size-matched K=1
        else:
            row["median"] = row["mean"] = row["trimmed_mean"] = float(probs[0])
            row["k1_first"] = float(probs[0])
        rows.append(row)
    return pd.DataFrame(rows)


def metrics_row(p, y, label, subset):
    p = np.asarray(p, dtype=float)
    y = np.asarray(y, dtype=float)
    rel, res, unc = murphy_decomposition(p, y)
    return {
        "label": label, "subset": subset, "n": len(p),
        "brier": brier(p, y),
        "reliability": rel, "resolution": res, "uncertainty": unc,
        "ece_equalwidth": ece(p, y, n_bins=10),
        "ece_equalmass": ece(p, y, n_bins=10, equal_mass=True),
        "log_loss": log_loss(p, y, clip=1e-3),
        "auc": auc(p, y) if 0 < y.sum() < len(y) else float("nan"),
        "mean_abs_from_half": mean_abs_from_half(p),
    }


def paired_bootstrap_delta_brier(pairs_a, pairs_b, n_boot=N_BOOT, seed=SEED):
    """Delta Brier (A - B) with 95% CI, resampling questions.

    pairs_a/pairs_b: list of (qid, p, y) aligned so the SAME qid set is compared;
    rows are matched on qid before resampling.
    """
    a = {qid: (p, y) for qid, p, y in pairs_a}
    b = {qid: (p, y) for qid, p, y in pairs_b}
    common = sorted(set(a) & set(b))
    if not common:
        return None
    pa = np.array([a[q][0] for q in common])
    pb = np.array([b[q][0] for q in common])
    y = np.array([a[q][1] for q in common])
    rng = np.random.default_rng(seed)
    n = len(common)
    deltas = np.empty(n_boot)
    point = brier(pa, y) - brier(pb, y)
    for i in range(n_boot):
        idx = rng.integers(0, n, n)
        deltas[i] = brier(pa[idx], y[idx]) - brier(pb[idx], y[idx])
    lo, hi = np.percentile(deltas, [2.5, 97.5])
    return {"n_questions": n, "delta_brier": point, "ci_lo": lo, "ci_hi": hi,
            "p_a": pa.mean(), "p_b": pb.mean()}


def main():
    df = load()
    pq = per_question_frame(df)
    qmeta = pd.DataFrame([json.loads(l) for l in open("data/questions.jsonl")]).set_index("qid")

    # ---- per-condition metrics (median aggregator for D/E; single for A/B/C) ----
    metric_rows = []
    subsets = {
        "full": pq,
        "pre_cutoff": pq[pq.stratum == "pre_cutoff"],
        "post_cutoff": pq[pq.stratum == "post_cutoff"],
    }
    for subset_name, sub in subsets.items():
        for cond in "ABCDE":
            s = sub[sub.condition == cond]
            if s.empty:
                continue
            metric_rows.append(metrics_row(s["median"].values, s["outcome"].values,
                                           f"cond_{cond}", subset_name))
        # baselines on the same subset
        s_all = sub[sub.condition.isin(list("ABCDE"))]
        if not s_all.empty:
            y = s_all.drop_duplicates("qid").outcome.values
            base_rate = y.mean()
            metric_rows.append(metrics_row(np.full(len(y), base_rate), y, "baseline_base_rate", subset_name))
            metric_rows.append(metrics_row(np.full(len(y), 0.5), y, "baseline_constant_half", subset_name))
            crowds = s_all.drop_duplicates("qid").crowd.values
            metric_rows.append(metrics_row(crowds, y, "baseline_crowd", subset_name))

    metrics = pd.DataFrame(metric_rows)
    metrics.to_csv("results/metrics.csv", index=False)
    print(metrics.to_string(index=False))

    # ---- condition comparisons (paired bootstrap over questions) ----
    comps = []

    def pairs_for(sub, cond, agg="median"):
        s = sub[sub.condition == cond]
        return list(zip(s.qid, s[agg], s.outcome))

    full = pq
    pre = pq[pq.stratum == "pre_cutoff"]
    post = pq[pq.stratum == "post_cutoff"]

    comparisons = [
        ("RQ1: D(median,K10) vs B(high,K1)", pairs_for(full, "D", "median"), pairs_for(full, "B")),
        ("RQ1: D(median,K10) vs C(max,K1)", pairs_for(full, "D", "median"), pairs_for(full, "C")),
        ("RQ2: C(max) vs A(low)", pairs_for(full, "C"), pairs_for(full, "A")),
        ("RQ2: B(high) vs A(low)", pairs_for(full, "B"), pairs_for(full, "A")),
        ("RQ2: C(max) vs B(high)", pairs_for(full, "C"), pairs_for(full, "B")),
        ("RQ3: E(baserate,K5) vs D-matched(K5)", None, None),  # special: E vs first-5 subsample of D
        ("RQ4: D post vs pre cutoff", pairs_for(post, "D"), pairs_for(pre, "D")),
        ("vs crowd: D(median) vs crowd", pairs_for(full, "D", "median"), pairs_for(full, "D", "crowd")),
        ("vs crowd: C(max) vs crowd", pairs_for(full, "C"), pairs_for(full, "C", "crowd")),
    ]
    for name, pa, pb in comparisons:
        if name.startswith("RQ3"):
            # E (K=5 baserate) vs first-5-subsample of D (same effort/temp, std prompt)
            e_rows = full[full.condition == "E"]
            d_rows = full[full.condition == "D"]
            # matched on qid; D's first-5 subsample = mean/median of D's first 5 samples
            raw = df[df.condition == "D"]
            d5 = raw[raw.parse_status == "ok"].groupby(["qid"]).apply(
                lambda g: float(np.median(g.sort_values("sample_idx").head(5).probability.values)))
            pairs_e = list(zip(e_rows.qid, e_rows["median"], e_rows.outcome))
            pairs_d5 = [(qid, p, int(qmeta.loc[qid, "outcome"])) for qid, p in d5.items()]
            r = paired_bootstrap_delta_brier(pairs_e, pairs_d5)
            if r:
                comps.append({"comparison": name, **r})
            continue
        if pa is None:
            continue
        r = paired_bootstrap_delta_brier(pa, pb)
        if r:
            comps.append({"comparison": name, **r})

    comps_df = pd.DataFrame(comps)
    comps_df.to_csv("results/comparisons.csv", index=False)
    print()
    print(comps_df.to_string(index=False))

    # ---- Brier vs K curve (from raw D samples) ----
    ok = df[(df.condition == "D") & (df.parse_status == "ok")]
    by_q = ok.groupby("qid").apply(
        lambda g: g.sort_values("sample_idx").probability.values)
    qs_common = [q for q in by_q.index if len(by_q[q]) >= 10]
    rng = np.random.default_rng(SEED)
    curve = []
    for K in (1, 2, 3, 4, 5, 6, 7, 8, 9, 10):
        # for each question, draw K samples without replacement; average forecast = median
        preds, ys = [], []
        for q in qs_common:
            v = by_q[q]
            take = rng.choice(len(v), size=K, replace=False)
            preds.append(float(np.median(v[take])))
            ys.append(int(qmeta.loc[q, "outcome"]))
        curve.append(metrics_row(preds, ys, f"K={K}", "d_curve"))
    curve_df = pd.DataFrame(curve)
    curve_df.to_csv("results/k_curve.csv", index=False)
    print()
    print("=== Brier vs K (condition D) ===")
    print(curve_df[["label", "n", "brier", "ece_equalwidth", "mean_abs_from_half"]].to_string(index=False))


if __name__ == "__main__":
    main()
