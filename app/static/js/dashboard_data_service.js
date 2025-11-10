/**
 * Dashboard Data Service
 * Centralized API client with caching, error handling, and retry logic
 * for the Andre-Assassin trading dashboard
 */

class DashboardDataService {
    constructor() {
        // Cache storage
        this.cache = new Map();
        this.cacheTimestamps = new Map();

        // Configuration
        this.maxRetries = 3;
        this.retryDelay = 1000; // 1 second base delay
        this.requestTimeout = 10000; // 10 seconds
    }

    /**
     * Core fetch method with caching, error handling, and retry logic
     * @param {string} endpoint - API endpoint to fetch
     * @param {number} ttl - Time to live in milliseconds
     * @param {object} options - Additional fetch options
     * @returns {Promise<any>} - Parsed JSON response
     */
    async fetchWithCache(endpoint, ttl = 30000, options = {}) {
        const now = Date.now();
        const cacheKey = endpoint;

        // Check if cached data exists and is still valid
        if (this.cache.has(cacheKey) && this.cacheTimestamps.has(cacheKey)) {
            const cachedTime = this.cacheTimestamps.get(cacheKey);
            if (now - cachedTime < ttl) {
                console.log(`[Cache HIT] ${endpoint}`);
                return this.cache.get(cacheKey);
            } else {
                console.log(`[Cache EXPIRED] ${endpoint}`);
            }
        } else {
            console.log(`[Cache MISS] ${endpoint}`);
        }

        // Fetch fresh data with retry logic
        const data = await this.fetchWithRetry(endpoint, options);

        // Cache the result
        this.cache.set(cacheKey, data);
        this.cacheTimestamps.set(cacheKey, now);

        return data;
    }

