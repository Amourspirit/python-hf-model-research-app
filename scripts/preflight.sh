#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

# Create top-level runtime directories.
mkdir -p \
  storage \
  exports

# Create project storage structure.
mkdir -p \
  storage/projects \
  storage/projects/default

# Create Hugging Face shell storage structure.
mkdir -p \
  storage/hf-shell \
  storage/hf-shell/assets \
  storage/hf-shell/cache \
  storage/hf-shell/downloads \
  storage/hf-shell/xet

# Ensure broad write permissions for host/container interoperability.
chmod -R 777 storage exports

echo "Pre-flight setup complete."
