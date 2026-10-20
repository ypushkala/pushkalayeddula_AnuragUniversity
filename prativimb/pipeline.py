"""Single entry point: python -m prativimb.pipeline [data|twin|glucose|cardio|report|followup|train|all]"""
from __future__ import annotations

import sys
import time


def main(argv: list[str]) -> None:
    stage = argv[0] if argv else "all"
    t0 = time.time()
    steps = {
        "data": ["data"], "twin": ["twin"], "glucose": ["glucose"], "hypo": ["hypo"], "cardio": ["cardio"],
        "report": ["report", "followup"], "followup": ["followup"],
        "reference": ["reference"], "counterfactual": ["counterfactual"],
        "train": ["twin", "glucose", "hypo", "cardio", "reference", "report", "followup", "counterfactual"],
        "all": ["data", "twin", "glucose", "hypo", "cardio", "reference", "report", "followup", "counterfactual"],
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
        elif s == "hypo":
            from prativimb.ml import hypo
            hypo.run()
        elif s == "cardio":
            from prativimb.ml import cardio
            cardio.run()
        elif s == "report":
            from prativimb.eval import report
            report.run()
        elif s == "reference":
            from prativimb.data import reference
            reference.build_checkpoints()
        elif s == "counterfactual":
            from prativimb.eval import counterfactual
            counterfactual.run(verbose=False)
        elif s == "followup":
            from prativimb.eval import followup
            followup.run(verbose=False)
    print(f"finished '{stage}' in {time.time() - t0:.0f}s")


if __name__ == "__main__":
    import warnings
    warnings.filterwarnings("ignore")
    main(sys.argv[1:])
