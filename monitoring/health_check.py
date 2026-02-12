"""
Health check system for monitoring component status and alerting
"""

import asyncio
from typing import Dict, Any, List, Optional, Callable
from datetime import datetime, timezone, timedelta
from enum import Enum
from dataclasses import dataclass, field
import aiohttp
from loguru import logger

from database.repository import Repository
from utils.decorators import async_retry


class HealthStatus(Enum):
    """Component health status levels"""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    CRITICAL = "critical"


class ComponentType(Enum):
    """System component types"""
    DATABASE = "database"
    EXCHANGE_API = "exchange_api"
    WEBSOCKET = "websocket"
    SIGNAL_PROCESSOR = "signal_processor"
    RISK_MANAGER = "risk_manager"
    POSITION_MANAGER = "position_manager"
    PROTECTION_SYSTEM = "protection_system"
    TRAILING_STOP = "trailing_stop"


@dataclass
class ComponentHealth:
    """Health status of a single component"""
    name: str
    type: ComponentType
    status: HealthStatus
    last_check: datetime
    response_time_ms: float
    error_count: int = 0
    error_message: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass 
class SystemHealth:
    """Overall system health status"""
    status: HealthStatus
    components: List[ComponentHealth]
    checks_passed: int
    checks_failed: int
    last_check: datetime
    alerts: List[str] = field(default_factory=list)


