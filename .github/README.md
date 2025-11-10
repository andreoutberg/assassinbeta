# GitHub Actions Workflows & Templates

This directory contains GitHub Actions workflows, issue templates, and other GitHub-specific configurations for the Assassin Beta project.

## Workflow Status Badges

![CI/CD Pipeline](https://github.com/assassinbeta/assassin-beta/workflows/CI%2FCD%20Pipeline/badge.svg)
![Tests](https://github.com/assassinbeta/assassin-beta/workflows/Comprehensive%20Tests/badge.svg)
![Docker](https://github.com/assassinbeta/assassin-beta/workflows/Docker%20Build%20%26%20Push/badge.svg)
![Code Quality](https://github.com/assassinbeta/assassin-beta/workflows/Code%20Quality/badge.svg)
[![codecov](https://codecov.io/gh/assassinbeta/assassin-beta/branch/main/graph/badge.svg)](https://codecov.io/gh/assassinbeta/assassin-beta)
[![Quality Gate Status](https://sonarcloud.io/api/project_badges/measure?project=assassinbeta_assassin-beta&metric=alert_status)](https://sonarcloud.io/summary/new_code?id=assassinbeta_assassin-beta)

## Workflows

### 1. CI/CD Pipeline (`ci.yml`)

**Trigger**: Push to main/develop, Pull requests to main
**Estimated Time**: 8-10 minutes
**Purpose**: Main continuous integration pipeline

**Jobs**:
- **Lint** (2 min): Python code formatting and linting with black, ruff, mypy
- **Test Backend** (5 min): Unit and integration tests with PostgreSQL and Redis
- **Test Frontend** (3 min): Jest tests, linting, and build verification
- **Build Docker** (5 min): Multi-platform Docker image builds

**Required Secrets**:
- `DOCKER_USERNAME`: Docker Hub username
- `DOCKER_PASSWORD`: Docker Hub password
- `SLACK_WEBHOOK_URL`: (Optional) Slack notifications

### 2. Comprehensive Tests (`tests.yml`)

**Trigger**: Daily at midnight UTC, Manual dispatch
**Estimated Time**: 20-30 minutes
**Purpose**: Extensive testing suite including load and security tests

**Test Types**:
- **Integration Tests**: Full stack integration testing
- **Load Tests**: Performance testing with k6
- **Security Scan**: Vulnerability scanning with Trivy, Bandit, Safety
- **E2E Tests**: End-to-end testing with Playwright

### 3. Release Automation (`release.yml`)

**Trigger**: Git tags (v*), Manual dispatch
**Purpose**: Automated release process with multi-registry publishing

**Features**:
- Semantic versioning support
- Multi-platform Docker builds (amd64, arm64)
- Automated changelog generation
- GitHub and Docker Hub publishing
- Staging deployment for production releases
- Slack/Discord notifications

### 4. Docker Build & Push (`docker.yml`)

**Trigger**: Push to main/develop, Tags, Pull requests
**Estimated Time**: 15-20 minutes
**Purpose**: Dedicated Docker image building and vulnerability scanning

**Features**:
- Multi-registry support (Docker Hub, GitHub Container Registry)
- Multi-platform builds
- Vulnerability scanning with Trivy
- SBOM generation
- Docker Compose testing

### 5. Code Quality (`quality.yml`)

**Trigger**: Push to main/develop, Pull requests, Weekly
**Estimated Time**: 10-15 minutes
**Purpose**: Comprehensive code quality and security analysis

**Checks**:
- **SonarCloud**: Code quality and coverage analysis
- **CodeClimate**: Maintainability and test coverage
- **CodeQL**: Security vulnerability detection
- **Dependency Review**: License and vulnerability checks
- **Complexity Analysis**: Cyclomatic complexity with radon
- **Documentation**: Docstring coverage with interrogate

**Required Secrets**:
- `SONAR_TOKEN`: SonarCloud authentication
- `CC_TEST_REPORTER_ID`: CodeClimate reporter ID

## Issue Templates

### Bug Report (`bug_report.yml`)
Structured form for reporting bugs with:
- Detailed reproduction steps
- Component selection
- Environment information
- Log output sections
- Screenshot support

### Feature Request (`feature_request.yml`)
Comprehensive feature request template with:
- Problem description
- Solution proposals
- Alternative considerations
- Priority levels
- Contribution willingness

### Configuration (`config.yml`)
- Disables blank issues
- Provides links to community resources
- Security issue reporting guidelines

## Pull Request Template

Comprehensive PR template including:
- Change type classification
- Testing checklist
- Performance impact assessment
- Database migration tracking
- Breaking change documentation
- Review focus areas

## Dependabot Configuration

Automated dependency updates for:
- **Python** (Backend): Weekly updates, grouped minor/patch
- **NPM** (Frontend): Weekly updates, React grouping
- **Docker**: Base image updates
- **GitHub Actions**: Workflow dependency updates
- **Terraform**: Infrastructure updates

## Secrets Required

### Critical (Required for basic CI/CD)
```bash
DOCKER_USERNAME     # Docker Hub username
DOCKER_PASSWORD     # Docker Hub password
```

### Quality & Analytics (Recommended)
```bash
SONAR_TOKEN              # SonarCloud integration
CC_TEST_REPORTER_ID      # CodeClimate coverage
CODECOV_TOKEN           # Codecov integration
```

### Notifications (Optional)
```bash
SLACK_WEBHOOK_URL       # Slack notifications
DISCORD_WEBHOOK_URL     # Discord notifications
```

## Usage

### Running Workflows Manually

```bash
# Trigger comprehensive tests
gh workflow run tests.yml -f test_type=all

# Create a release
gh workflow run release.yml -f version=v1.0.0

# Run specific test suite
gh workflow run tests.yml -f test_type=security
```

### Monitoring Workflow Runs

```bash
# List recent workflow runs
gh run list

# Watch a specific run
gh run watch

# View workflow run details
gh run view [run-id]
```

## Performance Optimization

### Estimated CI Times

| Workflow | Average Time | Parallel Jobs |
|----------|-------------|---------------|
| CI/CD Pipeline | 8-10 min | Yes |
| Docker Build | 15-20 min | Partial |
| Tests Suite | 20-30 min | Yes |
| Code Quality | 10-15 min | Yes |
| Release | 15-25 min | Sequential |

### Optimization Strategies

1. **Caching**: All workflows use dependency caching
2. **Parallel Execution**: Tests run in parallel where possible
3. **Conditional Runs**: Skip unnecessary jobs on certain branches
4. **Docker Layer Caching**: BuildKit and GitHub Actions cache
5. **Artifact Sharing**: Minimize redundant builds

## Troubleshooting

### Common Issues

1. **Docker push fails**: Check DOCKER_USERNAME and DOCKER_PASSWORD secrets
2. **Tests timeout**: Increase timeout values in workflow files
3. **Coverage upload fails**: Verify token secrets are set
4. **Security scan failures**: Review and update dependencies

### Debug Mode

Add to workflow file for verbose output:
```yaml
env:
  ACTIONS_STEP_DEBUG: true
  ACTIONS_RUNNER_DEBUG: true
```

## Contributing

When adding new workflows:
1. Follow existing naming conventions
2. Add appropriate timeout values
3. Include job summaries
4. Document required secrets
5. Update this README

## License

All workflows and templates are part of the Assassin Beta project and follow the main project license.