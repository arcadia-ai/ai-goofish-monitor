import { http } from '@/lib/http'

export interface AccountItem {
  name: string
  path: string
  health_status: 'unknown' | 'available' | 'expired' | 'risk_controlled' | 'invalid_file' | 'error'
  health_source: string | null
  last_checked_at: string | null
  last_success_at: string | null
  health_message: string | null
}

export interface AccountDetail extends AccountItem {
  content: string
}

export interface AccountHealthCheckResult extends Omit<AccountItem, 'name' | 'path'> {
  released_tasks: string[]
}

export async function listAccounts(): Promise<AccountItem[]> {
  return await http('/api/accounts')
}

export async function getAccount(name: string): Promise<AccountDetail> {
  return await http(`/api/accounts/${encodeURIComponent(name)}`)
}

export async function createAccount(payload: { name: string; content: string }): Promise<AccountDetail> {
  return await http('/api/accounts', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
}

export async function updateAccount(name: string, content: string): Promise<AccountDetail> {
  return await http(`/api/accounts/${encodeURIComponent(name)}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ content }),
  })
}

export async function deleteAccount(name: string): Promise<{ message: string }> {
  return await http(`/api/accounts/${encodeURIComponent(name)}`, { method: 'DELETE' })
}

export async function checkAccountHealth(name: string): Promise<AccountHealthCheckResult> {
  return await http(`/api/accounts/${encodeURIComponent(name)}/health-check`, { method: 'POST' })
}
