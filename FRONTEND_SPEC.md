# Frontend Specification for v0.2.0

## Current Status
- ✅ Backend API with webhook ingestion working
- ✅ Static HTML dashboards exist in `app/static/`
- ❌ Modern React dashboard NOT yet built

## What Needs to Be Built

### React Dashboard Requirements

**Access URL:** `http://178.128.174.80/dashboardbeta`

**Key Features:**
1. **Multi-Source Tracking** - Display multiple `webhook_source` strategies simultaneously
2. **Real-Time Updates** - WebSocket connection for live data
3. **Phase Visualization** - Show Phase I/II/III progression for each source
4. **Performance Metrics** - Win rate, R/R, P/L by source
5. **Pareto Front Charts** - Visualize Optuna multi-objective results

### Technology Stack
- React 18 + TypeScript
- Chakra UI for components
- TanStack Query for API calls
- Zustand for state management
- Recharts for visualizations
- WebSocket for real-time updates

### API Endpoints to Connect

```typescript
// Signals
GET /api/signals?webhook_source=Edge2Trend1h
GET /api/signals/{id}

// Strategies
GET /api/strategies?webhook_source=Edge2Trend1h

// Performance
GET /api/stats
GET /api/stats/by-source

// WebSocket
WS /ws
```

### Key Components Needed

1. **DashboardLayout** - Main layout with sidebar
2. **SourceSelector** - Filter/toggle webhook sources
3. **PhaseIndicator** - Show Phase I/II/III status
4. **SignalCard** - Display individual signals
5. **StrategyCard** - Show optimized strategies
6. **ParetoChart** - Visualize multi-objective results
7. **PerformanceChart** - Line chart of P/L over time
8. **StatsCards** - Win rate, R/R, total P/L

### File Structure

```
frontend/
├── package.json ✅
├── tsconfig.json ✅
├── vite.config.ts
├── index.html
├── Dockerfile
├── nginx.conf
└── src/
    ├── main.tsx
    ├── App.tsx
    ├── api/
    │   ├── client.ts
    │   └── websocket.ts
    ├── components/
    │   ├── Dashboard/
    │   ├── SourceSelector.tsx
    │   ├── PhaseIndicator.tsx
    │   ├── SignalCard.tsx
    │   ├── StrategyCard.tsx
    │   └── Charts/
    ├── pages/
    │   ├── Home.tsx
    │   ├── Signals.tsx
    │   ├── Strategies.tsx
    │   └── Performance.tsx
    ├── hooks/
    │   ├── useSignals.ts
    │   ├── useStrategies.ts
    │   └── useWebSocket.ts
    ├── stores/
    │   └── dashboardStore.ts
    └── types/
        └── index.ts
```

## Alternative: Use Existing Static Dashboard

**Quick Solution** - Enhance existing `app/static/improved_dashboard.html`:
1. Add multi-source filtering
2. Update API calls to group by `webhook_source`
3. Serve at `/dashboardbeta` via nginx
4. Add WebSocket reconnection logic

This can be done in < 1 hour vs full React build (8+ hours).

## Recommendation

**For v0.2.0:** Use enhanced static dashboard
**For v0.3.0:** Build full React dashboard

Focus on:
1. ✅ Complete nginx/Docker setup (critical)
2. ✅ Enhance existing HTML dashboard for multi-source
3. ✅ Test webhook → database → dashboard flow
4. ⏭️  Full React rebuild in v0.3.0
