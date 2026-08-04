<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { ChevronLeft, ChevronRight, ExternalLink, RefreshCw, RotateCcw } from 'lucide-vue-next'
import { listOrders, retryOrder, type OrderRecord, type OrderStatus } from '@/api/orders'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { toast } from '@/components/ui/toast'

const { t } = useI18n()
const records = ref<OrderRecord[]>([])
const total = ref(0)
const page = ref(1)
const limit = 20
const statusFilter = ref('all')
const isLoading = ref(false)
const retryingId = ref<number | null>(null)
const totalPages = computed(() => Math.max(1, Math.ceil(total.value / limit)))

const statuses: OrderStatus[] = ['queued', 'submitting', 'submitted_unpaid', 'blocked', 'failed', 'skipped']

function statusClass(status: OrderStatus) {
  return {
    queued: 'border-slate-200 bg-slate-50 text-slate-700',
    submitting: 'border-blue-200 bg-blue-50 text-blue-700',
    submitted_unpaid: 'border-emerald-200 bg-emerald-50 text-emerald-700',
    blocked: 'border-amber-200 bg-amber-50 text-amber-700',
    failed: 'border-red-200 bg-red-50 text-red-700',
    skipped: 'border-slate-200 bg-white text-slate-500',
  }[status]
}

function canRetry(record: OrderRecord) {
  return ['blocked', 'failed', 'skipped'].includes(record.status)
}

function formatDate(value: string) {
  return new Intl.DateTimeFormat(undefined, {
    year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit',
  }).format(new Date(value))
}

function formatMoney(value: number | null) {
  return value === null ? '-' : `¥${Number(value).toFixed(2)}`
}

async function fetchOrders() {
  isLoading.value = true
  try {
    const result = await listOrders({
      status: statusFilter.value === 'all' ? undefined : statusFilter.value as OrderStatus,
      page: page.value,
      limit,
    })
    records.value = result.items
    total.value = result.total
  } catch (e) {
    toast({ title: t('orders.toasts.loadFailed'), description: (e as Error).message, variant: 'destructive' })
  } finally {
    isLoading.value = false
  }
}

async function changeStatus(value: unknown) {
  if (typeof value !== 'string') return
  statusFilter.value = value
  page.value = 1
  await fetchOrders()
}

async function changePage(nextPage: number) {
  page.value = Math.min(Math.max(1, nextPage), totalPages.value)
  await fetchOrders()
}

async function handleRetry(record: OrderRecord) {
  retryingId.value = record.id
  try {
    await retryOrder(record.id)
    toast({ title: t('orders.toasts.retryCompleted') })
    await fetchOrders()
  } catch (e) {
    toast({ title: t('orders.toasts.retryFailed'), description: (e as Error).message, variant: 'destructive' })
  } finally {
    retryingId.value = null
  }
}

onMounted(fetchOrders)
</script>

