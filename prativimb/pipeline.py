"""Single entry point: python -m prativimb.pipeline [data|twin|glucose|cardio|report|train|all]"""
from __future__ import annotations

import sys
import time


def main(argv: list[str]) -> None:
    stage = argv[0] if argv else "all"
    t0 = time.time()
    steps = {
        "data": ["data"], "twin": ["twin"], "glucose": ["glucose"], "cardio": ["cardio"], "report": ["report"],
        "train": ["twin", "glucose", "cardio", "report"], "all": ["data", "twin", "glucose", "cardio", "report"],
    }[stage]
    for s in steps:
        print(f"== {s}")
        if s == "data":
            from prativimb.data import generate
            generate.run()
        elif s == "twin":
            from prativimb.twin import fit_all
            fit_all.run()
        elif s == "glucose":
            from prativimb.ml import glucose
            glucose.run()
        elif s == "cardio":
            from prativimb.ml import cardio
            cardio.run()
        elif s == "report":
            from prativimb.eval import report
            report.run()
    print(f"finished '{stage}' in {time.time() - t0:.0f}s")


if __name__ == "__main__":
    import warnings
    warnings.filterwarnings("ignore")
    main(sys.argv[1:])
