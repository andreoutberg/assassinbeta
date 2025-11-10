/**
 * Dashboard Improvements - Strategy Overlay, Loading Spinners, Error Handling
 * 
 * Add this script to improved_dashboard.html:
 * <script src="/static/dashboard_improvements.js"></script>
 */

// ======================
// LOADING SPINNER UTILITIES
// ======================

/**
 * Show loading spinner with message
 * @param {string} containerId - ID of container to show spinner in
 * @param {string} message - Loading message (default: "Loading...")
 */
function showLoadingSpinner(containerId, message = "Loading...") {
    const container = document.getElementById(containerId);
    if (!container) {
        console.warn(`Container ${containerId} not found for loading spinner`);
        return;
    }
    
    const spinner = document.createElement('div');
    spinner.className = 'loading-spinner-overlay';
    spinner.innerHTML = `
        <div class="spinner-container">
            <div class="spinner-border text-primary" role="status">
                <span class="visually-hidden">Loading...</span>
            </div>
            <p class="mt-2">${message}</p>
        </div>
    `;
    
    container.appendChild(spinner);
}

/**
 * Hide loading spinner
 * @param {string} containerId - ID of container containing spinner
 */
function hideLoadingSpinner(containerId) {
    const container = document.getElementById(containerId);
    if (!container) return;
    
    const spinner = container.querySelector('.loading-spinner-overlay');
    if (spinner) {
        spinner.remove();
    }
}

/**
 * Show global loading overlay (covers entire page)
 * @param {string} message - Loading message
 */
function showGlobalSpinner(message = "Loading...") {
    let overlay = document.getElementById('global-loading-overlay');
    
    if (!overlay) {
        overlay = document.createElement('div');
        overlay.id = 'global-loading-overlay';
        overlay.style.cssText = `
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            background: rgba(0, 0, 0, 0.7);
            display: flex;
            justify-content: center;
            align-items: center;
            z-index: 9999;
        `;
        overlay.innerHTML = `
            <div style="text-align: center; color: white;">
                <div class="spinner-border text-light" role="status" style="width: 3rem; height: 3rem;">
                    <span class="visually-hidden">Loading...</span>
                </div>
                <p class="mt-3" style="font-size: 1.2rem;">${message}</p>
            </div>
        `;
        document.body.appendChild(overlay);
    }
}

/**
 * Hide global loading overlay
 */
function hideGlobalSpinner() {
    const overlay = document.getElementById('global-loading-overlay');
    if (overlay) {
        overlay.remove();
    }
}


// ======================
// ERROR HANDLING UTILITIES
// ======================

/**
 * Handle fetch errors - checks response status and throws on error
 * @param {Response} response - Fetch API response
 * @returns {Response} - Original response if OK
 * @throws {Error} - If response is not OK
 */
function handleFetchErrors(response) {
    if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
    }
    return response.json();
}

/**
 * Display user-friendly error message
 * @param {Error} error - Error object
 * @param {string} context - Context where error occurred
 */
function handleApiError(error, context = 'API request') {
    console.error(`Error in ${context}:`, error);
    
    let message = `Failed to ${context}`;
    
    // Customize message based on error type
    if (error.message.includes('Failed to fetch')) {
        message += ': Server is unreachable. Please check your connection.';
    } else if (error.message.includes('404')) {
        message += ': Resource not found.';
    } else if (error.message.includes('500')) {
        message += ': Server error. Please try again later.';
    } else if (error.message.includes('timeout')) {
        message += ': Request timed out. Please try again.';
    } else {
        message += `: ${error.message}`;
    }
    
    showErrorToast(message);
}

/**
 * Show error toast notification
 * @param {string} message - Error message
 * @param {number} duration - Duration in ms (default: 5000)
 */
