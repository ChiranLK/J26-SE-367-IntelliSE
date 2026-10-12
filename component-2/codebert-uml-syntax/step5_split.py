"""STEP 5 - Leakage-safe train / validation / test split.

All samples that come from the same source diagram, and all diagrams in the same
ModelSet family / fingerprint group, go to the SAME split. Otherwise the model
would see an almost identical diagram in training and in testing, and the test
score would be inflated (proposal section 3.6).

Large template families go to TRAIN:
  Some ModelSet families hold dozens of near-identical diagrams made from one
  template. If such a family lands in test, the test set mostly measures one
  template (we saw 3 families = 65% of the test rows). So every group with more
  than --max_eval_group_diagrams source diagrams (default 10) is always put in
  train; val and test are built only from the smaller groups. Nothing is lost
  and val/test stay diverse.

The remaining groups are split with StratifiedGroupKFold (20 folds): ~70% train,
~15% val, ~15% test, stratified by label + diagram type.

--reuse_from : copy the group -> split assignment of an earlier split. Use it for
               the --strict ablation dataset, so both experiments are tested on
               exactly the same diagrams (a fair comparison).

Usage:
  python step5_split.py
  python step5_split.py --in data/syntax_dataset_strict.csv --out_dir data/splits_strict --reuse_from data/splits
"""
import argparse
from pathlib import Path

import pandas as pd
from sklearn.model_selection import StratifiedGroupKFold


def split_new(df, seed, max_eval_group):
    split = pd.Series("train", index=df.index)
    size = df.groupby("group")["diagram_id"].nunique()
    big = set(size[size > max_eval_group].index) if max_eval_group > 0 else set()
    rest = df[~df["group"].isin(big)]
    n_folds = min(20, rest["group"].nunique())
    strat = rest["label"] + "|" + rest["diagram_type"]
    sgkf = StratifiedGroupKFold(n_splits=n_folds, shuffle=True, random_state=seed)
    fold = pd.Series(-1, index=rest.index)
    for k, (_, idx) in enumerate(sgkf.split(rest, strat, rest["group"])):
        fold.iloc[idx] = k
    n_test = max(1, round(n_folds * 0.15))
    n_val = max(1, round(n_folds * 0.15))
    split[fold[fold < n_test].index] = "test"
    split[fold[(fold >= n_test) & (fold < n_test + n_val)].index] = "val"
    return split, big, size


def split_reuse(df, ref_dir):
    mapping = {}
    for s in ("train", "val", "test"):
        ref = pd.read_csv(Path(ref_dir) / f"{s}.csv", keep_default_na=False, usecols=["group"])
        for g in ref["group"].unique():
            mapping[g] = s
    split = df["group"].map(mapping)
    missing = split.isna().sum()
    if missing:
        print(f"note: {missing} rows belong to groups not in {ref_dir}; they go to train")
    return split.fillna("train")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp", default="data/syntax_dataset.csv")
    ap.add_argument("--out_dir", default="data/splits")
    ap.add_argument("--reuse_from", default="", help="folder of an earlier split to copy the group assignment from")
    ap.add_argument("--max_eval_group_diagrams", type=int, default=10,
                    help="groups with more source diagrams than this always go to train (0 = off)")
    ap.add_argument("--seed", type=int, default=42)
    a = ap.parse_args()

    df = pd.read_csv(a.inp, keep_default_na=False)
    if a.reuse_from:
        df["split"] = split_reuse(df, a.reuse_from)
    else:
        df["split"], big, size = split_new(df, a.seed, a.max_eval_group_diagrams)
        if big:
            print(f"{len(big)} large groups (> {a.max_eval_group_diagrams} diagrams, "
                  f"{int(size[list(big)].sum())} diagrams in total) were put in train")

    # hard guarantees: no group and no source diagram in more than one split
    assert df.groupby("group")["split"].nunique().max() == 1, "group leakage!"
    assert df.groupby("diagram_id")["split"].nunique().max() == 1, "diagram leakage!"

    out = Path(a.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    for s in ("train", "val", "test"):
        df[df.split == s].drop(columns="split").to_csv(out / f"{s}.csv", index=False)

    print(pd.crosstab(df["label"], df["split"]).to_string())
    print("\ndiagram types per split:")
    print(pd.crosstab(df["diagram_type"], df["split"]).to_string())
    print("\nrows:", df["split"].value_counts().to_dict(), "| groups:", df.groupby("split")["group"].nunique().to_dict(),
          "| source diagrams:", df.groupby("split")["diagram_id"].nunique().to_dict())
    for s in ("val", "test"):
        v = df[df.split == s]["group"].value_counts()
        if len(v):
            print(f"largest group share of {s}: {100 * v.max() / v.sum():.1f}%  "
                  f"(top 3 groups together: {100 * v.head(3).sum() / v.sum():.1f}%)")
    empty = [l for l in df["label"].unique() if (df[df.split == "test"]["label"] == l).sum() == 0]
    if empty:
        print("WARNING: these labels have NO test samples:", empty)


if __name__ == "__main__":
    main()