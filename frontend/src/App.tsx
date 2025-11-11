import { lazy, Suspense } from 'react'
import { Box } from '@chakra-ui/react'
import { BrowserRouter, Routes, Route } from 'react-router-dom'
import { useWebSocket } from './hooks/useWebSocket'
import DashboardLayout from './components/Dashboard/DashboardLayout'

// Lazy load page components
const Home = lazy(() => import('./pages/Home').then(module => ({ default: module.Home })))
const Signals = lazy(() => import('./pages/Signals'))
const Strategies = lazy(() => import('./pages/Strategies'))
const Performance = lazy(() => import('./pages/Performance'))
const System = lazy(() => import('./pages/System'))

// Loading spinner component
const LoadingSpinner = () => (
  <Box display="flex" alignItems="center" justifyContent="center" minH="100vh">
    <Box className="animate-spin rounded-full h-12 w-12 border-b-2 border-gold"></Box>
  </Box>
)

function App() {
  // Initialize WebSocket connection
  useWebSocket()

  return (
    <BrowserRouter>
      <Box minH="100vh" bg="black">
        <Suspense fallback={<LoadingSpinner />}>
          <Routes>
            <Route path="/dashboard" element={<DashboardLayout />}>
              <Route index element={<Home />} />
              <Route path="signals" element={<Signals />} />
              <Route path="strategies" element={<Strategies />} />
              <Route path="performance" element={<Performance />} />
              <Route path="system" element={<System />} />
            </Route>
            {/* Redirect root to dashboard */}
            <Route path="/" element={<DashboardLayout />}>
              <Route index element={<Home />} />
            </Route>
          </Routes>
        </Suspense>
      </Box>
    </BrowserRouter>
  )
}

export default App