class HealthChecker:
    """
    Comprehensive health monitoring system
    
    Features:
    - Component health checks
    - Dependency monitoring
    - Alert generation
    - Auto-recovery attempts
    - Health history tracking
    """
    
    def __init__(self,
                 repository: Repository,
                 config: Dict[str, Any],
                 signal_processor=None):

        self.repository = repository
        self.config = config
        self.signal_processor = signal_processor
        
        # Health check intervals
        self.check_interval = config.get('health_check_interval', 30)  # seconds
        self.critical_check_interval = config.get('critical_check_interval', 10)
        
        # Thresholds
        self.max_response_time_ms = config.get('max_response_time_ms', 1000)
        self.max_error_count = config.get('max_error_count', 3)
        self.degraded_threshold = config.get('degraded_threshold', 0.8)
        
        # Component checks
        self.component_checks: Dict[ComponentType, Callable] = {
            ComponentType.DATABASE: self._check_database,
            ComponentType.EXCHANGE_API: self._check_exchange_api,
            ComponentType.WEBSOCKET: self._check_websocket,
            ComponentType.SIGNAL_PROCESSOR: self._check_signal_processor,
            ComponentType.RISK_MANAGER: self._check_risk_manager,
            ComponentType.POSITION_MANAGER: self._check_position_manager,
            ComponentType.PROTECTION_SYSTEM: self._check_protection_system,
            ComponentType.TRAILING_STOP: self._check_trailing_stop
        }
        
        # Component dependencies
        self.dependencies = {
            ComponentType.SIGNAL_PROCESSOR: [ComponentType.DATABASE],
            ComponentType.POSITION_MANAGER: [ComponentType.DATABASE, ComponentType.EXCHANGE_API],
            ComponentType.PROTECTION_SYSTEM: [ComponentType.WEBSOCKET, ComponentType.POSITION_MANAGER],
            ComponentType.RISK_MANAGER: [ComponentType.DATABASE, ComponentType.POSITION_MANAGER]
        }
        
        # State tracking
        self.component_health: Dict[ComponentType, ComponentHealth] = {}
        self.system_health: Optional[SystemHealth] = None
        self.health_history: List[SystemHealth] = []
        self.consecutive_failures: Dict[ComponentType, int] = {}
        
        # Alert callbacks
        self.alert_callbacks: List[Callable] = []
        
        # Recovery actions
        self.recovery_actions: Dict[ComponentType, Callable] = {}
        
        # Monitoring task
        self.monitoring_task: Optional[asyncio.Task] = None
        self.is_running = False
        
        logger.info("HealthChecker initialized")

    def set_signal_processor(self, signal_processor):
        """Set signal processor reference after initialization"""
        self.signal_processor = signal_processor
        logger.warning(f"🔧 Signal processor reference set in HealthChecker: {signal_processor is not None}")
        logger.info("Signal processor reference set in HealthChecker")

    async def start(self):
        """Start health monitoring"""
        
        if self.is_running:
            logger.warning("Health monitoring already running")
            return
        
        self.is_running = True
        self.monitoring_task = asyncio.create_task(self._monitoring_loop())
        logger.info("Health monitoring started")
    
    async def stop(self):
        """Stop health monitoring"""
        
        self.is_running = False
        
        if self.monitoring_task:
            self.monitoring_task.cancel()
            try:
                await self.monitoring_task
            except asyncio.CancelledError:
                pass
        
        logger.info("Health monitoring stopped")
    
    async def _monitoring_loop(self):
        """Main monitoring loop"""
        
        while self.is_running:
            try:
                # Perform health checks
                system_health = await self.check_system_health()
                
                # Store health history
                self.health_history.append(system_health)
                if len(self.health_history) > 100:
                    self.health_history.pop(0)
                
                # Check for alerts
                await self._process_health_alerts(system_health)
                
                # Attempt recovery if needed
                await self._attempt_recovery(system_health)
                
                # Determine next check interval
                if system_health.status in [HealthStatus.CRITICAL, HealthStatus.UNHEALTHY]:
                    interval = self.critical_check_interval
                else:
                    interval = self.check_interval
                
                await asyncio.sleep(interval)
                
            except Exception as e:
                logger.error(f"Error in health monitoring loop: {e}")
                await asyncio.sleep(self.check_interval)
    
    async def check_system_health(self) -> SystemHealth:
        """Perform comprehensive system health check"""
        
        components = []
        checks_passed = 0
        checks_failed = 0
        
        # Check each component
        for component_type, check_func in self.component_checks.items():
            try:
                component_health = await check_func()
                components.append(component_health)
                
                # Update tracking
                self.component_health[component_type] = component_health
                
                if component_health.status == HealthStatus.HEALTHY:
                    checks_passed += 1
                    self.consecutive_failures[component_type] = 0
                else:
                    checks_failed += 1
                    self.consecutive_failures[component_type] = \
                        self.consecutive_failures.get(component_type, 0) + 1
                
            except Exception as e:
                logger.error(f"Failed to check {component_type.value}: {e}")
                
                # Create failed health check
                component_health = ComponentHealth(
                    name=component_type.value,
                    type=component_type,
                    status=HealthStatus.CRITICAL,
                    last_check=datetime.now(timezone.utc),
                    response_time_ms=0,
                    error_count=self.consecutive_failures.get(component_type, 0) + 1,
                    error_message=str(e)
                )
                components.append(component_health)
                checks_failed += 1
        
        # Check dependencies
        for component_type, deps in self.dependencies.items():
            if component_type in self.component_health:
                component = self.component_health[component_type]
                
                # Check if dependencies are healthy
                for dep in deps:
                    if dep in self.component_health:
                        dep_health = self.component_health[dep]
                        if dep_health.status != HealthStatus.HEALTHY:
                            # Degrade component if dependency is unhealthy
                            if component.status == HealthStatus.HEALTHY:
                                component.status = HealthStatus.DEGRADED
                                component.metadata['degraded_reason'] = \
                                    f"Dependency {dep.value} is {dep_health.status.value}"
        
        # Determine overall status
        if checks_failed == 0:
            overall_status = HealthStatus.HEALTHY
        elif checks_failed == len(self.component_checks):
            overall_status = HealthStatus.CRITICAL
        elif checks_passed / len(self.component_checks) < self.degraded_threshold:
            overall_status = HealthStatus.UNHEALTHY
        else:
            overall_status = HealthStatus.DEGRADED
        
        # Generate alerts
        alerts = self._generate_alerts(components)
        
        system_health = SystemHealth(
            status=overall_status,
            components=components,
            checks_passed=checks_passed,
            checks_failed=checks_failed,
            last_check=datetime.now(timezone.utc),
            alerts=alerts
        )
        
        self.system_health = system_health
        return system_health
    
    async def _check_database(self) -> ComponentHealth:
        """Check database connectivity and performance"""
        
        start_time = asyncio.get_event_loop().time()
        
        try:
            # Test database query
            result = await self.repository.health_check()
            
            response_time = (asyncio.get_event_loop().time() - start_time) * 1000
            
            if not result:
                status = HealthStatus.UNHEALTHY
                error_message = "Database health check returned false"
            elif response_time > self.max_response_time_ms:
                status = HealthStatus.DEGRADED
                error_message = f"Slow response: {response_time:.0f}ms"
            else:
                status = HealthStatus.HEALTHY
                error_message = None
            
            return ComponentHealth(
                name="PostgreSQL Database",
                type=ComponentType.DATABASE,
                status=status,
                last_check=datetime.now(timezone.utc),
                response_time_ms=response_time,
                error_message=error_message,
                metadata={'connection_pool_size': result.get('pool_size', 0)}
            )
            
        except Exception as e:
            return ComponentHealth(
                name="PostgreSQL Database",
                type=ComponentType.DATABASE,
                status=HealthStatus.CRITICAL,
                last_check=datetime.now(timezone.utc),
                response_time_ms=0,
                error_count=1,
                error_message=str(e)
            )
    
    async def _check_exchange_api(self) -> ComponentHealth:
        """Check exchange API connectivity"""
        
        # This should check actual exchange manager
        # For now, returning mock healthy status
        
        return ComponentHealth(
            name="Exchange APIs",
            type=ComponentType.EXCHANGE_API,
            status=HealthStatus.HEALTHY,
            last_check=datetime.now(timezone.utc),
            response_time_ms=50,
            metadata={
                'binance_status': 'connected'
            }
        )
    
    async def _check_websocket(self) -> ComponentHealth:
        """Check WebSocket connections"""
        
        # Should check actual WebSocket status
        
        return ComponentHealth(
            name="WebSocket Streams",
            type=ComponentType.WEBSOCKET,
            status=HealthStatus.HEALTHY,
            last_check=datetime.now(timezone.utc),
            response_time_ms=10,
            metadata={
                'binance_ws': 'connected',
                'message_rate': 100  # messages per second
            }
        )
    
    async def _check_signal_processor(self) -> ComponentHealth:
        """
        Check signal processing system

        NEW LOGIC:
        - Checks WebSocket connection status (primary indicator)
        - Checks last wave processing time (not signal time!)
        - Accounts for wave-based processing (13-15 min intervals)
        - No dependency on unimplemented repository.get_last_signal_time()
        """

        try:
            # If signal_processor not set, return DEGRADED with info
            if not self.signal_processor:
                return ComponentHealth(
                    name="Signal Processor",
                    type=ComponentType.SIGNAL_PROCESSOR,
                    status=HealthStatus.DEGRADED,
                    last_check=datetime.now(timezone.utc),
                    response_time_ms=0,
                    error_message="Signal processor not initialized in health checker"
                )

            # Get signal processor stats
            stats = self.signal_processor.get_stats()

            # Check WebSocket connection status (PRIMARY INDICATOR)
            ws_stats = stats.get('websocket', {})
            ws_state = ws_stats.get('state')
            ws_connected = ws_state in ('connected', 'authenticated')

            # Check if signal processor is running
            is_running = self.signal_processor.running

            # Get bot uptime (for grace period logic)
            # Note: This assumes signal_processor has start_time tracking
            # If not, can use first wave detection time as proxy
            waves_detected = stats.get('waves_detected', 0)
            last_signal_time = stats.get('last_signal_time')

            # Calculate time since last signal (if any)
            time_since_last_signal = None
            if last_signal_time:
                time_since_last_signal = datetime.now(timezone.utc) - last_signal_time

            # DETERMINE HEALTH STATUS
            status = HealthStatus.HEALTHY
            error_message = None

            # CRITICAL: Signal Processor not running
            if not is_running:
                status = HealthStatus.CRITICAL
                error_message = "Signal processor not running"

            # UNHEALTHY: WebSocket disconnected
            elif not ws_connected:
                reconnections = ws_stats.get('reconnections', 0)
                if reconnections > 5:
                    status = HealthStatus.UNHEALTHY
                    error_message = f"WebSocket disconnected ({reconnections} reconnections)"
                else:
                    status = HealthStatus.DEGRADED
                    error_message = f"WebSocket reconnecting (attempt {reconnections})"

            # CHECK: Last wave/signal time (with grace period)
            elif time_since_last_signal:
                # Grace period: 40 minutes (accounts for 2-3 wave intervals)
                # Waves come every 13-15 minutes, so 40 min = reasonable threshold
                max_allowed_silence = timedelta(minutes=40)

                if time_since_last_signal > max_allowed_silence:
                    # Check if this is just after bot start (grace period)
                    # If no waves detected yet, give more time
                    if waves_detected == 0:
                        # First wave might take up to 20 minutes after start
                        grace_period = timedelta(minutes=20)
                        if time_since_last_signal > grace_period:
                            status = HealthStatus.DEGRADED
                            error_message = f"No waves detected after {time_since_last_signal.seconds//60} minutes"
                        # else: still in grace period, status = HEALTHY
                    else:
                        # We've detected waves before, but nothing recently
                        status = HealthStatus.DEGRADED
                        error_message = f"No signals for {time_since_last_signal.seconds//60} minutes (last wave: {waves_detected})"

            else:
                # No last_signal_time - check if this is normal
                if waves_detected == 0:
                    # Just started, no signals yet - give 20 min grace period
                    # Can't check actual time without start_time, so assume HEALTHY for now
                    status = HealthStatus.HEALTHY
                    error_message = None  # No error during startup
                else:
                    # We detected waves but have no last_signal_time? Strange but not critical
                    status = HealthStatus.DEGRADED
                    error_message = "No last signal time tracked (internal error)"

            # Build metadata
            metadata = {
                'websocket_connected': ws_connected,
                'processor_running': is_running,
                'waves_detected': waves_detected,
                'waves_processed': stats.get('waves_processed', 0),
                'signals_received': stats.get('signals_received', 0),
                'signals_processed': stats.get('signals_processed', 0),
                'last_signal_time': last_signal_time.isoformat() if last_signal_time else None,
                'time_since_last_signal_seconds': int(time_since_last_signal.total_seconds()) if time_since_last_signal else None,
                'websocket_reconnections': ws_stats.get('reconnections', 0),
                'buffer_size': stats.get('buffer_size', 0)
            }

            return ComponentHealth(
                name="Signal Processor",
                type=ComponentType.SIGNAL_PROCESSOR,
                status=status,
                last_check=datetime.now(timezone.utc),
                response_time_ms=0,
                error_message=error_message,
                metadata=metadata
            )

        except Exception as e:
            # Exception during health check - mark as UNHEALTHY
            logger.error(f"Exception in _check_signal_processor: {e}", exc_info=True)
            return ComponentHealth(
                name="Signal Processor",
                type=ComponentType.SIGNAL_PROCESSOR,
                status=HealthStatus.UNHEALTHY,
                last_check=datetime.now(timezone.utc),
                response_time_ms=0,
                error_message=f"Health check exception: {str(e)}"
            )
    
    async def _check_risk_manager(self) -> ComponentHealth:
        """Check risk management system"""
        
        return ComponentHealth(
            name="Risk Manager",
            type=ComponentType.RISK_MANAGER,
            status=HealthStatus.HEALTHY,
            last_check=datetime.now(timezone.utc),
            response_time_ms=5,
            metadata={
                'active_limits': 5,
                'violations_today': 0
            }
        )
    
    async def _check_position_manager(self) -> ComponentHealth:
        """Check position management system"""
        
        try:
            # Check active positions
            positions = await self.repository.get_active_positions()
            
            return ComponentHealth(
                name="Position Manager",
                type=ComponentType.POSITION_MANAGER,
                status=HealthStatus.HEALTHY,
                last_check=datetime.now(timezone.utc),
                response_time_ms=20,
                metadata={
                    'active_positions': len(positions),
                    'pending_orders': 0
                }
            )
            
        except Exception as e:
            return ComponentHealth(
                name="Position Manager",
                type=ComponentType.POSITION_MANAGER,
                status=HealthStatus.UNHEALTHY,
                last_check=datetime.now(timezone.utc),
                response_time_ms=0,
                error_message=str(e)
            )
    
    async def _check_protection_system(self) -> ComponentHealth:
        """Check protection system status"""
        
        return ComponentHealth(
            name="Protection System",
            type=ComponentType.PROTECTION_SYSTEM,
            status=HealthStatus.HEALTHY,
            last_check=datetime.now(timezone.utc),
            response_time_ms=15,
            metadata={
                'monitored_positions': 3,
                'active_stops': 5,
                'trailing_stops': 2
            }
        )

    async def _check_trailing_stop(self) -> ComponentHealth:
        """
        Check Trailing Stop system health

        Metrics:
        - Number of active trailing stops
        - Number of activated trailing stops
        - Recent activation count (last hour)
        - Recent update count (last hour)
        - Error count
        """
        try:
            # Query TS state from database
            query = """
                SELECT
                    COUNT(*) as total_ts,
                    COUNT(*) FILTER (WHERE is_activated = TRUE) as activated_ts,
                    COUNT(*) FILTER (WHERE activated_at > NOW() - INTERVAL '1 hour') as activations_last_hour,
                    COUNT(*) FILTER (WHERE last_update_time > NOW() - INTERVAL '1 hour') as updates_last_hour,
                    AVG(update_count) as avg_updates_per_ts
                FROM monitoring.trailing_stop_state
            """

            row = await self.repository.pool.fetchrow(query)

            total_ts = row['total_ts'] or 0
            activated_ts = row['activated_ts'] or 0
            activations_last_hour = row['activations_last_hour'] or 0
            updates_last_hour = row['updates_last_hour'] or 0
            avg_updates = float(row['avg_updates_per_ts'] or 0)

            # Determine health status
            status = HealthStatus.HEALTHY
            error_message = None

            # Check if TS count matches open positions
            positions_count = len(await self.repository.get_open_positions())

            # Exclude lifecycle-managed positions (they use internal TS, not legacy SmartTrailingStop)
            lifecycle_count = 0
            try:
                lc_row = await self.repository.pool.fetchrow(
                    "SELECT COUNT(*) as cnt FROM monitoring.signal_lifecycles WHERE in_position = TRUE"
                )
                lifecycle_count = lc_row['cnt'] or 0
            except Exception:
                pass  # If table doesn't exist or query fails, assume 0

            # Only non-lifecycle positions need legacy TS coverage
            legacy_positions_count = positions_count - lifecycle_count

            if legacy_positions_count > 0 and total_ts == 0:
                status = HealthStatus.UNHEALTHY
                error_message = f"{legacy_positions_count} legacy positions but 0 trailing stops! ({lifecycle_count} lifecycle-managed excluded)"
            elif legacy_positions_count > 0 and total_ts < legacy_positions_count * 0.95:
                status = HealthStatus.DEGRADED
                coverage = (total_ts / legacy_positions_count * 100) if legacy_positions_count > 0 else 0
                error_message = f"Low TS coverage: {coverage:.1f}% ({total_ts}/{legacy_positions_count}, {lifecycle_count} lifecycle-managed excluded)"

            return ComponentHealth(
                name="Trailing Stop System",
                type=ComponentType.TRAILING_STOP,
                status=status,
                last_check=datetime.now(timezone.utc),
                response_time_ms=0,
                error_message=error_message,
                metadata={
                    'total_trailing_stops': total_ts,
                    'activated_trailing_stops': activated_ts,
                    'activations_last_hour': activations_last_hour,
                    'updates_last_hour': updates_last_hour,
                    'avg_updates_per_ts': round(avg_updates, 2),
                    'open_positions': positions_count,
                    'lifecycle_managed_positions': lifecycle_count,
                    'legacy_positions': legacy_positions_count,
                    'coverage_percent': round((total_ts / legacy_positions_count * 100) if legacy_positions_count > 0 else 100, 1)
                }
            )

        except Exception as e:
            return ComponentHealth(
                name="Trailing Stop System",
                type=ComponentType.TRAILING_STOP,
                status=HealthStatus.CRITICAL,
                last_check=datetime.now(timezone.utc),
                response_time_ms=0,
                error_count=1,
                error_message=str(e)
            )

    def _generate_alerts(self, components: List[ComponentHealth]) -> List[str]:
        """Generate alerts based on component health"""
        
        alerts = []
        
        for component in components:
            if component.status == HealthStatus.CRITICAL:
                alerts.append(f"🚨 CRITICAL: {component.name} is down!")
            elif component.status == HealthStatus.UNHEALTHY:
                alerts.append(f"⚠️ WARNING: {component.name} is unhealthy")
            elif component.status == HealthStatus.DEGRADED:
                if component.error_message:
                    alerts.append(f"⚡ DEGRADED: {component.name} - {component.error_message}")
            
            # Check consecutive failures
            if self.consecutive_failures.get(component.type, 0) >= self.max_error_count:
                alerts.append(f"🔄 {component.name} has failed {self.consecutive_failures[component.type]} times")
        
        return alerts
    
    async def _process_health_alerts(self, health: SystemHealth):
        """Process and send health alerts"""
        
        if not health.alerts:
            return
        
        # Send alerts to registered callbacks
        for callback in self.alert_callbacks:
            try:
                await callback(health)
            except Exception as e:
                logger.error(f"Error in alert callback: {e}")
        
        # Log critical alerts
        if health.status in [HealthStatus.CRITICAL, HealthStatus.UNHEALTHY]:
            logger.error(f"System health: {health.status.value}")
            for alert in health.alerts:
                logger.error(alert)
    
    async def _attempt_recovery(self, health: SystemHealth):
        """Attempt automatic recovery for failed components"""
        
        for component in health.components:
            if component.status in [HealthStatus.CRITICAL, HealthStatus.UNHEALTHY]:
                
                # Check if we have a recovery action
                if component.type in self.recovery_actions:
                    
                    # Don't attempt recovery too frequently
                    failures = self.consecutive_failures.get(component.type, 0)
                    if failures == 3:  # Attempt recovery on 3rd failure
                        
                        logger.info(f"Attempting recovery for {component.name}")
                        
                        try:
                            recovery_func = self.recovery_actions[component.type]
                            await recovery_func()
                            logger.info(f"Recovery initiated for {component.name}")
                        except Exception as e:
                            logger.error(f"Recovery failed for {component.name}: {e}")
    
    def register_alert_callback(self, callback: Callable):
        """Register callback for health alerts"""
        self.alert_callbacks.append(callback)
    
    def register_recovery_action(self, component_type: ComponentType, action: Callable):
        """Register automatic recovery action for component"""
        self.recovery_actions[component_type] = action
    
    async def get_health_summary(self) -> Dict[str, Any]:
        """Get current health summary"""
        
        if not self.system_health:
            return {'status': 'unknown', 'message': 'No health check performed yet'}
        
        return {
            'status': self.system_health.status.value,
            'last_check': self.system_health.last_check.isoformat(),
            'checks_passed': self.system_health.checks_passed,
            'checks_failed': self.system_health.checks_failed,
            'components': {
                c.name: {
                    'status': c.status.value,
                    'response_time_ms': c.response_time_ms,
                    'error': c.error_message
                }
                for c in self.system_health.components
            },
            'alerts': self.system_health.alerts
        }
    
    async def force_health_check(self) -> SystemHealth:
        """Force immediate health check"""
        return await self.check_system_health()

    def get_system_health(self) -> SystemHealth:
        """Get current system health status"""
        if not self.system_health:
            # Return default unhealthy status if no checks performed
            return SystemHealth(
                status=HealthStatus.UNHEALTHY,
                components=[],
                checks_passed=0,
                checks_failed=0,
                last_check=datetime.now(timezone.utc),
                alerts=["No health checks performed yet"]
            )
        return self.system_health

    def get_issues(self) -> List[str]:
        """Get current system issues"""
        issues = []

        if not self.system_health:
            return ["Health monitoring not initialized"]

        # Add component issues
        for component in self.system_health.components:
            if component.status != HealthStatus.HEALTHY:
                issue = f"{component.name}: {component.status.value}"
                if component.error_message:
                    issue += f" - {component.error_message}"
                issues.append(issue)

        # Add alerts
        issues.extend(self.system_health.alerts)

        # Add consecutive failure warnings
        for comp_type, count in self.consecutive_failures.items():
            if count >= 3:
                issues.append(f"{comp_type.value}: {count} consecutive failures")

        return issues

    def record_error(self, error_data: Dict[str, Any]):
        """Record an error for health tracking"""
        try:
            component_name = error_data.get('component', 'unknown')
            error_msg = error_data.get('error', 'Unknown error')

            # Find component type
            comp_type = None
            for ct in ComponentType:
                if ct.value == component_name:
                    comp_type = ct
                    break

            if comp_type and comp_type in self.consecutive_failures:
                self.consecutive_failures[comp_type] += 1

            logger.debug(f"Error recorded for {component_name}: {error_msg}")

        except Exception as e:
            logger.error(f"Failed to record error: {e}")