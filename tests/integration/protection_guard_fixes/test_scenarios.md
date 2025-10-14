# Test Scenarios for Protection Guard Fixes

## Fix #3: Side Validation

### Scenario 1: LONG position with correct SELL SL
- Open LONG position
- Check SL is SELL order
- Should: PASS

### Scenario 2: SHORT position with correct BUY SL
- Open SHORT position
- Check SL is BUY order
- Should: PASS

### Scenario 3: LONG position with wrong BUY SL (should not recognize)
- Mock: LONG position
- Mock: BUY stop order (wrong side)
- Should: NOT recognize as SL for LONG

## Fix #2: SL Price Validation

### Scenario 4: Valid existing SL (within tolerance)
- Existing SL: $49,000
- Target SL: $49,500
- Diff: 1.02%
- Should: REUSE existing SL

### Scenario 5: Invalid existing SL (from old position)
- Old position LONG @ $50,000, SL @ $49,000
- New position LONG @ $60,000, target SL @ $58,800
- Existing SL too far (16.67%)
- Should: CANCEL old SL, CREATE new

### Scenario 6: Wrong direction SL
- LONG position
- Existing SL ABOVE entry (wrong direction)
- Should: REJECT, create correct SL

## Fix #1: PositionGuard Integration

### Scenario 7: PositionGuard starts for new position
- Open position
- Should: start_protection() called
- Should: position added to monitored_positions

### Scenario 8: Health score calculated
- Position with 2% profit
- Should: health_score > 70
- Should: risk_level = LOW

### Scenario 9: Emergency exit triggered
- Position with -4% loss
- Should: emergency_exit_position() called
- Should: position closed via exchange
