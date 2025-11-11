import React from 'react'
import { Outlet, Link as RouterLink, useLocation } from 'react-router-dom'
import {
  Box,
  Flex,
  VStack,
  HStack,
  Text,
  Icon,
  IconButton,
  Heading,
  Badge,
  Drawer,
  DrawerContent,
  DrawerOverlay,
  useDisclosure,
  Container,
  Button,
} from '@chakra-ui/react'
import {
  FiHome,
  FiTrendingUp,
  FiLayers,
  FiBarChart2,
  FiActivity,
  FiMenu,
  FiX,
} from 'react-icons/fi'
import { useDashboardStore } from '@/stores/dashboardStore'

interface NavItem {
  name: string
  icon: typeof FiHome
  path: string
}

const navItems: NavItem[] = [
  { name: 'Home', icon: FiHome, path: '/dashboard' },
  { name: 'Signals', icon: FiTrendingUp, path: '/dashboard/signals' },
  { name: 'Strategies', icon: FiLayers, path: '/dashboard/strategies' },
  { name: 'Performance', icon: FiBarChart2, path: '/dashboard/performance' },
  { name: 'System', icon: FiActivity, path: '/dashboard/system' },
]

const DashboardLayout: React.FC = () => {
  const location = useLocation()
  const { isOpen, onOpen, onClose } = useDisclosure()
  const { wsConnected } = useDashboardStore()

  // Force dark theme colors
  const bgColor = 'black'
  const sidebarBg = 'gray.900'
  const borderColor = 'gray.800'

  const SidebarContent = () => (
    <VStack
      as="nav"
      h="full"
      p={4}
      spacing={4}
      align="stretch"
      bg={sidebarBg}
      borderRightWidth="1px"
      borderColor={borderColor}
    >
      <Flex align="center" justify="space-between" mb={6}>
        <Heading size="lg" color="rgba(255, 255, 255, 0.95)">Andre Assassin</Heading>
        {isOpen && (
          <IconButton
            aria-label="Close menu"
            icon={<FiX />}
            size="sm"
            variant="ghost"
            onClick={onClose}
            display={{ base: 'flex', md: 'none' }}
          />
        )}
      </Flex>

      <VStack spacing={2} align="stretch">
        {navItems.map((item) => {
          const isActive = location.pathname === item.path
          return (
            <Button
              key={item.path}
              as={RouterLink}
              to={item.path}
              leftIcon={<Icon as={item.icon} />}
              variant={isActive ? 'solid' : 'ghost'}
              bg={isActive ? '#D4AF37' : 'transparent'}
              color={isActive ? '#000' : 'rgba(255, 255, 255, 0.85)'}
              _hover={{ bg: isActive ? '#b8941f' : 'rgba(255, 255, 255, 0.1)' }}
              justifyContent="flex-start"
              w="full"
              onClick={onClose}
            >
              {item.name}
            </Button>
          )
        })}
      </VStack>

      <Box mt="auto" pt={4} borderTopWidth="1px" borderColor={borderColor}>
        <HStack spacing={2}>
          <Box
            w={2}
            h={2}
            borderRadius="full"
            bg={wsConnected ? 'green.400' : 'red.400'}
          />
          <Text fontSize="sm" color="rgba(255, 255, 255, 0.70)">
            WebSocket: {wsConnected ? 'Connected' : 'Disconnected'}
          </Text>
        </HStack>
      </Box>
    </VStack>
  )

  return (
    <Flex h="100vh" bg={bgColor}>
      {/* Desktop Sidebar */}
      <Box
        display={{ base: 'none', md: 'block' }}
        w="250px"
        h="full"
        position="sticky"
        top={0}
      >
        <SidebarContent />
      </Box>

      {/* Mobile Sidebar Drawer */}
      <Drawer isOpen={isOpen} placement="left" onClose={onClose}>
        <DrawerOverlay />
        <DrawerContent>
          <SidebarContent />
        </DrawerContent>
      </Drawer>

      {/* Main Content Area */}
      <Flex flex="1" direction="column" overflow="hidden">
        {/* Mobile Header */}
        <Flex
          display={{ base: 'flex', md: 'none' }}
          align="center"
          justify="space-between"
          p={4}
          borderBottomWidth="1px"
          borderColor={borderColor}
          bg={sidebarBg}
        >
          <IconButton
            aria-label="Open menu"
            icon={<FiMenu />}
            onClick={onOpen}
            variant="ghost"
          />
          <Heading size="md" color="rgba(255, 255, 255, 0.95)">Andre Assassin</Heading>
          <Badge colorScheme={wsConnected ? 'green' : 'red'}>
            {wsConnected ? 'Online' : 'Offline'}
          </Badge>
        </Flex>

        {/* Page Content */}
        <Box flex="1" overflow="auto">
          <Container maxW="container.2xl" py={6}>
            <Outlet />
          </Container>
        </Box>
      </Flex>
    </Flex>
  )
}

export default DashboardLayout