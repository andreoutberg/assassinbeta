/**
 * Home Tab Card Components for Andre-Assassin Dashboard
 * Each component is self-contained with render(), update(), and state management
 */

// ============================================================================
// 1. Account Summary Card
// ============================================================================
class AccountSummaryCard {
    constructor(containerId) {
        this.containerId = containerId;
        this.expanded = false;
        this.data = null;
        this.loading = true;
        this.error = null;
    }

    async load() {
        this.loading = true;
        this.error = null;
        this.render();
        try {
            this.data = await dataService.getAccountBalance();
            this.loading = false;
            this.render();
        } catch (error) {
            this.handleError(error);
        }
    }

    async update() {
        try {
            this.data = await dataService.getAccountBalance();
            this.render();
        } catch (error) {
            this.handleError(error);
        }
    }

    toggleExpand() {
        this.expanded = !this.expanded;
        this.render();
    }

    render() {
        const container = document.getElementById(this.containerId);
        if (!container) return;

        if (this.loading) {
            container.innerHTML = this.renderSkeleton();
            return;
        }

        if (this.error) {
            container.innerHTML = this.renderError();
            return;
        }

        container.innerHTML = this.renderContent();
        this.attachEventListeners();
    }

    renderSkeleton() {
        return `
            <div class="card">
                <div class="card-header">
                    <h3 class="card-title">Account Summary</h3>
                </div>
                <div class="card-body">
                    <div class="skeleton-loader">
                        <div class="skeleton-line" style="width: 60%; height: 36px; margin-bottom: 16px;"></div>
                        <div class="skeleton-line" style="width: 40%; height: 20px; margin-bottom: 8px;"></div>
                        <div class="skeleton-line" style="width: 40%; height: 20px; margin-bottom: 8px;"></div>
                        <div class="skeleton-line" style="width: 40%; height: 20px;"></div>
                    </div>
                </div>
            </div>
        `;
    }

    renderError() {
        return `
            <div class="card">
                <div class="card-header">
                    <h3 class="card-title">Account Summary</h3>
                </div>
                <div class="card-body">
                    <div class="error-state">
                        <i class="fas fa-exclamation-triangle"></i>
                        <p>Failed to load account data</p>
                        <small>${this.error}</small>
                        <button class="btn btn-sm btn-primary" onclick="accountSummaryCard.load()">Retry</button>
                    </div>
                </div>
            </div>
        `;
    }

    renderContent() {
        const { total_balance, net_pnl, realized_pnl, unrealized_pnl, completed_trades, active_trades } = this.data;

        const totalBalanceClass = total_balance >= 0 ? 'text-success' : 'text-danger';
        const netPnlClass = net_pnl >= 0 ? 'text-success' : 'text-danger';
        const realizedPnlClass = realized_pnl >= 0 ? 'text-success' : 'text-danger';
        const unrealizedPnlClass = unrealized_pnl >= 0 ? 'text-success' : 'text-danger';

        return `
            <div class="card">
                <div class="card-header">
                    <h3 class="card-title">Account Summary</h3>
                    <button class="btn btn-sm btn-icon expand-toggle" data-card="account-summary">
                        <i class="fas fa-chevron-${this.expanded ? 'up' : 'down'}"></i>
                    </button>
                </div>
                <div class="card-body">
                    <div class="stat-main ${totalBalanceClass}">
                        <div class="stat-value">$${this.formatNumber(total_balance)}</div>
                        <div class="stat-label">Total Balance</div>
                    </div>

                    <div class="stat-grid">
                        <div class="stat-item">
                            <span class="stat-label">Net P&L</span>
                            <span class="stat-value ${netPnlClass}">
                                ${net_pnl >= 0 ? '+' : ''}$${this.formatNumber(net_pnl)}
                            </span>
                        </div>
                        <div class="stat-item">
                            <span class="stat-label">Realized P&L</span>
                            <span class="stat-value ${realizedPnlClass}">
                                ${realized_pnl >= 0 ? '+' : ''}$${this.formatNumber(realized_pnl)}
                            </span>
                        </div>
                        <div class="stat-item">
                            <span class="stat-label">Unrealized P&L</span>
                            <span class="stat-value ${unrealizedPnlClass}">
                                ${unrealized_pnl >= 0 ? '+' : ''}$${this.formatNumber(unrealized_pnl)}
                            </span>
                        </div>
                    </div>

                    ${this.expanded ? this.renderExpandedContent() : ''}
                </div>
            </div>
        `;
    }

    renderExpandedContent() {
        const { completed_trades, active_trades } = this.data;

        return `
            <div class="expanded-content">
                <hr>
                <div class="stat-grid">
                    <div class="stat-item">
                        <span class="stat-label">Completed Trades</span>
                        <span class="stat-value">${completed_trades || 0}</span>
                    </div>
                    <div class="stat-item">
                        <span class="stat-label">Active Trades</span>
                        <span class="stat-value">${active_trades || 0}</span>
                    </div>
                </div>
            </div>
        `;
    }

