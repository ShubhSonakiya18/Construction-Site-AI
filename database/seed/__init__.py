"""
database/seed/ — Deterministic database seed scripts.

reference_data.py — Insert static lookup tables (trades, stages, PPE, material
                    categories). Idempotent: safe to run multiple times.

sample_data.py   — Insert a sample company, project, site, workers, and one
                    daily log for local development and testing.
                    Uses fixed UUIDs so the same records appear every run.
"""
