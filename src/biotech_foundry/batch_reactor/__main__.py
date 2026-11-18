"""Command-line entry point for Simulator 002."""
import argparse
import json
from pathlib import Path

from .model import BatchReactor, Equipment, Vessel, Water
from .plotting import save_plots
from .reporting import summarize
from .solver import SolverSettings, simulate


def main() -> None:
    parser = argparse.ArgumentParser(description="Simulate heating and ambient loss in a water batch.")
    parser.add_argument("--config", type=Path, help="JSON file containing SI model and solver settings")
    parser.add_argument("--plot", type=Path, default=Path("batch-reactor.png"), help="output figure path")
    args = parser.parse_args()

    try:
        config = {} if args.config is None else json.loads(args.config.read_text(encoding="utf-8"))
        if not isinstance(config, dict):
            raise ValueError("The configuration must be a JSON object.")
        settings = SolverSettings(**config.pop("solver", {}))
        target_k = config.pop("target_k", None)
        reactor = BatchReactor(
            vessel=Vessel(**config.pop("vessel", {})),
            water=Water(**config.pop("water", {})),
            equipment=Equipment(**config.pop("equipment", {})),
            **config,
        )
        result = simulate(reactor, settings, target_k=target_k)
        save_plots(result, args.plot)
    except (OSError, ValueError, TypeError, RuntimeError) as error:
        parser.exit(2, f"batch reactor: {error}\n")

    print(summarize(reactor, result))
    print(f"Plots saved to {args.plot}")


if __name__ == "__main__":
    main()
