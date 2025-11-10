# Multi-Objective Optimization Guide

## Overview

The enhanced Optuna optimizer now supports **multi-objective optimization** using the NSGA-II algorithm, finding Pareto-optimal trading strategies that balance multiple conflicting objectives simultaneously.

## Key Features

### 1. Multi-Objective Optimization (NSGA-II)

Instead of optimizing a single combined score, the system now optimizes three objectives independently:

- **Win Rate (WR)**: Percentage of profitable trades (consistency)
- **Risk/Reward Ratio (RR)**: Average profit vs average loss (profitability)
- **Expected Value (EV)**: Statistical expectation of profit per trade

#### Why Multi-Objective?

Single-objective optimization forces you to pre-define how to weight different metrics (e.g., 60% WR + 40% RR). Multi-objective optimization finds ALL optimal trade-offs (Pareto front), letting you choose based on market conditions.

#### The Pareto Front

A solution is **Pareto-optimal** if no other solution is better in all objectives. The set of all Pareto-optimal solutions forms the **Pareto front**.

Example Pareto-optimal strategies:
- Strategy A: 75% WR, 1.5 RR, 0.025 EV (conservative)
- Strategy B: 60% WR, 2.5 RR, 0.035 EV (balanced)
- Strategy C: 45% WR, 4.0 RR, 0.030 EV (aggressive)

Each is optimal for different risk preferences!

### 2. PostgreSQL Persistence

Studies can now be saved to PostgreSQL for:
- **Resumable optimization**: Continue if interrupted
- **Historical analysis**: Track performance over time
- **Distributed optimization**: Multiple workers on same study

#### Setup

```bash
# Install PostgreSQL adapter
pip install psycopg2-binary

# Set database URL
export DATABASE_URL='postgresql://user:password@localhost:5432/optuna_db'
```

#### Usage

```python
optimizer = OptunaOptimizer(
    storage_url=os.getenv('DATABASE_URL'),
    use_multi_objective=True
)

# Study automatically saved and can be resumed
result = optimizer.optimize_strategy(...)
```

#### Resume a Study

```python
import optuna

# Load existing study
study = optuna.load_study(
    study_name='BTCUSDT_LONG_20240315_143022',
    storage='postgresql://user:pass@localhost/optuna_db'
)

# Continue optimization
study.optimize(objective, n_trials=50)
```

### 3. Comprehensive Visualization Suite

The system generates 10+ interactive visualizations:

#### Core Visualizations

1. **Optimization History**: How objectives improved over trials
2. **Parameter Importance**: Which parameters matter most
3. **Parallel Coordinate**: Relationships between all parameters and objectives
4. **Slice Plot**: How each parameter affects performance
5. **Contour Plots**: 2D parameter interaction heat maps

#### Multi-Objective Specific

6. **2D Pareto Front**: Win Rate vs Risk/Reward trade-offs
7. **3D Pareto Front**: All three objectives in 3D space
8. **Timeline**: When each trial was executed

#### Access Visualizations

```python
# Visualizations auto-generated in:
./optuna_viz/{study_name}/index.html

# Open in browser to explore interactive plots
```

### 4. Intelligent Strategy Selection

From the Pareto front, the system selects 4 diverse strategies for Thompson Sampling:

1. **Highest Win Rate**: Conservative, consistent profits
2. **Highest R/R Ratio**: Aggressive, high reward potential
3. **Highest Expected Value**: Statistically optimal
4. **Most Balanced**: Best combined score

This diversity ensures robust performance across market conditions.

## Usage Examples

### Basic Multi-Objective Optimization

```python
from app.services.optuna_optimizer import OptunaOptimizer

# Create optimizer with multi-objective enabled
optimizer = OptunaOptimizer(
    n_trials=100,
    n_jobs=4,
    use_multi_objective=True  # Enable multi-objective
)

# Run optimization
result = optimizer.optimize_strategy(
    baseline_trades=trades,
    symbol="BTCUSDT",
    direction="LONG"
)

# Access Pareto front
print(f"Found {len(result.pareto_front)} Pareto-optimal solutions")

# Get best for each objective
best_wr = result.best_by_objective['win_rate']
best_rr = result.best_by_objective['rr_ratio']
best_ev = result.best_by_objective['expected_value']
```

### With Persistence

```python
# Enable persistence for resumable optimization
optimizer = OptunaOptimizer(
    n_trials=1000,  # Can be interrupted and resumed
    storage_url='postgresql://user:pass@localhost/optuna_db',
    use_multi_objective=True
)

result = optimizer.optimize_strategy(...)

# Study saved as: result.study_name
# Can be resumed from any machine with same DB access
```

