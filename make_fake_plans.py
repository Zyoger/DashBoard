"""
Генерирует data/plans.csv с общим планом по кварталам.
План квартала = факт квартала * k, k ∈ [0.75, 1.3].

Запуск:
    python make_fake_plans.py
    python make_fake_plans.py --seed 42
"""

import argparse
import random
from pathlib import Path

import pandas as pd

from data_loader import load_sales
from plans import save_plans, PLANS_PATH


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--path", default="data/sales.xlsx")
    parser.add_argument("--out", default=str(PLANS_PATH))
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--min-k", type=float, default=0.75)
    parser.add_argument("--max-k", type=float, default=1.30)
    parser.add_argument("--round-to", type=int, default=1_000_000,
                        help="Округление плана до, руб.")
    args = parser.parse_args()

    if args.seed is not None:
        random.seed(args.seed)

    print(f"→ Читаю {args.path}…")
    sales = load_sales(args.path)

    fact = (sales.groupby(["Год", "Квартал"], as_index=False)["Сумма_без_НДС"].sum()
            .rename(columns={"Сумма_без_НДС": "Факт"}))
    fact = fact[fact["Факт"] > 0].copy()

    def make_plan(row):
        k = random.uniform(args.min_k, args.max_k)
        plan = row["Факт"] * k
        if args.round_to > 0:
            plan = round(plan / args.round_to) * args.round_to
        return max(int(plan), args.round_to if args.round_to else 1)

    fact["План_без_НДС"] = fact.apply(make_plan, axis=1)

    plans = fact[["Год", "Квартал", "План_без_НДС"]].copy()
    plans["Год"] = plans["Год"].astype(int)
    plans["Квартал"] = plans["Квартал"].astype(int)
    plans = plans.sort_values(["Год", "Квартал"]).reset_index(drop=True)

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    save_plans(plans)

    print(f"\n✓ Сгенерировано {len(plans)} строк → {out_path}")

    check = plans.merge(fact[["Год", "Квартал", "Факт"]],
                        on=["Год", "Квартал"], how="left")
    check["Выполнение, %"] = (check["Факт"] / check["План_без_НДС"] * 100).round(1)
    print("\nВыполнение по кварталам:")
    print(check.to_string(index=False))


if __name__ == "__main__":
    main()