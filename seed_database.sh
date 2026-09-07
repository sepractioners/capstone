#!/bin/bash
# Convenience script to seed CLM database

cd "$(dirname "$0")" || exit 1

echo "Seeding CLM database..."
python seed_database.py "$@"