### Integration with Existing System

```python
# Drop-in replacement for grid_search_optimizer
strategies = await run_optuna_grid_search(
    db=db,
    symbol="BTCUSDT",
    direction="LONG",
    webhook_source="tradingview",
    baseline_trades=trades,
    use_multi_objective=True,  # New parameter
    storage_url=DATABASE_URL   # Optional persistence
)

# Returns 4 diverse strategies from Pareto front
for strategy in strategies:
    print(f"{strategy['strategy_profile']}: "
          f"WR={strategy['win_rate']}%, "
          f"RR={strategy['rr_ratio']}")
```

## Interpreting Results

### Understanding the Pareto Front

The Pareto front visualization shows trade-offs:

```
High WR (75%) ←→ Low RR (1.5)
     ↑              ↓
Conservative    Aggressive
     ↓              ↑
Low WR (45%) ←→ High RR (4.0)
```

Choose based on:
- **Market conditions**: Trending vs ranging
- **Account size**: Risk tolerance
- **Time frame**: Scalping vs swing trading

### Parameter Importance

The parameter importance plot shows which settings most affect performance:

```
TP (Take Profit):     ████████████ 65%
SL (Stop Loss):       ████████ 45%
Trailing Type:        ████ 25%
Breakeven:           ██ 15%
```

Focus optimization on high-impact parameters.

### Optimization History

Shows convergence and exploration:
- **Rapid improvement**: Good exploration/exploitation balance
- **Plateau**: May need more trials or different search space
- **Oscillation**: Noisy objective function

## Performance Benefits

### Speed Improvements

- **Grid Search**: 1,215 combinations × ~1s = 20 minutes
- **Single-Objective Optuna**: 100 trials × ~1s = 1.7 minutes (12x faster)
- **Multi-Objective Optuna**: 100 trials × ~1s = 1.7 minutes + Pareto front

### Quality Improvements

- **Grid Search**: Tests predefined combinations
- **Single-Objective**: Finds one "best" based on fixed weights
- **Multi-Objective**: Finds ALL optimal trade-offs

### Practical Benefits

1. **No weight tuning**: Don't need to decide WR vs RR importance
2. **Market adaptation**: Different strategies for different conditions
3. **Risk profiles**: Conservative to aggressive options
4. **Robust backtesting**: Test multiple Pareto-optimal strategies

## Advanced Features

### Custom Objectives

Add custom objectives by modifying the objective function:

```python
def objective(trial):
    # ... run simulation ...

    return [
        result['win_rate'],
        result['rr_ratio'],
        result['expected_value'] * 100,
        result['sharpe_ratio'],  # New objective
        -result['max_drawdown']  # Minimize (negate to maximize)
    ]
```

### Conditional Search Spaces

Use trial suggestions with conditions:

```python
def _suggest_parameters(self, trial):
    tp = trial.suggest_categorical('tp', [1.0, 1.5, 2.0, 3.0])

    # SL depends on TP for minimum RR ratio
    if tp <= 1.5:
        sl = trial.suggest_categorical('sl', [-0.5, -0.75])
    else:
        sl = trial.suggest_categorical('sl', [-0.75, -1.0, -1.5])
```

### Parallel Optimization

Leverage multiple cores or machines:

```python
# Local parallel
optimizer = OptunaOptimizer(n_jobs=-1)  # Use all cores

# Distributed (with PostgreSQL)
# Run on multiple machines with same storage_url
# Each worker pulls trials from shared queue
```

## Troubleshooting

### Common Issues

1. **"No module named 'plotly'"**
   ```bash
   pip install plotly kaleido
   ```

2. **"Cannot connect to PostgreSQL"**
   ```bash
   # Check connection
   psql $DATABASE_URL

   # Create database
   createdb optuna_db
   ```

3. **"Too few Pareto-optimal solutions"**
   - Increase n_trials (try 200+)
   - Adjust population_size in NSGAIISampler
   - Check if objectives are conflicting

### Performance Tuning

- **More trials**: 100-500 for good Pareto front
- **Population size**: 50-100 for NSGA-II
- **Parallel jobs**: Set to CPU cores - 1
- **Timeout**: Set reasonable limit (5-10 minutes)

## Conclusion

The multi-objective optimization upgrade transforms the system from finding a single "best" strategy to discovering the entire landscape of optimal strategies. This provides:

1. **Better strategies**: No compromise on pre-defined weights
2. **More flexibility**: Choose strategy based on conditions
3. **Deeper insights**: Understand parameter relationships
4. **Production ready**: Persistence and monitoring built-in

The system now matches or exceeds capabilities of specialized trading optimization platforms while remaining fully integrated with your existing Phase system.