    /**
     * Fetch with automatic retry on failure
     * @param {string} endpoint - API endpoint
     * @param {object} options - Fetch options
     * @param {number} attempt - Current attempt number
     * @returns {Promise<any>} - Parsed JSON response
     */
    async fetchWithRetry(endpoint, options = {}, attempt = 1) {
        try {
            const controller = new AbortController();
            const timeoutId = setTimeout(() => controller.abort(), this.requestTimeout);

            const response = await fetch(endpoint, {
                ...options,
                signal: controller.signal,
                headers: {
                    'Content-Type': 'application/json',
                    ...options.headers
                }
            });

            clearTimeout(timeoutId);

            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }

            const data = await response.json();
            return data;

        } catch (error) {
            console.error(`[Fetch Error] ${endpoint} (Attempt ${attempt}/${this.maxRetries}):`, error.message);

            // Retry logic
            if (attempt < this.maxRetries) {
                const delay = this.retryDelay * Math.pow(2, attempt - 1); // Exponential backoff
                console.log(`[Retry] Waiting ${delay}ms before retry...`);
                await this.sleep(delay);
                return this.fetchWithRetry(endpoint, options, attempt + 1);
            }

            // All retries exhausted
            throw new Error(`Failed to fetch ${endpoint} after ${this.maxRetries} attempts: ${error.message}`);
        }
    }

    /**
     * Clear cache for a specific endpoint or all cache
     * @param {string} endpoint - Optional endpoint to clear, if not provided clears all
     */
    clearCache(endpoint = null) {
        if (endpoint) {
            this.cache.delete(endpoint);
            this.cacheTimestamps.delete(endpoint);
            console.log(`[Cache CLEAR] ${endpoint}`);
        } else {
            this.cache.clear();
            this.cacheTimestamps.clear();
            console.log('[Cache CLEAR] All cache cleared');
        }
    }

    /**
     * Check if cache entry is valid
     * @param {string} endpoint - API endpoint
     * @param {number} ttl - Time to live in milliseconds
     * @returns {boolean} - Whether cache is valid
     */
    isCacheValid(endpoint, ttl) {
        if (!this.cache.has(endpoint) || !this.cacheTimestamps.has(endpoint)) {
            return false;
        }
        const now = Date.now();
        const cachedTime = this.cacheTimestamps.get(endpoint);
        return (now - cachedTime) < ttl;
    }

    /**
     * Sleep utility for retry delays
     * @param {number} ms - Milliseconds to sleep
     * @returns {Promise<void>}
     */
    sleep(ms) {
        return new Promise(resolve => setTimeout(resolve, ms));
    }

    // ========================================
    // HOME TAB APIs
    // ========================================

    /**
     * Get account balance information
     * @returns {Promise<object>} Account balance data
     */
    async getAccountBalance() {
        return this.fetchWithCache('/api/account/balance', 30000); // 30s TTL
    }

    /**
     * Get active trades
     * @returns {Promise<array>} Active trades data
     */
    async getActiveTrades() {
        return this.fetchWithCache('/api/trades/active', 15000); // 15s TTL
    }

    /**
     * Get system health status
     * @returns {Promise<object>} System health data
     */
    async getSystemHealth() {
        return this.fetchWithCache('/api/health', 60000); // 60s TTL
    }

    /**
     * Get strategy health metrics
     * @returns {Promise<object>} Strategy health data
     */
    async getStrategyHealth() {
        return this.fetchWithCache('/api/strategies/health', 60000); // 60s TTL
    }

    /**
     * Get dashboard overview (server-side cached)
     * @returns {Promise<object>} Dashboard overview data
     */
    async getDashboardOverview() {
        return this.fetchWithCache('/api/strategies/dashboard-overview', 300000); // 5min TTL
    }

    /**
     * Get recent trades overview (server-side cached)
     * @returns {Promise<array>} Recent trades data
     */
    async getRecentTrades() {
        return this.fetchWithCache('/api/strategies/recent-trades-overview', 120000); // 2min TTL
    }

    // ========================================
    // STRATEGY ANALYTICS APIs
    // ========================================

    /**
     * Get all strategy phases
     * @returns {Promise<array>} All phases data
     */
    async getAllPhases() {
        return this.fetchWithCache('/api/strategies/all-phases', 60000); // 60s TTL
    }

    /**
     * Get strategy performance for specific parameters
     * @param {string} symbol - Trading symbol (e.g., 'BTCUSDT')
     * @param {string} direction - Trade direction ('long' or 'short')
     * @param {string} webhook - Webhook identifier
     * @returns {Promise<object>} Strategy performance data
     */
    async getStrategyPerformance(symbol, direction, webhook) {
        if (!symbol || !direction || !webhook) {
            throw new Error('Symbol, direction, and webhook are required parameters');
        }

        const endpoint = `/api/strategies/performance/${symbol}/${direction}/${webhook}`;
        return this.fetchWithCache(endpoint, 60000); // 60s TTL
    }

    /**
     * Get trade simulations for a specific trade
     * @param {string|number} tradeId - Trade ID
     * @returns {Promise<object>} Trade simulation data
     */
    async getTradeSimulations(tradeId) {
        if (!tradeId) {
            throw new Error('Trade ID is required');
        }

        const endpoint = `/api/strategies/simulations/${tradeId}`;
        return this.fetchWithCache(endpoint, 300000); // 5min TTL
    }

    /**
     * Get parallel strategy comparison data
     * @returns {Promise<object>} Parallel comparison data
     */
    async getParallelComparison() {
        return this.fetchWithCache('/api/strategies/parallel-comparison', 60000); // 60s TTL
    }

    // ========================================
    // UTILITY METHODS
    // ========================================

    /**
     * Refresh all home tab data
     * Useful for manual refresh buttons
     * @returns {Promise<object>} All home tab data
     */
    async refreshHomeTab() {
        // Clear cache for home tab endpoints
        this.clearCache('/api/account/balance');
        this.clearCache('/api/trades/active');
        this.clearCache('/api/health');
        this.clearCache('/api/strategies/health');
        this.clearCache('/api/strategies/dashboard-overview');
        this.clearCache('/api/strategies/recent-trades-overview');

        // Fetch fresh data
        const [balance, activeTrades, systemHealth, strategyHealth, overview, recentTrades] = await Promise.all([
            this.getAccountBalance(),
            this.getActiveTrades(),
            this.getSystemHealth(),
            this.getStrategyHealth(),
            this.getDashboardOverview(),
            this.getRecentTrades()
        ]);

        return {
            balance,
            activeTrades,
            systemHealth,
            strategyHealth,
            overview,
            recentTrades
        };
    }

    /**
     * Refresh specific strategy analytics
     * @param {string} symbol - Trading symbol
     * @param {string} direction - Trade direction
     * @param {string} webhook - Webhook identifier
     * @returns {Promise<object>} Refreshed strategy data
     */
    async refreshStrategyAnalytics(symbol, direction, webhook) {
        const endpoint = `/api/strategies/performance/${symbol}/${direction}/${webhook}`;
        this.clearCache(endpoint);
        return this.getStrategyPerformance(symbol, direction, webhook);
    }

    /**
     * Get cache statistics
     * @returns {object} Cache statistics
     */
    getCacheStats() {
        const now = Date.now();
        const stats = {
            totalEntries: this.cache.size,
            entries: []
        };

        for (const [endpoint, timestamp] of this.cacheTimestamps.entries()) {
            const age = now - timestamp;
            stats.entries.push({
                endpoint,
                age: `${(age / 1000).toFixed(1)}s`,
                ageMs: age
            });
        }

        return stats;
    }

    /**
     * Prefetch common data
     * Useful for preloading data on page load
     * @returns {Promise<void>}
     */
    async prefetchCommonData() {
        console.log('[Prefetch] Starting prefetch of common data...');

        try {
            await Promise.all([
                this.getAccountBalance(),
                this.getActiveTrades(),
                this.getSystemHealth(),
                this.getStrategyHealth()
            ]);
            console.log('[Prefetch] Common data prefetch completed');
        } catch (error) {
            console.error('[Prefetch] Failed to prefetch common data:', error);
        }
    }

    /**
     * Health check - verify API is accessible
     * @returns {Promise<boolean>} True if API is healthy
     */
    async healthCheck() {
        try {
            await this.getSystemHealth();
            return true;
        } catch (error) {
            console.error('[Health Check] API health check failed:', error);
            return false;
        }
    }
}

// Export singleton instance
const dataService = new DashboardDataService();

// Make it available globally for console debugging
if (typeof window !== 'undefined') {
    window.dataService = dataService;
}

// Export for module usage
if (typeof module !== 'undefined' && module.exports) {
    module.exports = dataService;
}