function showErrorToast(message, duration = 5000) {
    const toast = document.createElement('div');
    toast.className = 'error-toast';
    toast.style.cssText = `
        position: fixed;
        top: 20px;
        right: 20px;
        background: #dc3545;
        color: white;
        padding: 15px 20px;
        border-radius: 8px;
        box-shadow: 0 4px 8px rgba(0,0,0,0.3);
        z-index: 10000;
        max-width: 400px;
        animation: slideIn 0.3s ease-out;
    `;
    toast.innerHTML = `
        <div style="display: flex; align-items: start;">
            <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" fill="currentColor" style="flex-shrink: 0; margin-right: 10px;">
                <path d="M8.982 1.566a1.13 1.13 0 0 0-1.96 0L.165 13.233c-.457.778.091 1.767.98 1.767h13.713c.889 0 1.438-.99.98-1.767L8.982 1.566zM8 5c.535 0 .954.462.9.995l-.35 3.507a.552.552 0 0 1-1.1 0L7.1 5.995A.905.905 0 0 1 8 5zm.002 6a1 1 0 1 1 0 2 1 1 0 0 1 0-2z"/>
            </svg>
            <div>
                <strong>Error</strong><br>
                ${message}
            </div>
        </div>
    `;
    
    document.body.appendChild(toast);
    
    setTimeout(() => {
        toast.style.animation = 'slideOut 0.3s ease-in';
        setTimeout(() => toast.remove(), 300);
    }, duration);
}

/**
 * Show success toast notification
 * @param {string} message - Success message
 * @param {number} duration - Duration in ms (default: 3000)
 */
function showSuccessToast(message, duration = 3000) {
    const toast = document.createElement('div');
    toast.className = 'success-toast';
    toast.style.cssText = `
        position: fixed;
        top: 20px;
        right: 20px;
        background: #28a745;
        color: white;
        padding: 15px 20px;
        border-radius: 8px;
        box-shadow: 0 4px 8px rgba(0,0,0,0.3);
        z-index: 10000;
        max-width: 400px;
        animation: slideIn 0.3s ease-out;
    `;
    toast.innerHTML = `
        <div style="display: flex; align-items: start;">
            <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" fill="currentColor" style="flex-shrink: 0; margin-right: 10px;">
                <path d="M10.97 4.97a.75.75 0 0 1 1.07 1.05l-3.99 4.99a.75.75 0 0 1-1.08.02L4.324 8.384a.75.75 0 1 1 1.06-1.06l2.094 2.093 3.473-4.425a.267.267 0 0 1 .02-.022z"/>
            </svg>
            <div>${message}</div>
        </div>
    `;
    
    document.body.appendChild(toast);
    
    setTimeout(() => {
        toast.style.animation = 'slideOut 0.3s ease-in';
        setTimeout(() => toast.remove(), 300);
    }, duration);
}


// ======================
// ENHANCED FETCH WRAPPER
// ======================

/**
 * Enhanced fetch with loading spinner and error handling
 * @param {string} url - API endpoint
 * @param {Object} options - Fetch options
 * @param {string} loadingMessage - Loading message (optional)
 * @param {boolean} showSpinner - Whether to show loading spinner (default: true)
 * @returns {Promise} - Promise with response data
 */
async function fetchWithHandling(url, options = {}, loadingMessage = 'Loading...', showSpinner = true) {
    if (showSpinner) {
        showGlobalSpinner(loadingMessage);
    }
    
    try {
        const response = await fetch(url, {
            ...options,
            headers: {
                'Content-Type': 'application/json',
                ...options.headers
            }
        });
        
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }
        
        const data = await response.json();
        
        if (showSpinner) {
            hideGlobalSpinner();
        }
        
        return data;
        
    } catch (error) {
        if (showSpinner) {
            hideGlobalSpinner();
        }
        
        handleApiError(error, `fetch ${url}`);
        throw error;
    }
}


// ======================
// STRATEGY OVERLAY IMPLEMENTATION
// ======================

// Store active strategy overlays
const activeStrategyOverlays = new Set();

/**
 * Enhanced toggleStrategyOverlay function
 * Overlays strategy TP/SL levels on main chart
 */
