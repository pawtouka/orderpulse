# OrderPulse contributor instructions

- `orderpulse/main.py` creates the FastAPI application and manages the database lifecycle.
- `orderpulse/routers/` defines the HTTP endpoints. `schemas.py` defines request validation and response contracts.
- `database.py` and `models.py` configure SQLAlchemy and SQLite. `csv_import.py` validates and imports orders in a transaction. `analytics.py` calculates paid-order metrics in integer cents.
- `tests/` contains HTTP tests organized by CSV import, analytics, and API contracts. `data/sample_orders.csv` contains synthetic example data.

Use Python 3.12 or newer. From the repository root, install the project and its development dependencies:

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
```

Run these checks before pushing changes:

```sh
python -m pytest -q --cov --cov-report=term-missing --cov-report=html
ruff check .
ruff format --check .
```

- Use the test client fixture for HTTP tests. Keep all tests on isolated databases. Never use a development or production database.
- Preserve existing API and data behavior unless the task calls for a change. Update tests and documentation when changing a public contract.
- Add a regression test for every bug fix. Exercise observable behavior and use parametrization for related cases.
- Keep coverage at or above 85%. Generated reports in `htmlcov/` and `.coverage` are ignored by Git.
