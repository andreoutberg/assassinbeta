// API client for backend communication

const API_BASE_URL = import.meta.env.VITE_PUBLIC_API_URL || 'http://localhost:8000'

export class ApiClient {
  private baseUrl: string

  constructor(baseUrl: string = API_BASE_URL) {
    this.baseUrl = baseUrl
  }

  private async request<T>(endpoint: string, options?: RequestInit): Promise<T> {
    const url = `${this.baseUrl}${endpoint}`

    try {
      const response = await fetch(url, {
        ...options,
        headers: {
          'Content-Type': 'application/json',
          ...options?.headers,
        },
      })

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`)
      }

      return await response.json()
    } catch (error) {
      console.error(`API request failed: ${url}`, error)
      throw error
    }
  }

  // Signals
  async getSignals(params?: { webhook_source?: string; phase?: string; limit?: number }) {
    const queryString = params ? `?${new URLSearchParams(params as any)}` : ''
    return this.request(`/api/signals${queryString}`)
  }

  async getSignal(id: number) {
    return this.request(`/api/signals/${id}`)
  }

  // Strategies
  async getStrategies(params?: { webhook_source?: string; phase?: string; is_active?: boolean }) {
    const queryString = params ? `?${new URLSearchParams(params as any)}` : ''
    return this.request(`/api/strategies${queryString}`)
  }

  async getStrategy(id: number) {
    return this.request(`/api/strategies/${id}`)
  }

  async getStrategyPerformance(id: number) {
    return this.request(`/api/strategies/${id}/performance`)
  }

  // Stats
  async getStats() {
    return this.request('/api/stats')
  }

  async getStatsBySource() {
    return this.request('/api/stats/by-source')
  }

  // Webhook sources
  async getWebhookSources() {
    return this.request<string[]>('/api/webhook-sources')
  }

  // Optuna studies (if exposed via API)
  async getOptunaStudies() {
    try {
      return await this.request('/api/optuna/studies')
    } catch {
      // Fallback if endpoint doesn't exist
      return []
    }
  }

  async getOptunaStudy(studyName: string) {
    try {
      return await this.request(`/api/optuna/studies/${studyName}`)
    } catch {
      return null
    }
  }
}

export const apiClient = new ApiClient()
