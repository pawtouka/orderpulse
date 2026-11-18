# OrderPulse

OrderPulse is a REST API for turning e-commerce order exports into sales reports. A store can upload a CSV and use the resulting API to track paid revenue, average order value, and performance by country or day.

## Features

- Atomic CSV imports with row-level validation errors and duplicate order IDs skipped.
- Paid revenue, order counts, and average order value across the store or for a selected country and date range.
- Revenue by country and UTC calendar day.
- Interactive OpenAPI documentation, a health endpoint, and 36 synthetic sample orders.

## Stack and architecture

Python 3.12+, FastAPI, Pydantic, SQLAlchemy 2.0, SQLite, Uvicorn, Pytest, HTTPX, and Ruff.

| Path | Responsibility |
| --- | --- |
| `orderpulse/main.py` | Application factory and database lifecycle |
| `orderpulse/routers/` | HTTP routes, request parameters, and error responses |
| `orderpulse/database.py`, `orderpulse/models.py` | Session configuration and order table |
| `orderpulse/schemas.py` | Input validation and response models |
| `orderpulse/csv_import.py` | CSV validation and transactional inserts |
| `orderpulse/analytics.py` | Paid-order SQL queries and exact amount formatting |
| `tests/` | HTTP tests with a fresh temporary SQLite database per test |

## Run locally

Run these commands from the project root to create a virtual environment, install the project, and start the API.

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
python -m uvicorn orderpulse.main:app --reload
```

The server creates `orderpulse.db` in the current directory on first startup. Set `ORDERPULSE_DATABASE_URL` to a SQLite URL such as `sqlite:////absolute/path/orders.db` to use a different file.

Open [Swagger UI](http://127.0.0.1:8000/docs) to upload a CSV or try the analytics endpoints in your browser. The health endpoint is `GET /health` and returns `{"status":"ok"}`.

## Import orders

```sh
curl --fail-with-body -F 'file=@data/sample_orders.csv;type=text/csv' \
  http://127.0.0.1:8000/orders/import
```

On the first upload into an empty database, the API returns this result.

```json
{"imported":36,"skipped":0}
```

The CSV must be UTF-8 (an optional byte order mark is accepted), at most 5 MiB, and include exactly the columns shown below in any order.

```csv
order_id,created_at,country,amount_usd,status
OP-1001,2025-03-01T08:12:00Z,US,89.90,paid
```

- Order IDs contain 1–128 characters. The first record for each ID wins. Reimporting the same sample returns `{"imported":0,"skipped":36}`.
- Dates accept `YYYY-MM-DD` or an ISO timestamp. Timestamps with offsets are converted to UTC. Dates and timestamps without offsets are treated as UTC.
- Country codes use two ASCII letters and are normalized to uppercase.
- Amounts must be nonnegative USD values up to `9999999.99` with at most two fractional digits.
- Status must be `paid`, `pending`, `cancelled`, or `refunded`.

An invalid header or row returns HTTP 422 and leaves the database unchanged, including when a malformed row repeats an existing ID. The error response includes a message and, where available, the CSV line and field. Oversized files return HTTP 413.

## Query analytics

All analytics endpoints accept optional `country`, `date_from`, and `date_to` query parameters. Dates are inclusive UTC dates in `YYYY-MM-DD` format. Only paid orders contribute. The database stores integer cents, and the API returns money as decimal strings with exactly two fractional digits. Average order values round half up to the nearest cent.

### Summary

```sh
curl --fail-with-body http://127.0.0.1:8000/analytics/summary
```

```json
{"total_revenue_usd":"2135.67","paid_orders":26,"average_order_value_usd":"82.14"}
```

When no paid orders match, amounts are `"0.00"` and the count is zero.

### By country

Results are sorted by revenue descending, with country code as the tie-breaker.

```sh
curl --fail-with-body 'http://127.0.0.1:8000/analytics/by-country?date_from=2025-03-01&date_to=2025-03-02'
```

```json
[
  {"country":"US","total_revenue_usd":"309.85","paid_orders":2},
  {"country":"AU","total_revenue_usd":"147.25","paid_orders":1},
  {"country":"DE","total_revenue_usd":"79.95","paid_orders":1},
  {"country":"FR","total_revenue_usd":"64.00","paid_orders":1},
  {"country":"GB","total_revenue_usd":"54.50","paid_orders":1},
  {"country":"CA","total_revenue_usd":"38.99","paid_orders":1}
]
```

### Daily revenue

Results are sorted chronologically. Dates without paid orders are omitted.

```sh
curl --fail-with-body 'http://127.0.0.1:8000/analytics/daily?country=US&date_from=2025-03-01&date_to=2025-03-02'
```

```json
[
  {"date":"2025-03-01","total_revenue_usd":"89.90"},
  {"date":"2025-03-02","total_revenue_usd":"219.95"}
]
```

## Tests and lint

```sh
python -m pytest -q
python -m pytest -q --cov --cov-report=term-missing --cov-report=html
ruff check .
ruff format --check .
```

Each API test uses an isolated SQLite database. The coverage command checks an
85% minimum for combined line and branch coverage and writes the HTML report to
`htmlcov/index.html`. GitHub Actions runs these checks on Python 3.12 and uploads
the HTML report.

## Future improvements

- Track status changes so a later export can record refunds against previously paid orders.
- Add Alembic migrations as the schema evolves.
- Record import history with row counts and timestamps.