    attachEventListeners() {
        const toggleBtn = document.querySelector(`#${this.containerId} .expand-toggle`);
        if (toggleBtn) {
            toggleBtn.addEventListener('click', () => this.toggleExpand());
        }
    }

    handleError(error) {
        this.loading = false;
        this.error = error.message || 'Unknown error occurred';
        this.render();
    }

    formatNumber(num) {
        if (num === null || num === undefined) return '0.00';
        return parseFloat(num).toFixed(2).replace(/\B(?=(\d{3})+(?!\d))/g, ',');
    }
}

// ============================================================================
// 2. Active Trades Summary Card
// ============================================================================
class ActiveTradesSummaryCard {
    constructor(containerId) {
        this.containerId = containerId;
        this.expanded = false;
        this.data = null;
        this.loading = true;
        this.error = null;
    }

    async load() {
        this.loading = true;
        this.error = null;
        this.render();
        try {
            this.data = await dataService.getActiveTrades();
            this.loading = false;
            this.render();
        } catch (error) {
            this.handleError(error);
        }
    }

    async update() {
        try {
            this.data = await dataService.getActiveTrades();
            this.render();
        } catch (error) {
            this.handleError(error);
        }
    }

    toggleExpand() {
        this.expanded = !this.expanded;
        this.render();
    }

    render() {
        const container = document.getElementById(this.containerId);
        if (!container) return;

        if (this.loading) {
            container.innerHTML = this.renderSkeleton();
            return;
        }

        if (this.error) {
            container.innerHTML = this.renderError();
            return;
        }

        container.innerHTML = this.renderContent();
        this.attachEventListeners();
    }

    renderSkeleton() {
        return `
            <div class="card">
                <div class="card-header">
                    <h3 class="card-title">Active Trades</h3>
                </div>
                <div class="card-body">
                    <div class="skeleton-loader">
                        <div class="skeleton-line" style="width: 50%; height: 36px; margin-bottom: 16px;"></div>
                        <div class="skeleton-line" style="width: 40%; height: 20px; margin-bottom: 8px;"></div>
                        <div class="skeleton-line" style="width: 40%; height: 20px; margin-bottom: 8px;"></div>
                        <div class="skeleton-line" style="width: 40%; height: 20px;"></div>
                    </div>
                </div>
            </div>
        `;
    }

    renderError() {
        return `
            <div class="card">
                <div class="card-header">
                    <h3 class="card-title">Active Trades</h3>
                </div>
                <div class="card-body">
                    <div class="error-state">
                        <i class="fas fa-exclamation-triangle"></i>
                        <p>Failed to load active trades</p>
                        <small>${this.error}</small>
                        <button class="btn btn-sm btn-primary" onclick="activeTradesSummaryCard.load()">Retry</button>
                    </div>
                </div>
            </div>
        `;
    }

    renderContent() {
        const total = this.data.total || 0;
        const live = this.data.live || 0;
        const paper = this.data.paper || 0;
        const baseline = this.data.baseline || 0;

        return `
            <div class="card">
                <div class="card-header">
                    <h3 class="card-title">Active Trades</h3>
                    <button class="btn btn-sm btn-icon expand-toggle" data-card="active-trades">
                        <i class="fas fa-chevron-${this.expanded ? 'up' : 'down'}"></i>
                    </button>
                </div>
                <div class="card-body">
                    <div class="stat-main">
                        <div class="stat-value">${total} Active ${total === 1 ? 'Trade' : 'Trades'}</div>
                        <div class="stat-label">Currently Open</div>
                    </div>

                    <div class="stat-grid">
                        <div class="stat-item">
                            <span class="stat-label">Live</span>
                            <span class="stat-value text-primary">${live}</span>
                        </div>
                        <div class="stat-item">
                            <span class="stat-label">Paper</span>
                            <span class="stat-value text-info">${paper}</span>
                        </div>
                        <div class="stat-item">
                            <span class="stat-label">Baseline</span>
                            <span class="stat-value text-secondary">${baseline}</span>
                        </div>
                    </div>

                    ${this.expanded ? this.renderExpandedContent() : ''}
                </div>
            </div>
        `;
    }

    renderExpandedContent() {
        const totalExposure = this.data.total_exposure || 0;
        const topTrade = this.data.top_performer || null;
        const worstTrade = this.data.worst_performer || null;

        return `
            <div class="expanded-content">
                <hr>
                <div class="stat-item">
                    <span class="stat-label">Total Exposure</span>
                    <span class="stat-value">$${this.formatNumber(totalExposure)}</span>
                </div>

                ${topTrade ? `
                    <div class="trade-highlight trade-highlight-success">
                        <div class="trade-highlight-label">Top Performer</div>
                        <div class="trade-highlight-content">
                            <span class="trade-symbol">${topTrade.symbol}</span>
                            <span class="trade-pnl text-success">+${this.formatNumber(topTrade.unrealized_pnl_pct)}%</span>
                        </div>
                    </div>
                ` : ''}

                ${worstTrade ? `
                    <div class="trade-highlight trade-highlight-danger">
                        <div class="trade-highlight-label">Worst Performer</div>
                        <div class="trade-highlight-content">
                            <span class="trade-symbol">${worstTrade.symbol}</span>
                            <span class="trade-pnl text-danger">${this.formatNumber(worstTrade.unrealized_pnl_pct)}%</span>
                        </div>
                    </div>
                ` : ''}
            </div>
        `;
    }

