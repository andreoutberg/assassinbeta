#!/usr/bin/env python3
"""
Redis Performance Tuning Wizard for Liquidation Detector
Analyzes current performance and provides optimization recommendations
"""

import asyncio
import sys
import os
import time
import statistics
from typing import Dict, List, Tuple, Any
import redis.asyncio as redis

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class RedisTuningWizard:
    """Automated Redis performance tuning analyzer"""

    def __init__(self, redis_url: str = "redis://localhost:6379/0"):
        self.redis_url = redis_url
        self.redis = None
        self.recommendations = []
        self.metrics = {}

    async def connect(self):
        """Connect to Redis"""
        self.redis = redis.from_url(self.redis_url, decode_responses=False)

    async def analyze(self):
        """Run complete analysis"""
        print("🔍 Redis Performance Tuning Wizard")
        print("=" * 50)

        # Connect to Redis
        await self.connect()

        # Run analysis steps
        await self.analyze_memory()
        await self.analyze_performance()
        await self.analyze_data_structures()
        await self.analyze_persistence()
        await self.analyze_network()
        await self.run_benchmarks()

        # Generate recommendations
        self.generate_recommendations()

        # Display results
        self.display_results()

    async def analyze_memory(self):
        """Analyze memory usage and efficiency"""
        print("\n📊 Analyzing Memory Usage...")

        info = await self.redis.info('memory')

        used_mb = int(info['used_memory']) / (1024 * 1024)
        peak_mb = int(info['used_memory_peak']) / (1024 * 1024)
        rss_mb = int(info['used_memory_rss']) / (1024 * 1024)
        fragmentation = float(info.get('mem_fragmentation_ratio', 1.0))

        self.metrics['memory'] = {
            'used_mb': used_mb,
            'peak_mb': peak_mb,
            'rss_mb': rss_mb,
            'fragmentation': fragmentation,
            'evicted_keys': int(info.get('evicted_keys', 0)),
            'expired_keys': int(info.get('expired_keys', 0))
        }

        # Check for issues
        if fragmentation > 1.5:
            self.recommendations.append({
                'category': 'Memory',
                'issue': f'High memory fragmentation: {fragmentation:.2f}',
                'recommendation': 'Consider running MEMORY PURGE or restart Redis to defragment',
                'priority': 'Medium'
            })

        if used_mb > 200:  # > 200MB for 256MB limit
            self.recommendations.append({
                'category': 'Memory',
                'issue': f'High memory usage: {used_mb:.1f}MB',
                'recommendation': 'Reduce TTLs, enable more aggressive eviction, or reduce data retention',
                'priority': 'High'
            })

        if self.metrics['memory']['evicted_keys'] > 0:
            self.recommendations.append({
                'category': 'Memory',
                'issue': f'{self.metrics["memory"]["evicted_keys"]} keys evicted',
                'recommendation': 'Memory pressure detected. Review maxmemory-policy and data retention',
                'priority': 'High'
            })

        print(f"  ✓ Memory: {used_mb:.1f}MB / 256MB")
        print(f"  ✓ Fragmentation: {fragmentation:.2f}")

    async def analyze_performance(self):
        """Analyze performance metrics"""
        print("\n⚡ Analyzing Performance...")

        info = await self.redis.info('stats')

        ops_per_sec = info.get('instantaneous_ops_per_sec', 0)
        total_commands = info.get('total_commands_processed', 0)
        hits = info.get('keyspace_hits', 0)
        misses = info.get('keyspace_misses', 0)

        hit_rate = (hits / (hits + misses) * 100) if (hits + misses) > 0 else 0

        self.metrics['performance'] = {
            'ops_per_sec': ops_per_sec,
            'total_commands': total_commands,
            'hit_rate': hit_rate,
            'connected_clients': info.get('connected_clients', 0),
            'blocked_clients': info.get('blocked_clients', 0)
        }

        # Check for issues
        if hit_rate < 80 and (hits + misses) > 1000:
            self.recommendations.append({
                'category': 'Performance',
                'issue': f'Low cache hit rate: {hit_rate:.1f}%',
                'recommendation': 'Review key expiration strategy and access patterns',
                'priority': 'Medium'
            })

        if self.metrics['performance']['blocked_clients'] > 0:
            self.recommendations.append({
                'category': 'Performance',
                'issue': f'{self.metrics["performance"]["blocked_clients"]} blocked clients',
                'recommendation': 'Check for slow operations or blocking commands',
                'priority': 'High'
            })

        print(f"  ✓ Operations/sec: {ops_per_sec}")
        print(f"  ✓ Cache hit rate: {hit_rate:.1f}%")

    async def analyze_data_structures(self):
        """Analyze data structure usage and optimization"""
        print("\n🔧 Analyzing Data Structures...")

        # Sample keys to analyze structure
        cursor = 0
        sample_size = 100
        sampled_keys = []

        while len(sampled_keys) < sample_size and cursor != 0:
            cursor, keys = await self.redis.scan(cursor, count=100)
            sampled_keys.extend(keys[:sample_size - len(sampled_keys)])
            if cursor == 0:
                break

        # Analyze key patterns and types
        type_counts = {}
        size_by_type = {}

        for key in sampled_keys:
            key_type = await self.redis.type(key)
            key_type = key_type.decode() if isinstance(key_type, bytes) else key_type

            if key_type not in type_counts:
                type_counts[key_type] = 0
                size_by_type[key_type] = []

            type_counts[key_type] += 1

            # Get memory usage if available
            try:
                memory_usage = await self.redis.memory_usage(key)
                if memory_usage:
                    size_by_type[key_type].append(memory_usage)
            except:
                pass

        self.metrics['structures'] = {
            'type_counts': type_counts,
            'avg_sizes': {k: statistics.mean(v) if v else 0 for k, v in size_by_type.items()}
        }

        # Check for optimization opportunities
        for key_type, sizes in size_by_type.items():
            if sizes and statistics.mean(sizes) > 10000:  # > 10KB average
                self.recommendations.append({
                    'category': 'Data Structures',
                    'issue': f'Large {key_type} keys: avg {statistics.mean(sizes)/1024:.1f}KB',
                    'recommendation': f'Consider breaking up large {key_type} structures or using compression',
                    'priority': 'Medium'
                })

        print(f"  ✓ Analyzed {len(sampled_keys)} keys")
        print(f"  ✓ Types: {', '.join(f'{k}({v})' for k, v in type_counts.items())}")

    async def analyze_persistence(self):
        """Analyze persistence configuration"""
        print("\n💾 Analyzing Persistence...")

        info = await self.redis.info('persistence')

        aof_enabled = info.get('aof_enabled', 0)
        rdb_saves = info.get('rdb_changes_since_last_save', 0)

        self.metrics['persistence'] = {
            'aof_enabled': aof_enabled,
            'rdb_changes': rdb_saves
        }

        # VPS recommendation: disable persistence
        if aof_enabled:
            self.recommendations.append({
                'category': 'Persistence',
                'issue': 'AOF persistence is enabled',
                'recommendation': 'Disable AOF on VPS to save memory and improve performance',
                'priority': 'High',
                'command': 'CONFIG SET appendonly no'
            })

        print(f"  ✓ AOF: {'Enabled' if aof_enabled else 'Disabled'}")
        print(f"  ✓ RDB changes: {rdb_saves}")

    async def analyze_network(self):
        """Analyze network and client connections"""
        print("\n🌐 Analyzing Network...")

        info = await self.redis.info('clients')

        connected = info.get('connected_clients', 0)
        max_clients = await self.redis.config_get('maxclients')
        max_clients = int(max_clients.get(b'maxclients', 10000))

        self.metrics['network'] = {
            'connected_clients': connected,
            'max_clients': max_clients,
            'client_longest_output_list': info.get('client_longest_output_list', 0),
            'client_biggest_input_buf': info.get('client_biggest_input_buf', 0)
        }

        # Check for issues
        if connected > max_clients * 0.8:
            self.recommendations.append({
                'category': 'Network',
                'issue': f'High client connection usage: {connected}/{max_clients}',
                'recommendation': 'Review connection pooling or increase maxclients',
                'priority': 'Medium'
            })

        print(f"  ✓ Connected clients: {connected}/{max_clients}")

    async def run_benchmarks(self):
        """Run performance benchmarks"""
        print("\n🏃 Running Performance Benchmarks...")

        results = {}

        # Benchmark 1: Single write performance
        print("  • Testing single writes...")
        start = time.time()
        for i in range(1000):
            await self.redis.set(f'bench:single:{i}', b'x' * 100)
        single_write_time = time.time() - start
        single_write_rate = 1000 / single_write_time
        results['single_write_rate'] = single_write_rate

        # Cleanup
        cursor = 0
        while True:
            cursor, keys = await self.redis.scan(cursor, match='bench:single:*', count=100)
            if keys:
                await self.redis.delete(*keys)
            if cursor == 0:
                break

        # Benchmark 2: Pipeline performance
        print("  • Testing pipeline writes...")
        start = time.time()
        pipe = self.redis.pipeline(transaction=False)
        for i in range(1000):
            pipe.set(f'bench:pipe:{i}', b'x' * 100)
        await pipe.execute()
        pipeline_time = time.time() - start
        pipeline_rate = 1000 / pipeline_time
        results['pipeline_write_rate'] = pipeline_rate

        # Cleanup
        cursor = 0
        while True:
            cursor, keys = await self.redis.scan(cursor, match='bench:pipe:*', count=100)
            if keys:
                await self.redis.delete(*keys)
            if cursor == 0:
                break

        # Benchmark 3: Stream performance
        print("  • Testing stream writes...")
        start = time.time()
        for i in range(100):
            await self.redis.xadd(
                'bench:stream',
                {'data': b'x' * 100},
                maxlen=1000,
                approximate=True
            )
        stream_time = time.time() - start
        stream_rate = 100 / stream_time
        results['stream_write_rate'] = stream_rate

        # Cleanup
        await self.redis.delete('bench:stream')

        self.metrics['benchmarks'] = results

        # Check performance
        if single_write_rate < 500:
            self.recommendations.append({
                'category': 'Performance',
                'issue': f'Slow single writes: {single_write_rate:.0f} ops/sec',
                'recommendation': 'Check network latency or consider batching',
                'priority': 'High'
            })

        improvement = pipeline_rate / single_write_rate
        if improvement < 5:
            self.recommendations.append({
                'category': 'Performance',
                'issue': f'Low pipeline improvement: {improvement:.1f}x',
                'recommendation': 'Network latency may be low; pipelining benefits are limited',
                'priority': 'Low'
            })

        print(f"  ✓ Single writes: {single_write_rate:.0f} ops/sec")
        print(f"  ✓ Pipeline writes: {pipeline_rate:.0f} ops/sec ({improvement:.1f}x faster)")
        print(f"  ✓ Stream writes: {stream_rate:.0f} ops/sec")

    def generate_recommendations(self):
        """Generate optimization recommendations based on analysis"""
        # Add general VPS optimizations
        if not any(r['category'] == 'General' for r in self.recommendations):
            self.recommendations.insert(0, {
                'category': 'General',
                'issue': 'VPS Optimization',
                'recommendation': 'Key settings for 256MB VPS: maxmemory 240mb, volatile-ttl policy, disable persistence',
                'priority': 'Info'
            })

        # Sort by priority
        priority_order = {'High': 0, 'Medium': 1, 'Low': 2, 'Info': 3}
        self.recommendations.sort(key=lambda x: priority_order.get(x['priority'], 99))

    def display_results(self):
        """Display analysis results and recommendations"""
        print("\n" + "=" * 50)
        print("📋 ANALYSIS COMPLETE")
        print("=" * 50)

        # Summary metrics
        print("\n📈 Summary Metrics:")
        print(f"  • Memory Usage: {self.metrics['memory']['used_mb']:.1f}MB / 256MB")
        print(f"  • Memory Fragmentation: {self.metrics['memory']['fragmentation']:.2f}")
        print(f"  • Operations/sec: {self.metrics['performance']['ops_per_sec']}")
        print(f"  • Cache Hit Rate: {self.metrics['performance']['hit_rate']:.1f}%")
        print(f"  • Connected Clients: {self.metrics['network']['connected_clients']}")

        # Recommendations
        if self.recommendations:
            print("\n🎯 Optimization Recommendations:")
            print("-" * 50)

            for i, rec in enumerate(self.recommendations, 1):
                priority_colors = {
                    'High': '🔴',
                    'Medium': '🟡',
                    'Low': '🟢',
                    'Info': 'ℹ️'
                }
                icon = priority_colors.get(rec['priority'], '•')

                print(f"\n{i}. {icon} [{rec['category']}] {rec['priority']} Priority")
                print(f"   Issue: {rec['issue']}")
                print(f"   Fix: {rec['recommendation']}")

                if 'command' in rec:
                    print(f"   Command: {rec['command']}")

        else:
            print("\n✅ No critical issues found. Redis is well-optimized!")

        # Performance grade
        grade = self.calculate_grade()
        print("\n" + "=" * 50)
        print(f"Overall Performance Grade: {grade}")
        print("=" * 50)

    def calculate_grade(self) -> str:
        """Calculate overall performance grade"""
        score = 100

        # Deduct points for issues
        for rec in self.recommendations:
            if rec['priority'] == 'High':
                score -= 20
            elif rec['priority'] == 'Medium':
                score -= 10
            elif rec['priority'] == 'Low':
                score -= 5

        # Grade based on score
        if score >= 90:
            return "A+ 🌟 Excellent!"
        elif score >= 80:
            return "A 👍 Very Good"
        elif score >= 70:
            return "B 👌 Good"
        elif score >= 60:
            return "C ⚠️ Needs Improvement"
        else:
            return "D 🔴 Critical Issues"

    async def close(self):
        """Close Redis connection"""
        if self.redis:
            await self.redis.close()


async def main():
    """Run the tuning wizard"""
    import argparse

    parser = argparse.ArgumentParser(description='Redis Performance Tuning Wizard')
    parser.add_argument(
        '--redis-url',
        default='redis://localhost:6379/0',
        help='Redis connection URL'
    )

    args = parser.parse_args()

    wizard = RedisTuningWizard(args.redis_url)

    try:
        await wizard.analyze()
    except Exception as e:
        print(f"\n❌ Error: {e}")
        print("Make sure Redis is running and accessible.")
    finally:
        await wizard.close()


if __name__ == "__main__":
    asyncio.run(main())