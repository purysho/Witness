"""Frozen-process entry point for the Witness desktop engine sidecar."""

from witness_engine.rpc.server import main


if __name__ == "__main__":
    raise SystemExit(main())
