# Payment Exception Resolution Engine

A local-first prototype for reconstructing ambiguous payment lifecycles, detecting payment exceptions, and evaluating controlled resolution trajectories. It does not connect to Razorpay, UPI, or move money.

## Current scope

Phases 0–7 are implemented:

- source CSV inspection and PostgreSQL ingestion;
- deterministic payment-state semantics;
- four controlled exception scenarios;
- reproducible lifecycle generation with observed/hidden event boundaries.
- time-safe deterministic state reconstruction and V1 exception detection.
- controlled customer complaint signals with cutoff-aware visibility.

ML, policy, API, and UI work are not implemented yet.

## Requirements

- Python 3.11+
- Docker Desktop or another local Docker runtime
- The [Kaggle UPI Payment Transactions Dataset](https://www.kaggle.com/datasets/devildyno/upi-payment-transactions-dataset)

The raw CSV and generated ground truth are intentionally ignored by Git. Download the dataset under its license and place the unchanged file at `data/raw/transactions.csv`.

## Run locally

```sh
python3 -m venv .venv
.venv/bin/pip install --editable .
docker compose up -d postgres

.venv/bin/python -m src.ingestion.inspect data/raw/transactions.csv --report evaluation/dataset_profile.json
.venv/bin/python -m src.ingestion.load data/raw/transactions.csv
.venv/bin/python -m src.generation.generate data/raw/transactions.csv --output data/generated
.venv/bin/python -m unittest discover -s tests -v
```

Generated lifecycle records are controlled experimental data. Their timing windows are simulated parameters, not real payment-service SLAs.

## License

Project code is available under the [MIT License](LICENSE). The external dataset retains its own license and provenance.
