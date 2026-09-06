"""ralph-lab: gate-neutral Ralph loop driver.

Public API (planned, WIP):
    - run_ralph_loop(spec): outer loop driver
    - GoalSpec: YAML-loaded goal definition

CLI:
    ralph run <spec.yaml>
    ralph init
    ralph check <spec.yaml>

See README.md for design principles and prior art.
"""

__version__ = "0.1.0"
