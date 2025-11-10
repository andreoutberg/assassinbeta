# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.1] - 2025-11-10

### Added
- Initial release with Optuna Bayesian optimization
- Multi-objective optimization (WR, R/R, EV)
- TradingView webhook integration
- Three-phase evolution system (I/II/III)
- Enhanced Bybit client with connection pooling
- One-command installation script
- Complete documentation suite
- Docker Compose infrastructure
- GitHub Actions CI/CD workflows
- PostgreSQL schema with 42 indexes
- Study persistence for resumable optimizations
- Complete visualization suite for Optuna

### Features
- 10-20x faster optimization vs grid search
- 65-70% win rate targeting
- Statistical validation before optimization
- Thompson Sampling for strategy selection
- Demo trading with real Bybit prices
- Rate limiting and retry logic
- Health monitoring
- Comprehensive error handling

### Documentation
- README.md with complete guide
- QUICK_START.md for beginners
- CONTRIBUTING.md for developers
- CODE_OF_CONDUCT.md for community
- ARCHITECTURE.md for technical details

### Infrastructure
- Docker Compose multi-service setup
- PostgreSQL 16 + Redis 7
- FastAPI backend
- React TypeScript frontend (WIP)
- Complete CI/CD pipeline

[0.1.1]: https://github.com/andreoutberg/andre-assassin/releases/tag/v0.1.1