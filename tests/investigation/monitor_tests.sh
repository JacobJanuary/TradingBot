#!/bin/bash
# Monitor test progress in real-time

echo "================================"
echo "TEST PROGRESS MONITOR"
echo "================================"
echo ""

while true; do
    clear
    echo "==================================================================================================="
    date '+%H:%M:%S'
    echo "==================================================================================================="

    echo ""
    echo "📊 BASELINE TEST (current status):"
    tail -15 tests/investigation/results_baseline.log | grep -E "(CYCLE|RESULTS|Success rate|Silent fails)" || echo "  (waiting...)"

    echo ""
    echo "📊 EVENT-BASED TEST (current status):"
    tail -15 tests/investigation/results_event_based.log | grep -E "(CYCLE|RESULTS|Success rate|Failed)" || echo "  (waiting...)"

    echo ""
    echo "📊 OPTIMISTIC TEST (completed):"
    tail -10 tests/investigation/results_optimistic.log | grep -E "(FINAL|success rate|fail rate)"

    echo ""
    echo "==================================================================================================="
    echo "Press Ctrl+C to stop monitoring"
    echo "==================================================================================================="

    sleep 10
done