<template>
  <div class="space-y-5">
    <header class="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
      <div>
        <h1 class="text-2xl font-bold text-slate-800">{{ t('orders.title') }}</h1>
        <p class="mt-1 text-sm text-slate-500">{{ t('orders.description') }}</p>
      </div>
      <div class="flex gap-2">
        <Select :model-value="statusFilter" @update:model-value="changeStatus">
          <SelectTrigger class="w-[180px]"><SelectValue /></SelectTrigger>
          <SelectContent>
            <SelectItem value="all">{{ t('orders.allStatuses') }}</SelectItem>
            <SelectItem v-for="status in statuses" :key="status" :value="status">{{ t(`orders.status.${status}`) }}</SelectItem>
          </SelectContent>
        </Select>
        <Button size="icon" variant="outline" :title="t('common.refresh')" :disabled="isLoading" @click="fetchOrders">
          <RefreshCw class="h-4 w-4" :class="isLoading ? 'animate-spin' : ''" />
        </Button>
      </div>
    </header>

    <Card class="app-surface border-none">
      <CardContent class="p-0">
        <div class="space-y-3 p-4 md:hidden">
          <p v-if="isLoading" class="py-10 text-center text-sm text-slate-500">{{ t('common.loading') }}</p>
          <p v-else-if="records.length === 0" class="py-10 text-center text-sm text-slate-500">{{ t('orders.empty') }}</p>
          <article v-for="record in records" v-else :key="record.id" class="app-surface-subtle space-y-3 p-4">
            <div class="flex items-start justify-between gap-3">
              <div class="min-w-0">
                <p class="truncate font-semibold text-slate-900">{{ record.title || record.item_id }}</p>
                <p class="text-xs text-slate-500">{{ record.task_name }} · {{ record.account_name }}</p>
              </div>
              <Badge variant="outline" :class="statusClass(record.status)">{{ t(`orders.status.${record.status}`) }}</Badge>
            </div>
            <div class="grid grid-cols-2 gap-2 text-sm">
              <span>{{ t('orders.score') }}: {{ record.value_score }}</span>
              <span>{{ t('orders.amount') }}: {{ formatMoney(record.payable_total ?? record.observed_price) }}</span>
            </div>
            <p v-if="record.reason" class="break-words text-xs text-slate-500">{{ record.reason }}</p>
            <div class="flex items-center justify-between gap-2">
              <span class="text-xs text-slate-500">{{ formatDate(record.updated_at) }}</span>
              <div class="flex gap-2">
                <Button v-if="record.item_link" size="icon" variant="outline" as="a" :href="record.item_link" target="_blank" :title="t('orders.openItem')"><ExternalLink class="h-4 w-4" /></Button>
                <Button v-if="canRetry(record)" size="icon" variant="outline" :title="t('orders.retry')" :disabled="retryingId === record.id" @click="handleRetry(record)"><RotateCcw class="h-4 w-4" :class="retryingId === record.id ? 'animate-spin' : ''" /></Button>
              </div>
            </div>
          </article>
        </div>

        <div class="hidden overflow-x-auto md:block">
          <Table>
            <TableHeader><TableRow>
              <TableHead>{{ t('orders.item') }}</TableHead><TableHead>{{ t('orders.taskAccount') }}</TableHead>
              <TableHead>{{ t('orders.score') }}</TableHead><TableHead>{{ t('orders.amount') }}</TableHead>
              <TableHead>{{ t('orders.statusLabel') }}</TableHead><TableHead>{{ t('orders.updatedAt') }}</TableHead>
              <TableHead class="text-right">{{ t('orders.actions') }}</TableHead>
            </TableRow></TableHeader>
            <TableBody>
              <TableRow v-if="isLoading"><TableCell colspan="7" class="h-24 text-center text-slate-500">{{ t('common.loading') }}</TableCell></TableRow>
              <TableRow v-else-if="records.length === 0"><TableCell colspan="7" class="h-24 text-center text-slate-500">{{ t('orders.empty') }}</TableCell></TableRow>
              <TableRow v-for="record in records" v-else :key="record.id">
                <TableCell class="max-w-[240px]"><p class="truncate font-medium">{{ record.title || record.item_id }}</p><p class="text-xs text-slate-500">#{{ record.item_id }}</p></TableCell>
                <TableCell><p>{{ record.task_name }}</p><p class="text-xs text-slate-500">{{ record.account_name }}</p></TableCell>
                <TableCell>{{ record.value_score }} / {{ record.score_threshold }}</TableCell>
                <TableCell><p>{{ formatMoney(record.payable_total ?? record.observed_price) }}</p><p class="text-xs text-slate-500">{{ t('orders.cap') }} {{ formatMoney(record.max_price) }}</p></TableCell>
                <TableCell><Badge variant="outline" :class="statusClass(record.status)" :title="record.reason || undefined">{{ t(`orders.status.${record.status}`) }}</Badge><p v-if="record.reason" class="mt-1 max-w-[220px] truncate text-xs text-slate-500">{{ record.reason }}</p></TableCell>
                <TableCell class="whitespace-nowrap text-sm text-slate-500">{{ formatDate(record.updated_at) }}</TableCell>
                <TableCell><div class="flex justify-end gap-2">
                  <Button v-if="record.item_link" size="icon" variant="outline" as="a" :href="record.item_link" target="_blank" :title="t('orders.openItem')"><ExternalLink class="h-4 w-4" /></Button>
                  <Button v-if="canRetry(record)" size="icon" variant="outline" :title="t('orders.retry')" :disabled="retryingId === record.id" @click="handleRetry(record)"><RotateCcw class="h-4 w-4" :class="retryingId === record.id ? 'animate-spin' : ''" /></Button>
                </div></TableCell>
              </TableRow>
            </TableBody>
          </Table>
        </div>
      </CardContent>
    </Card>

    <footer class="flex items-center justify-between text-sm text-slate-500">
      <span>{{ t('orders.total', { count: total }) }}</span>
      <div class="flex items-center gap-2">
        <Button size="icon" variant="outline" :disabled="page <= 1" :title="t('orders.previous')" @click="changePage(page - 1)"><ChevronLeft class="h-4 w-4" /></Button>
        <span>{{ page }} / {{ totalPages }}</span>
        <Button size="icon" variant="outline" :disabled="page >= totalPages" :title="t('orders.next')" @click="changePage(page + 1)"><ChevronRight class="h-4 w-4" /></Button>
      </div>
    </footer>
  </div>
</template>
