import { Box } from '@chakra-ui/react'
import { BrowserRouter, Routes, Route } from 'react-router-dom'
import { useWebSocket } from './hooks/useWebSocket'
import DashboardLayout from './components/Dashboard/DashboardLayout'
import Home from './pages/Home'
import Signals from './pages/Signals'
import Strategies from './pages/Strategies'
import Performance from './pages/Performance'

function App() {
  // Initialize WebSocket connection
  useWebSocket()

  return (
    <BrowserRouter>
      <Box minH="100vh" bg="gray.50">
        <Routes>
          <Route path="/" element={<DashboardLayout />}>
            <Route index element={<Home />} />
            <Route path="signals" element={<Signals />} />
            <Route path="strategies" element={<Strategies />} />
            <Route path="performance" element={<Performance />} />
          </Route>
        </Routes>
      </Box>
    </BrowserRouter>
  )
}

export default App
