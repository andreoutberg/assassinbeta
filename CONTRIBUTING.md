# Contributing to Andre Assassin

First off, thank you for considering contributing to Andre Assassin! 🎉

It's people like you that make Andre Assassin such a great tool for the trading community.

## 📋 Table of Contents

- [Code of Conduct](#code-of-conduct)
- [How Can I Contribute?](#how-can-i-contribute)
- [Development Setup](#development-setup)
- [Pull Request Process](#pull-request-process)
- [Coding Standards](#coding-standards)
- [Testing Guidelines](#testing-guidelines)
- [Documentation](#documentation)
- [Community](#community)

---

## 📜 Code of Conduct

This project and everyone participating in it is governed by our [Code of Conduct](CODE_OF_CONDUCT.md). By participating, you are expected to uphold this code. Please report unacceptable behavior to support@andreassassin.com.

---

## 🤝 How Can I Contribute?

### 🐛 Reporting Bugs

**Before submitting a bug report:**
- Check the [documentation](README.md) to see if it's expected behavior
- Search [existing issues](https://github.com/andreoutberg/assassinbeta/issues) to avoid duplicates
- Collect relevant information (logs, screenshots, environment details)

**How to submit a good bug report:**

Use our bug report template and include:
- **Clear title** - Describe the issue concisely
- **Steps to reproduce** - Exact steps to trigger the bug
- **Expected behavior** - What should happen
- **Actual behavior** - What actually happens
- **Environment** - OS, Python version, Docker version, etc.
- **Logs** - Relevant error messages or logs
- **Screenshots** - If applicable

Example:
```markdown
**Bug:** WebSocket disconnects after 5 minutes

**Steps to reproduce:**
1. Start system with `docker-compose up -d`
2. Open dashboard at http://localhost:3000
3. Wait 5 minutes
4. Observe WebSocket status in console

**Expected:** WebSocket stays connected

**Actual:** Shows "Disconnected" after ~5 minutes

**Environment:**
- OS: Ubuntu 22.04
- Python: 3.11.6
- Docker: 24.0.5
- Browser: Chrome 120

**Logs:**
```
[ERROR] WebSocket timeout after 300s
[ERROR] Connection closed: code=1006
```
```

### 💡 Suggesting Enhancements

**Before suggesting an enhancement:**
- Check if it already exists in [discussions](https://github.com/andreoutberg/assassinbeta/discussions)
- Review the [roadmap](README.md#-roadmap) to see if it's planned
- Consider if it fits the project's goals (high win-rate trading focus)

**How to suggest an enhancement:**

Use our feature request template and include:
- **Clear title** - Concise feature description
- **Problem statement** - What problem does this solve?
- **Proposed solution** - How should it work?
- **Alternatives** - What other solutions did you consider?
- **Benefits** - Who benefits and how?
- **Implementation complexity** - Easy/Medium/Hard (if you know)

### 📝 Improving Documentation

Documentation improvements are always welcome!

**Areas that need help:**
- Beginner tutorials
- API documentation
- Architecture diagrams
- Trading strategy examples
- Troubleshooting guides
- Translation to other languages

**How to contribute docs:**
1. Fork the repository
2. Edit markdown files in `docs/` or root directory
3. Preview locally to ensure formatting is correct
4. Submit a pull request

### 💻 Contributing Code

**Types of code contributions we need:**
- **Bug fixes** - Fix known issues
- **New features** - Implement roadmap items
- **Performance** - Optimize slow code
- **Testing** - Add/improve test coverage
- **Refactoring** - Clean up technical debt
- **Integrations** - New exchanges, indicators, etc.

**Before you start coding:**
1. Comment on the issue you want to work on (or create one)
2. Wait for maintainer approval to avoid duplicate work
3. Fork the repository
4. Create a feature branch

---

## 🛠️ Development Setup

### Prerequisites

- **Python 3.11+**
- **Docker & Docker Compose**
- **Git**
- **Node.js 18+** (for frontend)
- **PostgreSQL 16** (or use Docker)

### Local Development Setup

```bash
# 1. Fork and clone
git clone https://github.com/YOUR_USERNAME/assassinbeta.git
cd assassinbeta

# 2. Create virtual environment
python3.11 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt
pip install -r requirements-dev.txt  # Testing & linting tools

# 4. Set up environment
cp .env.example .env
# Edit .env with your configuration

# 5. Start database
docker-compose up -d postgres redis

# 6. Run migrations
python -m alembic upgrade head

# 7. Start backend (development mode)
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# 8. Start frontend (in another terminal)
cd frontend
npm install
npm run dev
```

### Running with Docker (Recommended)

```bash
# Start everything
docker-compose -f docker-compose.dev.yml up --build

# View logs
docker-compose logs -f backend

# Access shell
docker-compose exec backend bash
```

### Database Management

```bash
# Create migration
alembic revision --autogenerate -m "Description"

# Apply migrations
alembic upgrade head

# Rollback
alembic downgrade -1

# Access database
docker-compose exec postgres psql -U trading -d high_wr_db
```

---

## 🔄 Pull Request Process

### 1. Create a Feature Branch

```bash
git checkout -b feature/amazing-feature
# Or for bug fixes:
git checkout -b fix/issue-123
```

**Branch naming conventions:**
- `feature/` - New features
- `fix/` - Bug fixes
- `docs/` - Documentation
- `test/` - Test improvements
- `refactor/` - Code refactoring
- `perf/` - Performance improvements

### 2. Make Your Changes

- **Write clean code** - Follow our style guide
- **Add tests** - Cover your changes
- **Update docs** - If you change APIs or behavior
- **Commit often** - Small, logical commits

### 3. Test Your Changes

```bash
# Run backend tests
pytest tests/ -v --cov=app --cov-report=html

# Run frontend tests
cd frontend && npm test

# Run linting
black app/ --check
flake8 app/
mypy app/

# Run type checking
cd frontend && npm run type-check

# Run integration tests
pytest tests/integration/ -v
```

### 4. Commit Your Changes

Follow [Conventional Commits](https://www.conventionalcommits.org/):

```bash
git commit -m "feat: add Optuna optimization for faster grid search"
git commit -m "fix: resolve WebSocket disconnection after 5 minutes"
git commit -m "docs: update README with TradingView integration steps"
git commit -m "test: add unit tests for signal quality analyzer"
```

**Commit types:**
- `feat` - New feature
- `fix` - Bug fix
- `docs` - Documentation
- `test` - Testing
- `refactor` - Code refactoring
- `perf` - Performance improvement
- `style` - Code style (formatting, etc.)
- `chore` - Maintenance tasks

### 5. Push and Create Pull Request

```bash
git push origin feature/amazing-feature
```

Then on GitHub:
1. Click "Compare & pull request"
2. Fill out the PR template
3. Link related issues (e.g., "Closes #123")
4. Request review from maintainers

### 6. Code Review Process

**What to expect:**
- Maintainer will review within 2-3 days
- May request changes or ask questions
- CI/CD tests must pass
- At least one approval required

**After approval:**
- Maintainer will merge your PR
- Your changes will be in the next release!
- You'll be added to contributors list 🎉

---

## 📏 Coding Standards

### Python Style Guide

We follow [PEP 8](https://peps.python.org/pep-0008/) with some modifications:

```python
# Good
def calculate_win_rate(
    trades: List[Trade],
    min_trades: int = 30
) -> float:
    """
    Calculate win rate from list of trades.

    Args:
        trades: List of trade objects
        min_trades: Minimum trades required for valid calculation

    Returns:
        Win rate as percentage (0-100)

    Raises:
        ValueError: If insufficient trades
    """
    if len(trades) < min_trades:
        raise ValueError(f"Need at least {min_trades} trades")

    wins = sum(1 for t in trades if t.pnl > 0)
    return (wins / len(trades)) * 100


# Bad
def calc_wr(t, m=30):
    if len(t) < m: raise ValueError("not enough")
    w = 0
    for trade in t:
        if trade.pnl > 0: w += 1
    return (w / len(t)) * 100
```

**Key principles:**
- **Type hints** - Always use type annotations
- **Docstrings** - Document all public functions
- **Descriptive names** - No abbreviations unless obvious
- **Max line length** - 88 characters (Black formatter)
- **Async/await** - Use for I/O operations
- **Error handling** - Explicit exception handling

### TypeScript/React Style Guide

```typescript
// Good
interface TradePosition {
  id: number;
  symbol: string;
  direction: 'LONG' | 'SHORT';
  entryPrice: number;
  currentPnl: number;
}

const PositionCard: React.FC<{ position: TradePosition }> = ({ position }) => {
  const pnlColor = position.currentPnl >= 0 ? 'green.500' : 'red.500';

  return (
    <Box borderWidth="1px" borderRadius="lg" p={4}>
      <Heading size="md">{position.symbol}</Heading>
      <Text color={pnlColor}>
        {position.currentPnl.toFixed(2)} USDT
      </Text>
    </Box>
  );
};


// Bad
const card = (p: any) => {
  let c = p.currentPnl >= 0 ? 'green.500' : 'red.500';
  return <Box><Heading>{p.symbol}</Heading><Text color={c}>{p.currentPnl}</Text></Box>
}
```

**Key principles:**
- **TypeScript** - No `any` types
- **Functional components** - Use hooks, not classes
- **Props interfaces** - Define all prop types
- **Meaningful names** - Clear component/variable names
- **Small components** - Single responsibility

### Code Organization

```
app/
├── api/              # FastAPI routes
│   ├── routes/
│   └── dependencies.py
├── core/             # Core business logic
│   ├── phase_manager.py
│   └── strategy_optimizer.py
├── database/         # Database models & migrations
│   ├── models/
│   └── schemas/
├── services/         # External services (Bybit, etc.)
│   ├── bybit_client.py
│   └── optuna_optimizer.py
├── utils/            # Utility functions
│   ├── statistics.py
│   └── validation.py
└── tests/            # Test files
    ├── unit/
    └── integration/
```

---

## 🧪 Testing Guidelines

### Types of Tests

**1. Unit Tests** - Test individual functions
```python
def test_wilson_score_calculation():
    """Test Wilson score confidence interval calculation."""
    wins = 70
    total = 100

    lower, upper = calculate_wilson_score(wins, total, confidence=0.95)

    assert 0.60 < lower < 0.65  # Expected range
    assert 0.75 < upper < 0.80
    assert lower < wins/total < upper
```

**2. Integration Tests** - Test component interactions
```python
@pytest.mark.asyncio
async def test_signal_to_optimization_flow(db_session):
    """Test complete flow from signal receipt to optimization."""
    # Create signal
    signal = await create_signal(symbol="BTCUSDT", direction="LONG")

    # Collect 30 baseline trades
    for _ in range(30):
        await process_trade(signal.id)

    # Verify Phase II triggered
    strategies = await get_strategies(signal.id)
    assert len(strategies) == 4  # Thompson Sampling top 4
    assert all(s.win_rate >= 0.60 for s in strategies)
```

**3. E2E Tests** - Test complete user workflows
```python
def test_complete_trading_workflow(client, testnet_bybit):
    """Test full workflow: webhook → Phase I → II → III → trade."""
    # Send webhook
    response = client.post("/api/webhooks/tradingview", json={
        "symbol": "BTCUSDT",
        "direction": "LONG"
    })
    assert response.status_code == 200

    # ... complete flow testing
```

### Test Coverage Requirements

- **Minimum coverage:** 80%
- **Critical paths:** 95%+ (Phase I/II/III logic, optimization)
- **New features:** Must include tests

```bash
# Check coverage
pytest --cov=app --cov-report=html
open htmlcov/index.html
```

### Testing Best Practices

- **Arrange-Act-Assert** pattern
- **One assertion per test** (when possible)
- **Descriptive test names** - `test_what_when_then()`
- **Use fixtures** for common setup
- **Mock external services** (Bybit API, etc.)
- **Test edge cases** and error conditions

---

## 📚 Documentation

### Docstring Format

Use Google-style docstrings:

```python
def optimize_strategy(
    baseline_trades: List[Trade],
    symbol: str,
    direction: str,
    n_trials: int = 100
) -> OptimizationResult:
    """
    Optimize TP/SL parameters using Optuna Bayesian optimization.

    This function replaces traditional grid search with intelligent
    Bayesian optimization, achieving 10-20x faster results while
    often finding better parameters.

    Args:
        baseline_trades: List of baseline trades for simulation
        symbol: Trading symbol (e.g., "BTCUSDT")
        direction: Trade direction ("LONG" or "SHORT")
        n_trials: Number of optimization trials (default: 100)

    Returns:
        OptimizationResult containing:
            - best_params: Optimal TP/SL/trailing configuration
            - best_score: Quality score (0-100)
            - best_win_rate: Predicted win rate
            - all_trials: List of all trial results

    Raises:
        ValueError: If insufficient baseline trades (<30)
        OptimizationError: If optimization fails to converge

    Example:
        >>> result = optimize_strategy(
        ...     baseline_trades=trades,
        ...     symbol="BTCUSDT",
        ...     direction="LONG",
        ...     n_trials=100
        ... )
        >>> print(f"Best WR: {result.best_win_rate:.1f}%")
        Best WR: 68.5%

    Note:
        Optuna uses TPE sampler for intelligent parameter selection.
        Early pruning stops unpromising trials to save time.
    """
    pass
```

### README Updates

When adding features, update:
- Feature list
- Configuration section
- API documentation
- Examples

---

## 🌍 Community

### Communication Channels

- **GitHub Issues** - Bug reports, feature requests
- **GitHub Discussions** - Questions, ideas, showcase
- **Discord** - Real-time chat (coming soon)
- **Email** - support@andreassassin.com

### Getting Help

**Before asking:**
1. Search [documentation](README.md)
2. Check [existing issues](https://github.com/andreoutberg/assassinbeta/issues)
3. Read [troubleshooting guide](QUICK_START.md#-troubleshooting)

**When asking:**
- Be specific and clear
- Include relevant code/logs
- Describe what you've tried
- Be respectful and patient

### Recognition

Contributors are recognized in:
- [README.md](README.md) contributors section
- Release notes
- GitHub contributors page

Top contributors may be invited to become maintainers!

---

## 📝 License

By contributing, you agree that your contributions will be licensed under the MIT License.

---

## 🙏 Thank You!

Your contributions make Andre Assassin better for everyone. Whether it's code, docs, or bug reports - we appreciate your help!

**Questions?** Reach out:
- Open a [discussion](https://github.com/andreoutberg/assassinbeta/discussions)
- Email: support@andreassassin.com

**Happy coding! 🚀**