    attachEventListeners() {
        const toggleBtn = document.querySelector(`#${this.containerId} .expand-toggle`);
        if (toggleBtn) {
            toggleBtn.addEventListener('click', () => this.toggleExpand());
        }
    }

    handleError(error) {
        this.loading = false;
        this.error = error.message || 'Unknown error occurred';
        this.render();
    }

    formatNumber(num) {
        if (num === null || num === undefined) return '0.00';
        return parseFloat(num).toFixed(2).replace(/\B(?=(\d{3})+(?!\d))/g, ',');
    }
}

// ============================================================================
// 3. System Health Card
// ============================================================================
class SystemHealthCard {
    constructor(containerId) {
        this.containerId = containerId;
        this.expanded = false;
        this.data = null;
        this.strategyHealth = null;
        this.loading = true;
        this.error = null;
    }

    async load() {
        this.loading = true;
        this.error = null;
        this.render();
        try {
            const [systemHealth, strategyHealth] = await Promise.all([
                dataService.getSystemHealth(),
                dataService.getStrategyHealth()
            ]);
            this.data = systemHealth;
            this.strategyHealth = strategyHealth;
            this.loading = false;
            this.render();
        } catch (error) {
            this.handleError(error);
        }
    }

    async update() {
        try {
            const [systemHealth, strategyHealth] = await Promise.all([
                dataService.getSystemHealth(),
                dataService.getStrategyHealth()
            ]);
            this.data = systemHealth;
            this.strategyHealth = strategyHealth;
            this.render();
        } catch (error) {
            this.handleError(error);
        }
    }

    toggleExpand() {
        this.expanded = !this.expanded;
        this.render();
    }

    render() {
        const container = document.getElementById(this.containerId);
        if (!container) return;

        if (this.loading) {
            container.innerHTML = this.renderSkeleton();
            return;
        }

        if (this.error) {
            container.innerHTML = this.renderError();
            return;
        }

        container.innerHTML = this.renderContent();
        this.attachEventListeners();
    }

    renderSkeleton() {
        return `
            <div class="card">
                <div class="card-header">
                    <h3 class="card-title">System Health</h3>
                </div>
                <div class="card-body">
                    <div class="skeleton-loader">
                        <div class="skeleton-line" style="width: 50%; height: 36px; margin-bottom: 16px;"></div>
                        <div class="skeleton-line" style="width: 40%; height: 20px; margin-bottom: 8px;"></div>
                        <div class="skeleton-line" style="width: 40%; height: 20px; margin-bottom: 8px;"></div>
                        <div class="skeleton-line" style="width: 40%; height: 20px;"></div>
                    </div>
                </div>
            </div>
        `;
    }

    renderError() {
        return `
            <div class="card">
                <div class="card-header">
                    <h3 class="card-title">System Health</h3>
                </div>
                <div class="card-body">
                    <div class="error-state">
                        <i class="fas fa-exclamation-triangle"></i>
                        <p>Failed to load system health</p>
                        <small>${this.error}</small>
                        <button class="btn btn-sm btn-primary" onclick="systemHealthCard.load()">Retry</button>
                    </div>
                </div>
            </div>
        `;
    }

    getStatusBadge(status) {
        const statusMap = {
            'healthy': { class: 'badge-success', icon: 'fa-check-circle', text: 'Healthy' },
            'degraded': { class: 'badge-warning', icon: 'fa-exclamation-circle', text: 'Degraded' },
            'down': { class: 'badge-danger', icon: 'fa-times-circle', text: 'Down' }
        };

        const config = statusMap[status] || statusMap['down'];
        return `<span class="badge ${config.class}"><i class="fas ${config.icon}"></i> ${config.text}</span>`;
    }

    getComponentStatus(component) {
        if (!component) return { class: 'text-secondary', icon: 'fa-question', text: 'Unknown' };

        const status = component.status || 'unknown';
        const statusMap = {
            'healthy': { class: 'text-success', icon: 'fa-check-circle', text: 'Healthy' },
            'degraded': { class: 'text-warning', icon: 'fa-exclamation-circle', text: 'Degraded' },
            'down': { class: 'text-danger', icon: 'fa-times-circle', text: 'Down' },
            'unknown': { class: 'text-secondary', icon: 'fa-question', text: 'Unknown' }
        };

        return statusMap[status] || statusMap['unknown'];
    }

