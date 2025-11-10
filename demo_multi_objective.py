#!/usr/bin/env python3
"""
Demo script showing how to use the enhanced Optuna optimizer with multi-objective optimization.

This demonstrates:
1. Multi-objective optimization with NSGA-II
2. Study persistence to PostgreSQL
3. Comprehensive visualization generation
4. Pareto front analysis
"""

import asyncio
import os
from typing import List, Dict
import logging

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def demo_multi_objective_optimization():
    """
    Demonstrate the new multi-objective optimization capabilities.
    """
    from app.services.optuna_optimizer import OptunaOptimizer, run_optuna_grid_search

    # Example baseline trades for simulation
    baseline_trades = [
        {'entry_price': 100, 'exit_price': 103, 'direction': 'LONG'},
        {'entry_price': 105, 'exit_price': 102, 'direction': 'LONG'},
        {'entry_price': 98, 'exit_price': 101, 'direction': 'LONG'},
        # Add more sample trades...
    ] * 10  # Multiply for more data

    print("=" * 80)
    print("MULTI-OBJECTIVE OPTUNA OPTIMIZATION DEMO")
    print("=" * 80)

    # 1. Basic multi-objective optimization
    print("\n1. BASIC MULTI-OBJECTIVE OPTIMIZATION")
    print("-" * 40)

    optimizer = OptunaOptimizer(
        n_trials=50,  # Reduced for demo
        n_jobs=4,
        timeout=60,  # 1 minute for demo
        use_multi_objective=True  # Enable multi-objective
    )

    print("Running optimization with 3 objectives:")
    print("  - Maximize Win Rate (consistency)")
    print("  - Maximize Risk/Reward Ratio (profitability)")
    print("  - Maximize Expected Value (statistical edge)")

    result = optimizer.optimize_strategy(
        baseline_trades=baseline_trades,
        symbol="BTCUSDT",
        direction="LONG"
    )

    print(f"\nOptimization completed in {result.optimization_time:.1f} seconds")
    print(f"Found {len(result.pareto_front)} Pareto-optimal solutions")

    # Display Pareto front
    if result.pareto_front:
        print("\nTop 5 Pareto-optimal strategies:")
        print("-" * 40)
        for i, strategy in enumerate(result.pareto_front[:5], 1):
            print(f"{i}. TP={strategy['params']['tp']:.2f}%, SL={strategy['params']['sl']:.2f}%")
            print(f"   WR={strategy['objectives']['win_rate']:.1f}%, "
                  f"RR={strategy['objectives']['rr_ratio']:.2f}, "
                  f"EV={strategy['objectives']['expected_value']:.3f}")
            print(f"   Combined Score: {strategy['combined_score']:.2f}")

    # 2. Study persistence with PostgreSQL
    print("\n2. STUDY PERSISTENCE (PostgreSQL)")
    print("-" * 40)

    # Example with persistence (requires PostgreSQL setup)
    storage_url = os.getenv('DATABASE_URL')  # or "postgresql://user:pass@localhost/optuna_db"

    if storage_url:
        print(f"Using storage: {storage_url[:30]}...")

        optimizer_persistent = OptunaOptimizer(
            n_trials=30,
            n_jobs=4,
            timeout=30,
            storage_url=storage_url,
            use_multi_objective=True
        )

        result_persistent = optimizer_persistent.optimize_strategy(
            baseline_trades=baseline_trades,
            symbol="ETHUSDT",
            direction="SHORT"
        )

        print(f"Study saved as: {result_persistent.study_name}")
        print("You can resume this study later or analyze it from another process")
    else:
        print("No DATABASE_URL found. Set it to enable persistence:")
        print("export DATABASE_URL='postgresql://user:pass@localhost/optuna_db'")

    # 3. Compare single vs multi-objective
    print("\n3. SINGLE VS MULTI-OBJECTIVE COMPARISON")
    print("-" * 40)

    # Single-objective
    optimizer_single = OptunaOptimizer(
        n_trials=30,
        n_jobs=4,
        timeout=30,
        use_multi_objective=False  # Single-objective
    )

    result_single = optimizer_single.optimize_strategy(
        baseline_trades=baseline_trades,
        symbol="BTCUSDT",
        direction="LONG"
    )

    print("Single-objective result:")
    print(f"  Best Score: {result_single.best_score:.2f}")
    print(f"  Best WR: {result_single.best_win_rate:.1f}%")
    print(f"  Best RR: {result_single.best_rr:.2f}")

    print("\nMulti-objective results (from earlier):")
    if result.best_by_objective:
        print(f"  Best WR: {result.best_by_objective.get('win_rate', {}).get('value', 0):.1f}%")
        print(f"  Best RR: {result.best_by_objective.get('rr_ratio', {}).get('value', 0):.2f}")
        print(f"  Best EV: {result.best_by_objective.get('expected_value', {}).get('value', 0):.3f}")

    # 4. Using run_optuna_grid_search (integration function)
    print("\n4. INTEGRATION WITH EXISTING SYSTEM")
    print("-" * 40)

    strategies = await run_optuna_grid_search(
        db=None,  # Your database connection
        symbol="BTCUSDT",
        direction="LONG",
        webhook_source="demo",
        baseline_trades=baseline_trades,
        use_multi_objective=True,
        storage_url=storage_url
    )

    print(f"Selected {len(strategies)} diverse strategies for Thompson Sampling:")
    for i, strat in enumerate(strategies, 1):
        profile = strat.get('strategy_profile', 'unknown')
        print(f"{i}. {profile}: WR={strat['win_rate']:.1f}%, "
              f"RR={strat['rr_ratio']:.2f}, Score={strat['quality_score']:.2f}")

    print("\n" + "=" * 80)
    print("DEMO COMPLETE")
    print("=" * 80)


def main():
    """
    Main entry point for the demo.
    """
    print("\n" + "=" * 80)
    print("OPTUNA MULTI-OBJECTIVE OPTIMIZATION DEMO")
    print("World-Class Strategy Discovery System")
    print("=" * 80)

    print("\nFeatures demonstrated:")
    print("1. Multi-objective optimization (Pareto front discovery)")
    print("2. PostgreSQL persistence for resumable studies")
    print("3. Comprehensive visualization suite")
    print("4. Diverse strategy selection from Pareto front")

    # Run the async demo
    asyncio.run(demo_multi_objective_optimization())

    print("\nTo view visualizations:")
    print("1. Check ./optuna_viz/*/index.html for interactive plots")
    print("2. Open in browser to explore:")
    print("   - Pareto front (trade-offs between objectives)")
    print("   - Parameter importance")
    print("   - Optimization history")
    print("   - Parameter relationships")

    print("\nNext steps:")
    print("1. Set DATABASE_URL for persistence")
    print("2. Install plotly for visualizations: pip install plotly kaleido")
    print("3. Use optuna-dashboard for live monitoring: pip install optuna-dashboard")


if __name__ == "__main__":
    main()