function toggleStrategyOverlay(strategyLetter) {
    const checkbox = document.getElementById(`strategy-${strategyLetter.toLowerCase()}-toggle`);
    if (!checkbox) {
        console.warn(`Checkbox not found for strategy ${strategyLetter}`);
        return;
    }
    
    const isEnabled = checkbox.checked;
    
    // Get current filters
    const symbolFilter = document.getElementById('symbol-filter');
    const directionFilter = document.getElementById('direction-filter');
    
    if (!symbolFilter || !directionFilter) {
        showErrorToast('Please select a symbol and direction to view strategy overlays');
        checkbox.checked = false;
        return;
    }
    
    const symbol = symbolFilter.value;
    const direction = directionFilter.value;
    
    if (symbol === 'ALL' || direction === 'ALL') {
        showErrorToast('Please select a specific symbol and direction to view strategy overlays');
        checkbox.checked = false;
        return;
    }
    
    if (isEnabled) {
        // Add overlay
        activeStrategyOverlays.add(strategyLetter);
        
        fetchWithHandling(
            `/strategies/performance/${symbol}/${direction}/tradingview`,
            {},
            `Loading strategy ${strategyLetter} data...`,
            false  // Don't show global spinner for this
        )
        .then(data => {
            if (data && data.strategies) {
                const strategy = data.strategies.find(s => 
                    s.strategy_name === `strategy_${strategyLetter}`
                );
                
                if (strategy && strategy.current_params) {
                    displayStrategyOverlay(strategy, strategyLetter);
                    showSuccessToast(`Strategy ${strategyLetter} overlay enabled`);
                } else {
                    showErrorToast(`Strategy ${strategyLetter} not found or no data available`);
                    checkbox.checked = false;
                    activeStrategyOverlays.delete(strategyLetter);
                }
            }
        })
        .catch(() => {
            checkbox.checked = false;
            activeStrategyOverlays.delete(strategyLetter);
        });
        
    } else {
        // Remove overlay
        activeStrategyOverlays.delete(strategyLetter);
        removeStrategyOverlayFromChart(strategyLetter);
        showSuccessToast(`Strategy ${strategyLetter} overlay disabled`);
    }
}

/**
 * Display strategy overlay on chart
 * Note: Actual implementation depends on chart library (Chart.js, Plotly, etc.)
 */
function displayStrategyOverlay(strategy, letter) {
    console.log(`Displaying strategy ${letter} overlay:`, strategy.current_params);
    
    // This is a placeholder - actual implementation depends on your chart library
    // For Chart.js with annotation plugin:
    const params = strategy.current_params;
    
    // Store overlay data for rendering
    if (!window.strategyOverlays) {
        window.strategyOverlays = {};
    }
    
    window.strategyOverlays[letter] = {
        tp1: params.tp1,
        tp2: params.tp2,
        tp3: params.tp3,
        sl: params.sl,
        trailing: params.trailing,
        color: {A: '#28a745', B: '#007bff', C: '#ffc107', D: '#dc3545'}[letter]
    };
    
    // Trigger chart update if chart is available
    if (typeof updateChartOverlays === 'function') {
        updateChartOverlays();
    }
}

/**
 * Remove strategy overlay from chart
 */
function removeStrategyOverlayFromChart(letter) {
    if (window.strategyOverlays) {
        delete window.strategyOverlays[letter];
    }
    
    // Trigger chart update
    if (typeof updateChartOverlays === 'function') {
        updateChartOverlays();
    }
}


// ======================
// CSS ANIMATIONS
// ======================

// Add CSS for animations
const style = document.createElement('style');
style.textContent = `
    @keyframes slideIn {
        from {
            transform: translateX(400px);
            opacity: 0;
        }
        to {
            transform: translateX(0);
            opacity: 1;
        }
    }
    
    @keyframes slideOut {
        from {
            transform: translateX(0);
            opacity: 1;
        }
        to {
            transform: translateX(400px);
            opacity: 0;
        }
    }
    
    .loading-spinner-overlay {
        position: absolute;
        top: 0;
        left: 0;
        width: 100%;
        height: 100%;
        background: rgba(255, 255, 255, 0.9);
        display: flex;
        justify-content: center;
        align-items: center;
        z-index: 1000;
    }
    
    .spinner-container {
        text-align: center;
    }
`;
document.head.appendChild(style);


// ======================
// INITIALIZATION
// ======================

console.log('Dashboard improvements loaded successfully');
console.log('Available functions:');
console.log('- showLoadingSpinner(containerId, message)');
console.log('- hideLoadingSpinner(containerId)');
console.log('- showGlobalSpinner(message)');
console.log('- hideGlobalSpinner()');
console.log('- handleFetchErrors(response)');
console.log('- handleApiError(error, context)');
console.log('- showErrorToast(message, duration)');
console.log('- showSuccessToast(message, duration)');
console.log('- fetchWithHandling(url, options, loadingMessage, showSpinner)');
console.log('- toggleStrategyOverlay(strategyLetter)');