    renderContent() {
        const overallStatus = this.data.overall_status || 'unknown';
        const apiStatus = this.getComponentStatus(this.data.api);
        const dbStatus = this.getComponentStatus(this.data.database);
        const priceTrackerStatus = this.getComponentStatus(this.data.price_tracker);

        return `
            <div class="card">
                <div class="card-header">
                    <h3 class="card-title">System Health</h3>
                    <button class="btn btn-sm btn-icon expand-toggle" data-card="system-health">
                        <i class="fas fa-chevron-${this.expanded ? 'up' : 'down'}"></i>
                    </button>
                </div>
                <div class="card-body">
                    <div class="stat-main">
                        <div class="stat-value">${this.getStatusBadge(overallStatus)}</div>
                        <div class="stat-label">System Status</div>
                    </div>

                    <div class="stat-grid">
                        <div class="stat-item">
                            <span class="stat-label">API</span>
                            <span class="stat-value ${apiStatus.class}">
                                <i class="fas ${apiStatus.icon}"></i> ${apiStatus.text}
                            </span>
                        </div>
                        <div class="stat-item">
                            <span class="stat-label">Database</span>
                            <span class="stat-value ${dbStatus.class}">
                                <i class="fas ${dbStatus.icon}"></i> ${dbStatus.text}
                            </span>
                        </div>
                        <div class="stat-item">
                            <span class="stat-label">Price Tracker</span>
                            <span class="stat-value ${priceTrackerStatus.class}">
                                <i class="fas ${priceTrackerStatus.icon}"></i> ${priceTrackerStatus.text}
                            </span>
                        </div>
                    </div>

                    ${this.expanded ? this.renderExpandedContent() : ''}
                </div>
            </div>
        `;
    }

    renderExpandedContent() {
        const strategyStatus = this.getComponentStatus(this.strategyHealth);
        const connectionPool = this.data.database?.connection_pool || null;

        return `
            <div class="expanded-content">
                <hr>
                <div class="stat-item">
                    <span class="stat-label">Strategy System</span>
                    <span class="stat-value ${strategyStatus.class}">
                        <i class="fas ${strategyStatus.icon}"></i> ${strategyStatus.text}
                    </span>
                </div>

                ${connectionPool ? `
                    <div class="stat-item">
                        <span class="stat-label">Connection Pool</span>
                        <span class="stat-value">
                            ${connectionPool.active || 0} / ${connectionPool.total || 0} active
                        </span>
                    </div>
                ` : ''}

                ${this.data.api?.response_time ? `
                    <div class="stat-item">
                        <span class="stat-label">API Response Time</span>
                        <span class="stat-value">${this.data.api.response_time}ms</span>
                    </div>
                ` : ''}
            </div>
        `;
    }

    attachEventListeners() {
        const toggleBtn = document.querySelector(`#${this.containerId} .expand-toggle`);
        if (toggleBtn) {
            toggleBtn.addEventListener('click', () => this.toggleExpand());
        }
    }

    handleError(error) {
        this.loading = false;
        this.error = error.message || 'Unknown error occurred';
        this.render();
    }
}

// ============================================================================
// 4. Top Performers Row
// ============================================================================
class TopPerformersRow {
    constructor(containerId) {
        this.containerId = containerId;
        this.expanded = { strategy: false, asset: false, source: false };
        this.data = null;
        this.loading = true;
        this.error = null;
    }

    async load() {
        this.loading = true;
        this.error = null;
        this.render();
        try {
            const overview = await dataService.getDashboardOverview();
            this.data = overview.top_performers || {};
            this.loading = false;
            this.render();
        } catch (error) {
            this.handleError(error);
        }
    }

    async update() {
        try {
            const overview = await dataService.getDashboardOverview();
            this.data = overview.top_performers || {};
            this.render();
        } catch (error) {
            this.handleError(error);
        }
    }

    toggleExpand(type) {
        this.expanded[type] = !this.expanded[type];
        this.render();
    }

    render() {
        const container = document.getElementById(this.containerId);
        if (!container) return;

        if (this.loading) {
            container.innerHTML = this.renderSkeleton();
            return;
        }

        if (this.error) {
            container.innerHTML = this.renderError();
            return;
        }

        container.innerHTML = this.renderContent();
        this.attachEventListeners();
    }

    renderSkeleton() {
        return `
            <div class="top-performers-row">
                ${this.renderCardSkeleton()}
                ${this.renderCardSkeleton()}
                ${this.renderCardSkeleton()}
            </div>
        `;
    }

    renderCardSkeleton() {
        return `
            <div class="card">
                <div class="card-header">
                    <h3 class="card-title">Loading...</h3>
                </div>
                <div class="card-body">
                    <div class="skeleton-loader">
                        <div class="skeleton-line" style="width: 60%; height: 24px; margin-bottom: 12px;"></div>
                        <div class="skeleton-line" style="width: 40%; height: 20px; margin-bottom: 8px;"></div>
                        <div class="skeleton-line" style="width: 40%; height: 20px;"></div>
                    </div>
                </div>
            </div>
        `;
    }

    renderError() {
        return `
            <div class="top-performers-row">
                <div class="card">
                    <div class="card-body">
                        <div class="error-state">
                            <i class="fas fa-exclamation-triangle"></i>
                            <p>Failed to load top performers</p>
                            <small>${this.error}</small>
                            <button class="btn btn-sm btn-primary" onclick="topPerformersRow.load()">Retry</button>
                        </div>
                    </div>
                </div>
            </div>
        `;
    }

