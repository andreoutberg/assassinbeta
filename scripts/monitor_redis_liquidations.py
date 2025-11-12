#!/usr/bin/env python3
"""
Redis Liquidation Monitor - Real-time monitoring dashboard for VPS
Tracks memory usage, liquidation stats, and performance metrics
"""

import asyncio
import sys
import os
import time
from datetime import datetime, timedelta
from typing import Dict, List, Any
import redis.asyncio as redis
from rich.console import Console
from rich.table import Table
from rich.live import Live
from rich.layout import Layout
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn
from rich.text import Text
from rich.align import Align

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.services.redis_liquidation_manager import OptimizedRedisManager


class RedisMonitorDashboard:
    """Real-time monitoring dashboard for Redis liquidation data"""

    def __init__(self, redis_url: str = "redis://localhost:6379/0"):
        self.console = Console()
        self.manager = OptimizedRedisManager(redis_url)
        self.redis = None
        self.running = True
        self.refresh_interval = 1  # seconds

        # Monitoring data
        self.memory_history = []
        self.liquidation_counts = {}
        self.performance_metrics = {}
        self.alerts = []

    async def connect(self):
        """Initialize connections"""
        await self.manager.connect()
        self.redis = self.manager.redis

    def create_layout(self) -> Layout:
        """Create the dashboard layout"""
        layout = Layout()

        layout.split(
            Layout(name="header", size=3),
            Layout(name="main", ratio=1),
            Layout(name="footer", size=4)
        )

        layout["main"].split_row(
            Layout(name="left", ratio=1),
            Layout(name="right", ratio=1)
        )

        layout["left"].split(
            Layout(name="memory", ratio=1),
            Layout(name="performance", ratio=1)
        )

        layout["right"].split(
            Layout(name="liquidations", ratio=1),
            Layout(name="alerts", ratio=1)
        )

        return layout

    async def update_memory_panel(self) -> Panel:
        """Update memory usage panel"""
        try:
            # Get memory stats
            stats = await self.manager.get_memory_stats()
            info = await self.redis.info('memory')

            # Calculate additional metrics
            fragmentation = float(info.get('mem_fragmentation_ratio', 1.0))
            evicted = int(info.get('evicted_keys', 0))
            expired = int(info.get('expired_keys', 0))

            # Create memory table
            table = Table(title="Memory Usage", show_header=True, header_style="bold cyan")
            table.add_column("Metric", style="dim", width=20)
            table.add_column("Value", justify="right")
            table.add_column("Status", justify="center", width=10)

            # Memory usage with color coding
            used_pct = stats.get('used_pct', 0)
            if used_pct > 85:
                usage_style = "bold red"
                status = "⚠️ CRITICAL"
            elif used_pct > 75:
                usage_style = "bold yellow"
                status = "⚠️ WARNING"
            else:
                usage_style = "bold green"
                status = "✅ OK"

            table.add_row(
                "Used Memory",
                f"{stats.get('used_mb', 0):.1f} MB ({used_pct:.1f}%)",
                f"[{usage_style}]{status}[/{usage_style}]"
            )

            table.add_row(
                "Peak Memory",
                f"{stats.get('peak_mb', 0):.1f} MB",
                ""
            )

            table.add_row(
                "RSS Memory",
                f"{stats.get('rss_mb', 0):.1f} MB",
                ""
            )

            # Fragmentation with color coding
            frag_status = "🔴" if fragmentation > 1.5 else "🟢"
            table.add_row(
                "Fragmentation",
                f"{fragmentation:.2f}",
                frag_status
            )

            table.add_row(
                "Evicted Keys",
                str(evicted),
                "🔴" if evicted > 0 else "🟢"
            )

            table.add_row(
                "Expired Keys",
                str(expired),
                ""
            )

            table.add_row(
                "Storage Mode",
                stats.get('storage_mode', 'normal').upper(),
                ""
            )

            # Add memory bar
            memory_bar = self.create_memory_bar(used_pct)
            table.add_row("", "", "")
            table.add_row("Memory Bar", memory_bar, "")

            return Panel(table, border_style="cyan", title="📊 Memory Monitor")

        except Exception as e:
            return Panel(f"Error: {e}", border_style="red", title="Memory Monitor")

    def create_memory_bar(self, used_pct: float) -> str:
        """Create a visual memory usage bar"""
        bar_width = 30
        filled = int(bar_width * used_pct / 100)
        empty = bar_width - filled

        if used_pct > 85:
            bar_char = "█"
            empty_char = "░"
            color = "red"
        elif used_pct > 75:
            bar_char = "█"
            empty_char = "░"
            color = "yellow"
        else:
            bar_char = "█"
            empty_char = "░"
            color = "green"

        bar = f"[{color}]{bar_char * filled}[/{color}]{empty_char * empty}"
        return bar

    async def update_performance_panel(self) -> Panel:
        """Update performance metrics panel"""
        try:
            info = await self.redis.info('stats', 'commandstats')

            # Create performance table
            table = Table(title="Performance Metrics", show_header=True, header_style="bold magenta")
            table.add_column("Metric", style="dim", width=20)
            table.add_column("Value", justify="right")

            # Operations per second
            ops_per_sec = info.get('instantaneous_ops_per_sec', 0)
            table.add_row(
                "Ops/Second",
                f"{ops_per_sec:,.0f}"
            )

            # Network I/O
            input_kb = info.get('instantaneous_input_kbps', 0)
            output_kb = info.get('instantaneous_output_kbps', 0)
            table.add_row(
                "Network In",
                f"{input_kb:.1f} KB/s"
            )
            table.add_row(
                "Network Out",
                f"{output_kb:.1f} KB/s"
            )

            # Hit rate
            hits = info.get('keyspace_hits', 0)
            misses = info.get('keyspace_misses', 0)
            total = hits + misses
            hit_rate = (hits / total * 100) if total > 0 else 0
            table.add_row(
                "Cache Hit Rate",
                f"{hit_rate:.1f}%"
            )

            # Connected clients
            clients = info.get('connected_clients', 0)
            blocked = info.get('blocked_clients', 0)
            table.add_row(
                "Connected Clients",
                str(clients)
            )
            table.add_row(
                "Blocked Clients",
                str(blocked)
            )

            # Total commands processed
            total_commands = info.get('total_commands_processed', 0)
            table.add_row(
                "Total Commands",
                f"{total_commands:,}"
            )

            return Panel(table, border_style="magenta", title="⚡ Performance")

        except Exception as e:
            return Panel(f"Error: {e}", border_style="red", title="Performance")

    async def update_liquidations_panel(self) -> Panel:
        """Update liquidations statistics panel"""
        try:
            # Get active symbols
            symbols = await self._get_top_symbols(limit=5)

            # Create liquidations table
            table = Table(title="Liquidation Activity", show_header=True, header_style="bold yellow")
            table.add_column("Symbol", style="cyan", width=10)
            table.add_column("Count", justify="right", width=8)
            table.add_column("Volume", justify="right", width=12)
            table.add_column("Buy/Sell", justify="center", width=10)
            table.add_column("P80 Size", justify="right", width=10)

            for symbol in symbols:
                # Get stats for each symbol
                stats = await self.manager.get_liquidation_stats(symbol, window_minutes=60)

                total_count = stats.get('total_count', 0)
                total_volume = stats.get('total_volume', 0)
                buy_count = stats.get('buy_count', 0)
                sell_count = stats.get('sell_count', 0)
                p80 = stats.get('percentile_80', 0) or 0

                # Buy/Sell ratio with color
                if buy_count > sell_count:
                    ratio_text = f"[green]↑{buy_count}/{sell_count}[/green]"
                elif sell_count > buy_count:
                    ratio_text = f"[red]↓{buy_count}/{sell_count}[/red]"
                else:
                    ratio_text = f"[yellow]={buy_count}/{sell_count}[/yellow]"

                table.add_row(
                    symbol,
                    str(total_count),
                    f"${total_volume:,.0f}",
                    ratio_text,
                    f"${p80:,.0f}"
                )

            # Add summary row
            table.add_row("", "", "", "", "")

            # Get global stats
            cursor = 0
            total_streams = 0
            total_entries = 0

            while True:
                cursor, keys = await self.redis.scan(
                    cursor,
                    match='liq:*',
                    count=100
                )

                for key in keys:
                    total_streams += 1
                    length = await self.redis.xlen(key)
                    total_entries += length

                if cursor == 0:
                    break

            table.add_row(
                "[bold]TOTAL[/bold]",
                f"[bold]{total_entries}[/bold]",
                f"[bold]{total_streams} streams[/bold]",
                "",
                ""
            )

            return Panel(table, border_style="yellow", title="📈 Liquidations (60m)")

        except Exception as e:
            return Panel(f"Error: {e}", border_style="red", title="Liquidations")

    async def update_alerts_panel(self) -> Panel:
        """Update alerts and warnings panel"""
        try:
            alerts = []
            now = datetime.now()

            # Check memory alerts
            stats = await self.manager.get_memory_stats()
            used_pct = stats.get('used_pct', 0)

            if used_pct > 90:
                alerts.append({
                    'level': 'CRITICAL',
                    'message': f'Memory usage critical: {used_pct:.1f}%',
                    'time': now,
                    'color': 'red'
                })
            elif used_pct > 80:
                alerts.append({
                    'level': 'WARNING',
                    'message': f'Memory usage high: {used_pct:.1f}%',
                    'time': now,
                    'color': 'yellow'
                })

            # Check evictions
            info = await self.redis.info('memory')
            evicted = int(info.get('evicted_keys', 0))
            if evicted > 0:
                alerts.append({
                    'level': 'WARNING',
                    'message': f'{evicted} keys evicted due to memory pressure',
                    'time': now,
                    'color': 'yellow'
                })

            # Check fragmentation
            fragmentation = float(info.get('mem_fragmentation_ratio', 1.0))
            if fragmentation > 1.5:
                alerts.append({
                    'level': 'INFO',
                    'message': f'High memory fragmentation: {fragmentation:.2f}',
                    'time': now,
                    'color': 'cyan'
                })

            # Storage mode alert
            if stats.get('storage_mode') == 'critical':
                alerts.append({
                    'level': 'CRITICAL',
                    'message': 'Operating in CRITICAL storage mode',
                    'time': now,
                    'color': 'red'
                })
            elif stats.get('storage_mode') == 'optimized':
                alerts.append({
                    'level': 'INFO',
                    'message': 'Operating in OPTIMIZED storage mode',
                    'time': now,
                    'color': 'cyan'
                })

            # Create alerts display
            if alerts:
                alert_text = ""
                for alert in alerts[-5:]:  # Show last 5 alerts
                    color = alert['color']
                    level = alert['level']
                    message = alert['message']
                    time_str = alert['time'].strftime('%H:%M:%S')

                    alert_text += f"[{color}][{time_str}] {level}: {message}[/{color}]\n"

                return Panel(
                    Text(alert_text.strip()),
                    border_style="red" if any(a['level'] == 'CRITICAL' for a in alerts) else "yellow",
                    title="⚠️ Alerts"
                )
            else:
                return Panel(
                    Text("✅ All systems operational", style="green"),
                    border_style="green",
                    title="✅ Status"
                )

        except Exception as e:
            return Panel(f"Error: {e}", border_style="red", title="Alerts")

    def create_header(self) -> Panel:
        """Create dashboard header"""
        header_text = Text.assemble(
            ("Redis Liquidation Monitor", "bold cyan"),
            " | ",
            ("VPS Optimized (256MB)", "yellow"),
            " | ",
            (f"Updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", "dim")
        )
        return Panel(
            Align.center(header_text),
            border_style="cyan"
        )

    def create_footer(self) -> Panel:
        """Create dashboard footer with controls"""
        footer_text = """
[bold cyan]Controls:[/bold cyan]
[yellow]Q[/yellow] - Quit | [yellow]C[/yellow] - Clear Old Data | [yellow]R[/yellow] - Reset Stats | [yellow]+/-[/yellow] - Change Refresh Rate
[dim]Refresh Rate: {}s | Press Ctrl+C to exit[/dim]
        """.format(self.refresh_interval).strip()

        return Panel(
            Text(footer_text),
            border_style="dim"
        )

    async def _get_top_symbols(self, limit: int = 5) -> List[str]:
        """Get top symbols by activity"""
        symbols = []
        symbol_counts = {}

        # Scan for liquidation streams
        cursor = 0
        while True:
            cursor, keys = await self.redis.scan(
                cursor,
                match='liq:*',
                count=100
            )

            for key in keys:
                symbol = key.decode().split(':')[-1]
                length = await self.redis.xlen(key)
                symbol_counts[symbol] = length

            if cursor == 0:
                break

        # Sort by count and return top N
        sorted_symbols = sorted(symbol_counts.items(), key=lambda x: x[1], reverse=True)
        return [symbol for symbol, _ in sorted_symbols[:limit]]

    async def run_dashboard(self):
        """Main dashboard loop"""
        layout = self.create_layout()

        with Live(layout, refresh_per_second=1, console=self.console) as live:
            while self.running:
                try:
                    # Update all panels
                    layout["header"].update(self.create_header())
                    layout["memory"].update(await self.update_memory_panel())
                    layout["performance"].update(await self.update_performance_panel())
                    layout["liquidations"].update(await self.update_liquidations_panel())
                    layout["alerts"].update(await self.update_alerts_panel())
                    layout["footer"].update(self.create_footer())

                    # Sleep for refresh interval
                    await asyncio.sleep(self.refresh_interval)

                except KeyboardInterrupt:
                    self.running = False
                    break
                except Exception as e:
                    self.console.print(f"[red]Dashboard error: {e}[/red]")
                    await asyncio.sleep(1)

    async def cleanup_data(self):
        """Trigger data cleanup"""
        self.console.print("[yellow]Starting data cleanup...[/yellow]")
        await self.manager.cleanup_old_data(aggressive=False)
        self.console.print("[green]Cleanup completed![/green]")

    async def run(self):
        """Main entry point"""
        await self.connect()

        self.console.print("[cyan]Starting Redis Liquidation Monitor...[/cyan]")
        self.console.print("[dim]Connecting to Redis...[/dim]")

        try:
            # Test connection
            await self.redis.ping()
            self.console.print("[green]✓ Connected to Redis[/green]")

            # Run dashboard
            await self.run_dashboard()

        except Exception as e:
            self.console.print(f"[red]Failed to start monitor: {e}[/red]")
        finally:
            await self.manager.close()
            self.console.print("[yellow]Monitor stopped.[/yellow]")


async def main():
    """Main entry point"""
    import argparse

    parser = argparse.ArgumentParser(description='Redis Liquidation Monitor')
    parser.add_argument(
        '--redis-url',
        default='redis://localhost:6379/0',
        help='Redis connection URL'
    )
    parser.add_argument(
        '--refresh',
        type=int,
        default=1,
        help='Refresh interval in seconds'
    )

    args = parser.parse_args()

    dashboard = RedisMonitorDashboard(args.redis_url)
    dashboard.refresh_interval = args.refresh

    await dashboard.run()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n[yellow]Monitor stopped by user[/yellow]")