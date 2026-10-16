#!/usr/bin/env bash
# Smoke test script for ImpactGraph deployed / local instance
set -e

HOST="${1:-http://localhost:8000}"
echo "=========================================="
echo "ImpactGraph Smoke Test: targeting $HOST"
echo "=========================================="

# 1. Health check
echo -n "Checking /health ... "
HEALTH=$(curl -s "$HOST/health")
echo "$HEALTH" | grep -q '"status":"ok"' && echo "✅ OK" || (echo "❌ FAILED" && exit 1)

# 2. Available repositories
echo -n "Checking /repos ... "
REPOS=$(curl -s "$HOST/repos")
echo "$REPOS" | grep -q "vorta" && echo "✅ OK ($REPOS)" || echo "⚠️  No vorta graph loaded"

# 3. Demo PR 1 endpoint
echo -n "Checking /demo/1 ... "
DEMO=$(curl -s "$HOST/demo/1")
echo "$DEMO" | grep -q '"risk"' && echo "✅ OK" || (echo "❌ FAILED" && exit 1)

# 4. Benchmark endpoint
echo -n "Checking /benchmark ... "
BENCH=$(curl -s "$HOST/benchmark")
echo "$BENCH" | grep -q '"metrics"' && echo "✅ OK" || (echo "❌ FAILED" && exit 1)

echo "=========================================="
echo "All smoke tests PASSED successfully!"
echo "=========================================="
