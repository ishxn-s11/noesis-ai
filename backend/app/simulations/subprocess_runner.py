"""Subprocess entrypoint: run one REBOUND simulation with isolation.

Usage: python -m app.simulations.subprocess_runner <request.json> <result.json>

The parent (simulation service) enforces the wall-clock deadline, so a hung or
pathological integration is killed without taking the API process down.
"""
import json
import sys
import traceback


def main() -> int:
    if len(sys.argv) != 3:
        print("usage: subprocess_runner <request.json> <result.json>", file=sys.stderr)
        return 2
    req_path, out_path = sys.argv[1], sys.argv[2]
    try:
        from app.physics.celestial.types import SimulationRequest

        with open(req_path, encoding="utf-8") as fh:
            request = SimulationRequest.model_validate(json.load(fh))
        from app.physics.celestial.rebound_engine import run_simulation

        result = run_simulation(request)
        with open(out_path, "w", encoding="utf-8") as fh:
            json.dump({"ok": True, "result": result}, fh)
        return 0
    except Exception as exc:
        with open(out_path, "w", encoding="utf-8") as fh:
            json.dump({"ok": False, "error": str(exc), "traceback": traceback.format_exc()}, fh)
        return 1


if __name__ == "__main__":
    sys.exit(main())
