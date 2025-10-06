#!/bin/bash
# ============================================================================
# REAL INTEGRATION TEST - Launcher Script
# ============================================================================
# Launches all components of the integration test in correct sequence
# Date: 2025-10-04
# ============================================================================

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Configuration
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TEST_DIR="${PROJECT_ROOT}/tests/integration"
DB_DSN="${DB_DSN:-postgresql://localhost/trading_bot}"
TEST_DURATION="${TEST_DURATION:-3600}"  # 1 hour by default
WAVE_INTERVAL="${WAVE_INTERVAL:-900}"  # 15 minutes
MONITOR_INTERVAL="${MONITOR_INTERVAL:-10}"  # 10 seconds

# PIDs for cleanup
GENERATOR_PID=""
BOT_PID=""
MONITOR_PID=""

# ============================================================================
# Helper Functions
# ============================================================================

print_header() {
    echo -e "${CYAN}╔════════════════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${CYAN}║${NC}    $1"
    echo -e "${CYAN}╚════════════════════════════════════════════════════════════════════════╝${NC}"
}

print_step() {
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${GREEN}▶${NC} $1"
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
}

print_success() {
    echo -e "${GREEN}✅${NC} $1"
}

print_error() {
    echo -e "${RED}❌${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}⚠️${NC}  $1"
}

print_info() {
    echo -e "${CYAN}ℹ️${NC}  $1"
}

# ============================================================================
# Cleanup Function
# ============================================================================

cleanup() {
    echo ""
    print_step "Cleaning up processes..."
    
    # Kill monitor
    if [ -n "$MONITOR_PID" ] && kill -0 $MONITOR_PID 2>/dev/null; then
        print_info "Stopping monitor (PID: $MONITOR_PID)..."
        kill -TERM $MONITOR_PID 2>/dev/null || true
        wait $MONITOR_PID 2>/dev/null || true
        print_success "Monitor stopped"
    fi
    
    # Kill bot
    if [ -n "$BOT_PID" ] && kill -0 $BOT_PID 2>/dev/null; then
        print_info "Stopping bot (PID: $BOT_PID)..."
        kill -TERM $BOT_PID 2>/dev/null || true
        sleep 5  # Give bot time for graceful shutdown
        kill -KILL $BOT_PID 2>/dev/null || true
        wait $BOT_PID 2>/dev/null || true
        print_success "Bot stopped"
    fi
    
    # Kill signal generator
    if [ -n "$GENERATOR_PID" ] && kill -0 $GENERATOR_PID 2>/dev/null; then
        print_info "Stopping signal generator (PID: $GENERATOR_PID)..."
        kill -TERM $GENERATOR_PID 2>/dev/null || true
        wait $GENERATOR_PID 2>/dev/null || true
        print_success "Signal generator stopped"
    fi
    
    print_success "All processes stopped"
}

# Set trap for cleanup
trap cleanup EXIT INT TERM

# ============================================================================
# Main Execution
# ============================================================================

main() {
    print_header "🧪 REAL INTEGRATION TEST LAUNCHER"
    
    echo ""
    print_info "Project Root: $PROJECT_ROOT"
    print_info "Test Directory: $TEST_DIR"
    print_info "Database DSN: $DB_DSN"
    print_info "Test Duration: ${TEST_DURATION}s ($(($TEST_DURATION / 60))m)"
    print_info "Wave Interval: ${WAVE_INTERVAL}s ($(($WAVE_INTERVAL / 60))m)"
    echo ""
    
    # ========================================================================
    # Phase 1: Database Setup
    # ========================================================================
    print_step "Phase 1: Database Setup"
    
    print_info "Setting up test database schema..."
    psql "$DB_DSN" -f "${TEST_DIR}/real_test_db_setup.sql" > /dev/null 2>&1
    
    if [ $? -eq 0 ]; then
        print_success "Database schema created"
    else
        print_error "Failed to create database schema"
        exit 1
    fi
    
    # ========================================================================
    # Phase 2: Fetch Liquid Pairs
    # ========================================================================
    print_step "Phase 2: Fetching Liquid Pairs"
    
    if [ ! -f "${TEST_DIR}/liquid_pairs.json" ]; then
        print_info "Fetching top liquid pairs from exchanges..."
        cd "$PROJECT_ROOT"
        python3 "${TEST_DIR}/real_test_fetch_liquid_pairs.py"
        
        if [ $? -eq 0 ]; then
            print_success "Liquid pairs fetched"
        else
            print_error "Failed to fetch liquid pairs"
            exit 1
        fi
    else
        print_info "Using existing liquid_pairs.json"
        print_success "Liquid pairs loaded"
    fi
    
    # ========================================================================
    # Phase 3: Start Signal Generator
    # ========================================================================
    print_step "Phase 3: Starting Signal Generator"
    
    print_info "Starting signal generator in background..."
    cd "$PROJECT_ROOT"
    python3 "${TEST_DIR}/real_test_signal_generator.py" \
        --duration $TEST_DURATION \
        --db-dsn "$DB_DSN" \
        --wave-interval $WAVE_INTERVAL \
        > "${TEST_DIR}/signal_generator.log" 2>&1 &
    
    GENERATOR_PID=$!
    sleep 2
    
    if kill -0 $GENERATOR_PID 2>/dev/null; then
        print_success "Signal generator started (PID: $GENERATOR_PID)"
        print_info "Log: ${TEST_DIR}/signal_generator.log"
    else
        print_error "Failed to start signal generator"
        exit 1
    fi
    
    # Wait for first wave
    print_info "Waiting for first wave of signals..."
    sleep 10
    
    # ========================================================================
    # Phase 4: Start Bot (Commented out - requires modification to main.py)
    # ========================================================================
    print_step "Phase 4: Starting Trading Bot"
    
    print_warning "Bot start is MANUAL for now"
    print_info "To start bot in test mode:"
    print_info "  1. Set TEST_MODE=true in .env"
    print_info "  2. Set TEST_SIGNAL_TABLE=test.scoring_history in .env"
    print_info "  3. Run: python main.py"
    print_info ""
    print_info "Press ENTER when bot is running..."
    read -r
    
    # Uncomment when bot wrapper is ready:
    # print_info "Starting trading bot in TEST mode..."
    # cd "$PROJECT_ROOT"
    # TEST_MODE=true python3 main.py > "${TEST_DIR}/bot.log" 2>&1 &
    # BOT_PID=$!
    # sleep 5
    # 
    # if kill -0 $BOT_PID 2>/dev/null; then
    #     print_success "Bot started (PID: $BOT_PID)"
    #     print_info "Log: ${TEST_DIR}/bot.log"
    # else
    #     print_error "Failed to start bot"
    #     exit 1
    # fi
    
    # ========================================================================
    # Phase 5: Start Monitor
    # ========================================================================
    print_step "Phase 5: Starting Real-time Monitor"
    
    print_info "Starting monitor..."
    sleep 2
    
    cd "$PROJECT_ROOT"
    python3 "${TEST_DIR}/real_test_monitor.py" \
        --interval $MONITOR_INTERVAL \
        --db-dsn "$DB_DSN"
    
    # Monitor runs in foreground, blocking until Ctrl+C
    
    # ========================================================================
    # Phase 6: Test Complete
    # ========================================================================
    print_step "Test Complete"
    
    print_success "Integration test finished"
    print_info "Check logs for details:"
    print_info "  - Signal Generator: ${TEST_DIR}/signal_generator.log"
    print_info "  - Bot: ${TEST_DIR}/bot.log (if started)"
}

# ============================================================================
# Execute Main
# ============================================================================

main "$@"