    renderContent() {
        const strategy = this.data.strategy || null;
        const asset = this.data.asset || null;
        const source = this.data.source || null;

        return `
            <div class="top-performers-row">
                ${this.renderStrategyCard(strategy)}
                ${this.renderAssetCard(asset)}
                ${this.renderSourceCard(source)}
            </div>
        `;
    }

    renderStrategyCard(strategy) {
        if (!strategy) {
            return `
                <div class="card">
                    <div class="card-header">
                        <h3 class="card-title">Best Strategy</h3>
                    </div>
                    <div class="card-body">
                        <p class="text-muted">No data available</p>
                    </div>
                </div>
            `;
        }

        const pnlClass = strategy.pnl >= 0 ? 'text-success' : 'text-danger';

        return `
            <div class="card">
                <div class="card-header">
                    <h3 class="card-title">Best Strategy</h3>
                    <button class="btn btn-sm btn-icon expand-toggle" data-type="strategy">
                        <i class="fas fa-chevron-${this.expanded.strategy ? 'up' : 'down'}"></i>
                    </button>
                </div>
                <div class="card-body">
                    <div class="performer-name">${strategy.name}</div>
                    <div class="performer-stats">
                        <div class="stat-item">
                            <span class="stat-label">P&L</span>
                            <span class="stat-value ${pnlClass}">
                                ${strategy.pnl >= 0 ? '+' : ''}$${this.formatNumber(strategy.pnl)}
                            </span>
                        </div>
                        <div class="stat-item">
                            <span class="stat-label">Win Rate</span>
                            <span class="stat-value">${this.formatNumber(strategy.win_rate)}%</span>
                        </div>
                    </div>

                    ${this.expanded.strategy ? `
                        <div class="expanded-content">
                            <hr>
                            <div class="stat-item">
                                <span class="stat-label">Total Trades</span>
                                <span class="stat-value">${strategy.total_trades || 0}</span>
                            </div>
                            <div class="stat-item">
                                <span class="stat-label">Avg P&L</span>
                                <span class="stat-value">$${this.formatNumber(strategy.avg_pnl)}</span>
                            </div>
                            <a href="#strategy-analytics" class="btn btn-sm btn-primary mt-2">
                                View Analytics <i class="fas fa-arrow-right"></i>
                            </a>
                        </div>
                    ` : ''}
                </div>
            </div>
        `;
    }

    renderAssetCard(asset) {
        if (!asset) {
            return `
                <div class="card">
                    <div class="card-header">
                        <h3 class="card-title">Best Asset</h3>
                    </div>
                    <div class="card-body">
                        <p class="text-muted">No data available</p>
                    </div>
                </div>
            `;
        }

        const pnlClass = asset.pnl >= 0 ? 'text-success' : 'text-danger';

        return `
            <div class="card">
                <div class="card-header">
                    <h3 class="card-title">Best Asset</h3>
                    <button class="btn btn-sm btn-icon expand-toggle" data-type="asset">
                        <i class="fas fa-chevron-${this.expanded.asset ? 'up' : 'down'}"></i>
                    </button>
                </div>
                <div class="card-body">
                    <div class="performer-name">${asset.symbol}</div>
                    <div class="performer-stats">
                        <div class="stat-item">
                            <span class="stat-label">P&L</span>
                            <span class="stat-value ${pnlClass}">
                                ${asset.pnl >= 0 ? '+' : ''}$${this.formatNumber(asset.pnl)}
                            </span>
                        </div>
                        <div class="stat-item">
                            <span class="stat-label">Win Rate</span>
                            <span class="stat-value">${this.formatNumber(asset.win_rate)}%</span>
                        </div>
                    </div>

                    ${this.expanded.asset ? `
                        <div class="expanded-content">
                            <hr>
                            <div class="stat-item">
                                <span class="stat-label">Total Trades</span>
                                <span class="stat-value">${asset.total_trades || 0}</span>
                            </div>
                            <div class="stat-item">
                                <span class="stat-label">Avg P&L</span>
                                <span class="stat-value">$${this.formatNumber(asset.avg_pnl)}</span>
                            </div>
                            <a href="#strategy-analytics" class="btn btn-sm btn-primary mt-2">
                                View Analytics <i class="fas fa-arrow-right"></i>
                            </a>
                        </div>
                    ` : ''}
                </div>
            </div>
        `;
    }

