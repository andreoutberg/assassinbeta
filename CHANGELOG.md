# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.2.0] - 2025-11-10

### Added
- Optuna Dashboard integration for real-time optimization monitoring
- Grafana + Prometheus metrics stack with pre-configured dashboards
- iOS-inspired React frontend with glassmorphism design
- Multi-channel alerting system for optimization events and degradation
- Enhanced CCXT Bybit integration with improved demo trading
- Nginx reverse proxy for unified service access
- Docker health checks for all services
- Database connection retry logic with exponential backoff
- Structured JSON logging with automatic rotation
- Comprehensive deployment automation scripts
- Frontend development guide and build scripts
- Grafana dashboard templates for trading metrics
- WebSocket support for real-time updates
- Dark/light mode theme support in frontend
- Mobile-responsive dashboard design

### Changed
- Improved error handling across all services
- Enhanced API documentation with examples
- Optimized database queries for better performance
- Upgraded Docker Compose configuration for production
- Refactored frontend components for better maintainability
- Updated deployment documentation with new services

### Fixed
- Database connection pooling issues under load
- Memory leaks in optimization runner
- WebSocket reconnection logic
- Frontend routing in production environment
- SSL certificate automation scripts

### Security
- Added rate limiting to all API endpoints
- Implemented CORS policy configuration
- Enhanced authentication token validation
- Added input sanitization for webhook payloads

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

[Unreleased]: https://github.com/andreoutberg/andre-assassin/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/andreoutberg/andre-assassin/compare/v0.1.1...v0.2.0
[0.1.1]: https://github.com/andreoutberg/andre-assassin/releases/tag/v0.1.1