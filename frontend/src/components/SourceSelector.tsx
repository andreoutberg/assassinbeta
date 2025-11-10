import React from 'react'
import { Select, FormControl, FormLabel, Skeleton } from '@chakra-ui/react'
import { useDashboardStore } from '@/stores/dashboardStore'
import { useWebhookSources } from '@/hooks/useStats'

const SourceSelector: React.FC = () => {
  const { filters, setWebhookSource } = useDashboardStore()
  const { data: sources, isLoading, error } = useWebhookSources()

  const handleChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    const value = e.target.value
    setWebhookSource(value === 'all' ? null : value)
  }

  if (isLoading) {
    return (
      <FormControl>
        <FormLabel>Webhook Source</FormLabel>
        <Skeleton height="40px" />
      </FormControl>
    )
  }

  if (error || !sources) {
    return (
      <FormControl>
        <FormLabel>Webhook Source</FormLabel>
        <Select isDisabled placeholder="Error loading sources" />
      </FormControl>
    )
  }

  return (
    <FormControl>
      <FormLabel>Webhook Source</FormLabel>
      <Select
        value={filters.webhook_source || 'all'}
        onChange={handleChange}
        placeholder="Select source"
      >
        <option value="all">All Sources</option>
        {sources.map((source) => (
          <option key={source} value={source}>
            {source}
          </option>
        ))}
      </Select>
    </FormControl>
  )
}

export default SourceSelector