    renderSourceCard(source) {
        if (!source) {
            return `
                <div class="card">
                    <div class="card-header">
                        <h3 class="card-title">Best Source</h3>
                    </div>
                    <div class="card-body">
                        <p class="text-muted">No data available</p>
                    </div>
                </div>
            `;
        }

        const pnlClass = source.pnl >= 0 ? 'text-success' : 'text-danger';

        return `
            <div class="card">
                <div class="card-header">
                    <h3 class="card-title">Best Source</h3>
                    <button class="btn btn-sm btn-icon expand-toggle" data-type="source">
                        <i class="fas fa-chevron-${this.expanded.source ? 'up' : 'down'}"></i>
                    </button>
                </div>
                <div class="card-body">
                    <div class="performer-name">${source.name}</div>
                    <div class="performer-stats">
                        <div class="stat-item">
                            <span class="stat-label">P&L</span>
                            <span class="stat-value ${pnlClass}">
                                ${source.pnl >= 0 ? '+' : ''}$${this.formatNumber(source.pnl)}
                            </span>
                        </div>
                        <div class="stat-item">
                            <span class="stat-label">Win Rate</span>
                            <span class="stat-value">${this.formatNumber(source.win_rate)}%</span>
                        </div>
                    </div>

                    ${this.expanded.source ? `
                        <div class="expanded-content">
                            <hr>
                            <div class="stat-item">
                                <span class="stat-label">Total Trades</span>
                                <span class="stat-value">${source.total_trades || 0}</span>
                            </div>
                            <div class="stat-item">
                                <span class="stat-label">Avg P&L</span>
                                <span class="stat-value">$${this.formatNumber(source.avg_pnl)}</span>
                            </div>
                            <a href="#strategy-analytics" class="btn btn-sm btn-primary mt-2">
                                View Analytics <i class="fas fa-arrow-right"></i>
                            </a>
                        </div>
                    ` : ''}
                </div>
            </div>
        `;
    }

    attachEventListeners() {
        const toggleBtns = document.querySelectorAll(`#${this.containerId} .expand-toggle`);
        toggleBtns.forEach(btn => {
            btn.addEventListener('click', () => {
                const type = btn.getAttribute('data-type');
                this.toggleExpand(type);
            });
        });
    }

    handleError(error) {
        this.loading = false;
        this.error = error.message || 'Unknown error occurred';
        this.render();
    }

    formatNumber(num) {
        if (num === null || num === undefined) return '0.00';
        return parseFloat(num).toFixed(2).replace(/\B(?=(\d{3})+(?!\d))/g, ',');
    }
}

// ============================================================================
// 5. Breakeven Test Card
// ============================================================================
class BreakevenTestCard {
    constructor(containerId) {
        this.containerId = containerId;
        this.expanded = false;
        this.data = null;
        this.loading = true;
        this.error = null;
    }

    async load() {
        this.loading = true;
        this.error = null;
        this.render();
        try {
            const overview = await dataService.getDashboardOverview();
            this.data = overview.breakeven_test || null;
            this.loading = false;
            this.render();
        } catch (error) {
            this.handleError(error);
        }
    }

    async update() {
        try {
            const overview = await dataService.getDashboardOverview();
            this.data = overview.breakeven_test || null;
            this.render();
        } catch (error) {
            this.handleError(error);
        }
    }

    toggleExpand() {
        this.expanded = !this.expanded;
        this.render();
    }

    render() {
        const container = document.getElementById(this.containerId);
        if (!container) return;

        if (this.loading) {
            container.innerHTML = this.renderSkeleton();
            return;
        }

        if (this.error) {
            container.innerHTML = this.renderError();
            return;
        }

        container.innerHTML = this.renderContent();
        this.attachEventListeners();
    }

    renderSkeleton() {
        return `
            <div class="card">
                <div class="card-header">
                    <h3 class="card-title">Breakeven Test</h3>
                </div>
                <div class="card-body">
                    <div class="skeleton-loader">
                        <div class="skeleton-line" style="width: 60%; height: 32px; margin-bottom: 16px;"></div>
                        <div class="skeleton-line" style="width: 80%; height: 40px; margin-bottom: 8px;"></div>
                        <div class="skeleton-line" style="width: 80%; height: 40px;"></div>
                    </div>
                </div>
            </div>
        `;
    }

    renderError() {
        return `
            <div class="card">
                <div class="card-header">
                    <h3 class="card-title">Breakeven Test</h3>
                </div>
                <div class="card-body">
                    <div class="error-state">
                        <i class="fas fa-exclamation-triangle"></i>
                        <p>Failed to load breakeven test data</p>
                        <small>${this.error}</small>
                        <button class="btn btn-sm btn-primary" onclick="breakevenTestCard.load()">Retry</button>
                    </div>
                </div>
            </div>
        `;
    }

    renderContent() {
        if (!this.data) {
            return `
                <div class="card">
                    <div class="card-header">
                        <h3 class="card-title">Breakeven Test</h3>
                    </div>
                    <div class="card-body">
                        <p class="text-muted">No breakeven test data available</p>
                    </div>
                </div>
            `;
        }

        const cfComparison = this.data.cf_comparison || {};
        const aeComparison = this.data.ae_comparison || null;

        return `
            <div class="card">
                <div class="card-header">
                    <h3 class="card-title">Breakeven Test</h3>
                    <button class="btn btn-sm btn-icon expand-toggle" data-card="breakeven-test">
                        <i class="fas fa-chevron-${this.expanded ? 'up' : 'down'}"></i>
                    </button>
                </div>
                <div class="card-body">
                    ${this.renderComparison('C vs F', cfComparison)}
                    ${aeComparison ? this.renderComparison('A vs E', aeComparison) : ''}

                    ${this.expanded ? this.renderExpandedContent() : ''}
                </div>
            </div>
        `;
    }

