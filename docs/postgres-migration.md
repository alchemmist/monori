## PostgreSQL opt-in (schema 0021)

`MONORI_DATABASE_URL` selects PostgreSQL. Without it, existing SQLite deployments are unchanged. Keep the data volume and existing authentication/encryption secrets. Use TLS verify-full in production. Do not run with two different databases accepting writes. `scripts/import_postgres_0021.py` expects an empty dedicated database, not an existing schema: it imports once, compares typed row multisets and financial receipts and commits atomically. Provision the financial app separately, with only namespace-scoped network access; do not grant cluster-level privileges.

Validation: `scripts/pgtests/run.sh` exercises the application integration suite on a private PostgreSQL cluster; the original SQLite suite remains in place. Arbitrary admin SQL is deliberately unavailable in PostgreSQL mode: SQLite statement limits, transaction oversight and progress handlers do not secure a shared PostgreSQL server. Do not represent this as feature parity or switch a deployment requiring the SQL console before resolving that difference.

In the isolated production-data rehearsal all 16 tables matched and account totals, transactions and both transfer legs compared equal. No production switch is implied by an application commit. Once writes begin on PostgreSQL, rolling back to the old SQLite file would lose newer transactions.
