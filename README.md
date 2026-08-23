# Payment Exception Resolution Engine

A local-first prototype for reconstructing ambiguous payment lifecycles, detecting payment exceptions, and evaluating controlled resolution trajectories. It does not connect to Razorpay, UPI, or move money.

## Current scope

Phases 0–15 are implemented:

- source CSV inspection and PostgreSQL ingestion;
- deterministic payment-state semantics;
- four controlled exception scenarios;
- reproducible lifecycle generation with observed/hidden event boundaries.
- time-safe deterministic state reconstruction and V1 exception detection.
- controlled customer complaint signals with cutoff-aware visibility.
- versioned, leakage-safe feature rows.
- controlled targets, deterministic splits, and a measured rules baseline.
- logistic-regression ablations on the V2 intervention target; observed timing contributes meaningful held-out signal.
- deterministic policy recommendations constrained to a safe action catalogue and human approval for money-moving intents.
- append-only, provenance-tagged audit trails and controlled resolution verification after future evidence is revealed.
- a standalone end-to-end evaluator that proves the entire engine without API or UI dependencies.
- a read-only local HTTP boundary over the existing evaluated engine records.
- a static, API-backed local demo that visualizes the evaluated records without business logic.

All planned phases are complete. The demo remains local, simulated, read-only, and non-money-moving.

## Requirements

- Python 3.11+
- Docker Desktop or another local Docker runtime
- The [Kaggle UPI Payment Transactions Dataset](https://www.kaggle.com/datasets/devildyno/upi-payment-transactions-dataset)

The raw CSV and generated ground truth are intentionally ignored by Git. Download the dataset under its license and place the unchanged file at `data/raw/transactions.csv`.

## Quick start

1. Download the dataset under its license and place the unchanged CSV at `data/raw/transactions.csv`.
2. Run:

```sh
make setup
make check
make run
```

Open <http://127.0.0.1:8000>. The page is a local, read-only controlled-simulation demo; it has no payment controls.

For the end-to-end evaluation, run `make evaluate`. For the full suite, start PostgreSQL with `docker compose up -d postgres`, then run `make test`.

Run `make help` for all commands. You can override `PYTHON`, `VENV`, or `DATA` when needed, for example `make DATA=/path/to/transactions.csv run`.

## Manual commands

```sh
python3 -m venv .venv
.venv/bin/pip install --editable .
docker compose up -d postgres

.venv/bin/python -m src.ingestion.inspect data/raw/transactions.csv --report evaluation/dataset_profile.json
.venv/bin/python -m src.ingestion.load data/raw/transactions.csv
.venv/bin/python -m src.generation.generate data/raw/transactions.csv --output data/generated
.venv/bin/python -m src.evaluation data/raw/transactions.csv --report evaluation/phase13_end_to_end_report.json --markdown-report evaluation/reports/phase13_end_to_end.md
.venv/bin/python -m src.api data/raw/transactions.csv --host 127.0.0.1 --port 8000
.venv/bin/python -m unittest discover -s tests -v
```

Generated lifecycle records are controlled experimental data. Their timing windows are simulated parameters, not real payment-service SLAs.

## License

Project code is available under the [MIT License](LICENSE). The external dataset retains its own license and provenance.
