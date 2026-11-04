#!/usr/bin/env bash
set -e
cd "$(dirname "$0")"
for dir in task1-mcp-server task2-mcp-gateway task3-pii-guardrail task4-model-router; do
  echo "$dir"
  (cd "$dir" && python -m pytest -q tests)
done
