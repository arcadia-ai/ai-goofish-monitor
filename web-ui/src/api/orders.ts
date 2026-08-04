import { http } from '@/lib/http'

export type OrderStatus = 'queued' | 'submitting' | 'submitted_unpaid' | 'blocked' | 'failed' | 'skipped'

export interface OrderRecord {
  id: number
  task_id: number | null
  task_name: string
  account_name: string
  item_id: string
  title: string | null
  item_link: string | null
  value_score: number
  score_threshold: number
  observed_price: number
  max_price: number
  payable_total: number | null
  status: OrderStatus
  reason: string | null
  attempt_count: number
  platform_order_id: string | null
  created_at: string
  updated_at: string
  submitted_at: string | null
}

export interface OrderPage {
  items: OrderRecord[]
  total: number
  page: number
  limit: number
}

export async function listOrders(params: { status?: OrderStatus; page?: number; limit?: number } = {}): Promise<OrderPage> {
  return await http('/api/orders', { params })
}

export async function retryOrder(id: number): Promise<OrderRecord> {
  const response = await http(`/api/orders/${id}/retry`, { method: 'POST' })
  return response.order
}