    renderComparison(title, comparison) {
        const first = comparison.first || {};
        const second = comparison.second || {};
        const winner = comparison.winner || null;

        const firstPnl = first.pnl || 0;
        const secondPnl = second.pnl || 0;
        const firstClass = firstPnl >= 0 ? 'text-success' : 'text-danger';
        const secondClass = secondPnl >= 0 ? 'text-success' : 'text-danger';

        return `
            <div class="breakeven-comparison">
                <h4 class="comparison-title">${title}</h4>
                <div class="comparison-grid">
                    <div class="comparison-item ${winner === first.name ? 'winner' : ''}">
                        <div class="comparison-name">
                            ${first.name || 'Unknown'}
                            ${winner === first.name ? '<i class="fas fa-trophy text-warning"></i>' : ''}
                        </div>
                        <div class="comparison-pnl ${firstClass}">
                            ${firstPnl >= 0 ? '+' : ''}$${this.formatNumber(firstPnl)}
                        </div>
                    </div>
                    <div class="comparison-vs">vs</div>
                    <div class="comparison-item ${winner === second.name ? 'winner' : ''}">
                        <div class="comparison-name">
                            ${second.name || 'Unknown'}
                            ${winner === second.name ? '<i class="fas fa-trophy text-warning"></i>' : ''}
                        </div>
                        <div class="comparison-pnl ${secondClass}">
                            ${secondPnl >= 0 ? '+' : ''}$${this.formatNumber(secondPnl)}
                        </div>
                    </div>
                </div>
            </div>
        `;
    }

    renderExpandedContent() {
        const cfComparison = this.data.cf_comparison || {};
        const aeComparison = this.data.ae_comparison || null;

        return `
            <div class="expanded-content">
                <hr>
                <h5>C vs F Details</h5>
                ${this.renderComparisonDetails(cfComparison)}

                ${aeComparison ? `
                    <h5 class="mt-3">A vs E Details</h5>
                    ${this.renderComparisonDetails(aeComparison)}
                ` : ''}

                <div class="mt-3">
                    <small class="text-muted">Chart visualization coming soon</small>
                </div>
            </div>
        `;
    }

    renderComparisonDetails(comparison) {
        const first = comparison.first || {};
        const second = comparison.second || {};

        return `
            <div class="comparison-details">
                <table class="table table-sm">
                    <thead>
                        <tr>
                            <th></th>
                            <th>${first.name || 'First'}</th>
                            <th>${second.name || 'Second'}</th>
                        </tr>
                    </thead>
                    <tbody>
                        <tr>
                            <td>Trades</td>
                            <td>${first.trade_count || 0}</td>
                            <td>${second.trade_count || 0}</td>
                        </tr>
                        <tr>
                            <td>Win Rate</td>
                            <td>${this.formatNumber(first.win_rate)}%</td>
                            <td>${this.formatNumber(second.win_rate)}%</td>
                        </tr>
                        <tr>
                            <td>Avg P&L</td>
                            <td>$${this.formatNumber(first.avg_pnl)}</td>
                            <td>$${this.formatNumber(second.avg_pnl)}</td>
                        </tr>
                    </tbody>
                </table>
            </div>
        `;
    }

    attachEventListeners() {
        const toggleBtn = document.querySelector(`#${this.containerId} .expand-toggle`);
        if (toggleBtn) {
            toggleBtn.addEventListener('click', () => this.toggleExpand());
        }
    }

    handleError(error) {
        this.loading = false;
        this.error = error.message || 'Unknown error occurred';
        this.render();
    }

    formatNumber(num) {
        if (num === null || num === undefined) return '0.00';
        return parseFloat(num).toFixed(2).replace(/\B(?=(\d{3})+(?!\d))/g, ',');
    }
}

// ============================================================================
// 6. Recent Trades Card
// ============================================================================
class RecentTradesCard {
    constructor(containerId) {
        this.containerId = containerId;
        this.expanded = false;
        this.data = null;
        this.loading = true;
        this.error = null;
    }

    async load() {
        this.loading = true;
        this.error = null;
        this.render();
        try {
            this.data = await dataService.getRecentTrades();
            this.loading = false;
            this.render();
        } catch (error) {
            this.handleError(error);
        }
    }

    async update() {
        try {
            this.data = await dataService.getRecentTrades();
            this.render();
        } catch (error) {
            this.handleError(error);
        }
    }

    toggleExpand() {
        this.expanded = !this.expanded;
        this.render();
    }

    render() {
        const container = document.getElementById(this.containerId);
        if (!container) return;

        if (this.loading) {
            container.innerHTML = this.renderSkeleton();
            return;
        }

        if (this.error) {
            container.innerHTML = this.renderError();
            return;
        }

        container.innerHTML = this.renderContent();
        this.attachEventListeners();
    }

    renderSkeleton() {
        return `
            <div class="card">
                <div class="card-header">
                    <h3 class="card-title">Recent Trades</h3>
                </div>
                <div class="card-body">
                    <div class="skeleton-loader">
                        <div class="skeleton-line" style="width: 100%; height: 30px; margin-bottom: 8px;"></div>
                        <div class="skeleton-line" style="width: 100%; height: 30px; margin-bottom: 8px;"></div>
                        <div class="skeleton-line" style="width: 100%; height: 30px; margin-bottom: 8px;"></div>
                        <div class="skeleton-line" style="width: 100%; height: 30px; margin-bottom: 8px;"></div>
                        <div class="skeleton-line" style="width: 100%; height: 30px;"></div>
                    </div>
                </div>
            </div>
        `;
    }

    renderError() {
        return `
            <div class="card">
                <div class="card-header">
                    <h3 class="card-title">Recent Trades</h3>
                </div>
                <div class="card-body">
                    <div class="error-state">
                        <i class="fas fa-exclamation-triangle"></i>
                        <p>Failed to load recent trades</p>
                        <small>${this.error}</small>
                        <button class="btn btn-sm btn-primary" onclick="recentTradesCard.load()">Retry</button>
                    </div>
                </div>
            </div>
        `;
    }

    renderContent() {
        const trades = this.expanded ? (this.data.slice(0, 20) || []) : (this.data.slice(0, 5) || []);

        return `
            <div class="card">
                <div class="card-header">
                    <h3 class="card-title">Recent Trades</h3>
                    <button class="btn btn-sm btn-icon expand-toggle" data-card="recent-trades">
                        <i class="fas fa-chevron-${this.expanded ? 'up' : 'down'}"></i>
                    </button>
                </div>
                <div class="card-body">
                    ${trades.length === 0 ? `
                        <p class="text-muted">No recent trades</p>
                    ` : `
                        <div class="table-responsive">
                            <table class="table table-sm table-hover">
                                <thead>
                                    <tr>
                                        <th>Symbol</th>
                                        <th>Direction</th>
                                        <th class="text-right">P&L %</th>
                                        <th class="text-right">Completed</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    ${trades.map(trade => this.renderTradeRow(trade)).join('')}
                                </tbody>
                            </table>
                        </div>
                        ${this.expanded ? this.renderExpandedContent() : ''}
                    `}
                </div>
            </div>
        `;
    }

    renderTradeRow(trade) {
        const pnlPct = trade.pnl_pct || 0;
        const pnlClass = pnlPct >= 0 ? 'text-success' : 'text-danger';
        const directionIcon = trade.direction === 'LONG' ? 'fa-arrow-up text-success' : 'fa-arrow-down text-danger';
        const completedAt = trade.completed_at ? this.formatDateTime(trade.completed_at) : 'N/A';

        return `
            <tr>
                <td><strong>${trade.symbol}</strong></td>
                <td><i class="fas ${directionIcon}"></i> ${trade.direction}</td>
                <td class="text-right ${pnlClass}">
                    ${pnlPct >= 0 ? '+' : ''}${this.formatNumber(pnlPct)}%
                </td>
                <td class="text-right">${completedAt}</td>
            </tr>
        `;
    }

    renderExpandedContent() {
        return `
            <div class="expanded-content">
                <div class="mt-3 text-center">
                    <small class="text-muted">Mini sparkline visualization coming soon</small>
                </div>
            </div>
        `;
    }

    attachEventListeners() {
        const toggleBtn = document.querySelector(`#${this.containerId} .expand-toggle`);
        if (toggleBtn) {
            toggleBtn.addEventListener('click', () => this.toggleExpand());
        }
    }

    handleError(error) {
        this.loading = false;
        this.error = error.message || 'Unknown error occurred';
        this.render();
    }

    formatNumber(num) {
        if (num === null || num === undefined) return '0.00';
        return parseFloat(num).toFixed(2).replace(/\B(?=(\d{3})+(?!\d))/g, ',');
    }

    formatDateTime(timestamp) {
        const date = new Date(timestamp);
        const now = new Date();
        const diff = now - date;
        const hours = Math.floor(diff / (1000 * 60 * 60));
        const days = Math.floor(diff / (1000 * 60 * 60 * 24));

        if (hours < 1) {
            const minutes = Math.floor(diff / (1000 * 60));
            return `${minutes}m ago`;
        } else if (hours < 24) {
            return `${hours}h ago`;
        } else if (days < 7) {
            return `${days}d ago`;
        } else {
            return date.toLocaleDateString();
        }
    }
}

// ============================================================================
// Export components for use in other modules
// ============================================================================
if (typeof module !== 'undefined' && module.exports) {
    module.exports = {
        AccountSummaryCard,
        ActiveTradesSummaryCard,
        SystemHealthCard,
        TopPerformersRow,
        BreakevenTestCard,
        RecentTradesCard
    };
}
