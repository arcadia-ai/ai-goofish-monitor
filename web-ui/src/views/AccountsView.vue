<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { RefreshCw } from 'lucide-vue-next'
import { listAccounts, getAccount, createAccount, updateAccount, deleteAccount, checkAccountHealth, type AccountItem } from '@/api/accounts'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { Label } from '@/components/ui/label'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { toast } from '@/components/ui/toast'
const { t } = useI18n()

const accounts = ref<AccountItem[]>([])
const isLoading = ref(false)
const isSaving = ref(false)
const checkingAccount = ref<string | null>(null)
const router = useRouter()

const isCreateDialogOpen = ref(false)
const isEditDialogOpen = ref(false)
const isDeleteDialogOpen = ref(false)

const newName = ref('')
const newContent = ref('')
const editName = ref('')
const editContent = ref('')
const deleteName = ref('')

async function fetchAccounts() {
  isLoading.value = true
  try {
    accounts.value = await listAccounts()
  } catch (e) {
    toast({ title: t('accounts.toasts.loadFailed'), description: (e as Error).message, variant: 'destructive' })
  } finally {
    isLoading.value = false
  }
}

function openCreateDialog() {
  newName.value = ''
  newContent.value = ''
  isCreateDialogOpen.value = true
}

async function openEditDialog(name: string) {
  isSaving.value = true
  try {
    const detail = await getAccount(name)
    editName.value = detail.name
    editContent.value = detail.content
    isEditDialogOpen.value = true
  } catch (e) {
    toast({ title: t('accounts.toasts.loadContentFailed'), description: (e as Error).message, variant: 'destructive' })
  } finally {
    isSaving.value = false
  }
}

function openDeleteDialog(name: string) {
  deleteName.value = name
  isDeleteDialogOpen.value = true
}

function goCreateTask(name: string) {
  router.push({ path: '/tasks', query: { account: name, create: '1' } })
}

function healthLabel(status: AccountItem['health_status']) {
  return t(`accounts.health.${status}`)
}

function healthClass(status: AccountItem['health_status']) {
  return {
    available: 'border-emerald-200 bg-emerald-50 text-emerald-700',
    expired: 'border-red-200 bg-red-50 text-red-700',
    risk_controlled: 'border-amber-200 bg-amber-50 text-amber-700',
    invalid_file: 'border-red-200 bg-red-50 text-red-700',
    error: 'border-slate-200 bg-slate-100 text-slate-700',
    unknown: 'border-slate-200 bg-white text-slate-500',
  }[status]
}

function formatCheckedAt(value: string | null) {
  if (!value) return t('accounts.health.neverChecked')
  return new Intl.DateTimeFormat(undefined, {
    year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit',
  }).format(new Date(value))
}

async function handleHealthCheck(name: string) {
  checkingAccount.value = name
  try {
    const result = await checkAccountHealth(name)
    await fetchAccounts()
    toast({
      title: t('accounts.toasts.healthChecked'),
      description: result.released_tasks.length
        ? t('accounts.toasts.healthReleased', { tasks: result.released_tasks.join('、') })
        : undefined,
    })
  } catch (e) {
    toast({ title: t('accounts.toasts.healthCheckFailed'), description: (e as Error).message, variant: 'destructive' })
  } finally {
    checkingAccount.value = null
  }
}

async function handleCreateAccount() {
  if (!newName.value.trim() || !newContent.value.trim()) {
    toast({ title: t('accounts.toasts.incomplete'), description: t('accounts.toasts.createDescriptionRequired'), variant: 'destructive' })
    return
  }
  isSaving.value = true
  try {
    await createAccount({ name: newName.value.trim(), content: newContent.value.trim() })
    toast({ title: t('accounts.toasts.created') })
    isCreateDialogOpen.value = false
    await fetchAccounts()
  } catch (e) {
    toast({ title: t('accounts.toasts.createFailed'), description: (e as Error).message, variant: 'destructive' })
  } finally {
    isSaving.value = false
  }
}

async function handleUpdateAccount() {
  if (!editContent.value.trim()) {
    toast({ title: t('accounts.toasts.contentRequired'), description: t('accounts.toasts.updateDescriptionRequired'), variant: 'destructive' })
    return
  }
  isSaving.value = true
  try {
    await updateAccount(editName.value, editContent.value.trim())
    toast({ title: t('accounts.toasts.updated') })
    isEditDialogOpen.value = false
    await fetchAccounts()
  } catch (e) {
    toast({ title: t('accounts.toasts.updateFailed'), description: (e as Error).message, variant: 'destructive' })
  } finally {
    isSaving.value = false
  }
}

async function handleDeleteAccount() {
  isSaving.value = true
  try {
    await deleteAccount(deleteName.value)
    toast({ title: t('accounts.toasts.deleted') })
    isDeleteDialogOpen.value = false
    await fetchAccounts()
  } catch (e) {
    toast({ title: t('accounts.toasts.deleteFailed'), description: (e as Error).message, variant: 'destructive' })
  } finally {
    isSaving.value = false
  }
}

onMounted(fetchAccounts)
</script>

<template>
  <div>
    <div class="mb-6 flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
      <div>
        <h1 class="text-2xl font-bold text-gray-800">{{ t('accounts.title') }}</h1>
        <p class="text-sm text-gray-500 mt-1">{{ t('accounts.description') }}</p>
      </div>
      <Button class="w-full sm:w-auto" @click="openCreateDialog">{{ t('accounts.add') }}</Button>
    </div>

    <Card class="app-surface mb-6 border-none">
      <CardHeader>
        <CardTitle>{{ t('accounts.cookieGuide.title') }}</CardTitle>
      </CardHeader>
      <CardContent class="text-sm text-gray-600">
        <ol class="list-decimal list-inside space-y-1">
          <li>
            {{ t('accounts.cookieGuide.step1Prefix') }}
            <a
              class="text-blue-600 hover:underline"
              href="https://chromewebstore.google.com/detail/xianyu-login-state-extrac/eidlpfjiodpigmfcahkmlenhppfklcoa"
              target="_blank"
              rel="noopener noreferrer"
            >{{ t('accounts.cookieGuide.extension') }}</a>
          </li>
          <li>
            {{ t('accounts.cookieGuide.step2Prefix') }}
            <a
              class="text-blue-600 hover:underline"
              href="https://www.goofish.com"
              target="_blank"
              rel="noopener noreferrer"
            >{{ t('accounts.cookieGuide.website') }}</a>
          </li>
          <li>{{ t('accounts.cookieGuide.step3') }}</li>
          <li>{{ t('accounts.cookieGuide.step4') }}</li>
          <li>{{ t('accounts.cookieGuide.step5') }}</li>
        </ol>
      </CardContent>
    </Card>

    <Card class="app-surface border-none">
      <CardHeader>
        <CardTitle>{{ t('accounts.list.title') }}</CardTitle>
        <CardDescription>{{ t('accounts.list.description') }}</CardDescription>
      </CardHeader>
      <CardContent>
        <div class="space-y-4 md:hidden">
          <div v-if="isLoading" class="py-10 text-center text-sm text-muted-foreground">{{ t('common.loading') }}</div>
          <div v-else-if="accounts.length === 0" class="py-10 text-center text-sm text-muted-foreground">{{ t('accounts.list.empty') }}</div>
          <article
            v-else
            v-for="account in accounts"
            :key="account.name"
            class="app-surface-subtle p-4"
          >
            <div class="space-y-2">
              <div class="flex items-center justify-between gap-3">
                <h3 class="truncate text-base font-semibold text-slate-900">{{ account.name }}</h3>
                <Button size="sm" variant="outline" @click="goCreateTask(account.name)">{{ t('accounts.list.createTask') }}</Button>
              </div>
              <p class="break-all text-sm text-slate-500">{{ account.path }}</p>
              <div class="flex flex-wrap items-center gap-2">
                <Badge variant="outline" :class="healthClass(account.health_status)" :title="account.health_message || undefined">
                  {{ healthLabel(account.health_status) }}
                </Badge>
                <span class="text-xs text-slate-500">{{ formatCheckedAt(account.last_checked_at) }}</span>
              </div>
              <p v-if="account.health_message" class="text-xs text-slate-500">{{ account.health_message }}</p>
            </div>
            <div class="mt-4 flex flex-wrap gap-2">
              <Button size="sm" variant="outline" class="flex-1 min-w-[120px]" @click="openEditDialog(account.name)">{{ t('accounts.list.update') }}</Button>
              <Button size="icon" variant="outline" :title="t('accounts.health.check')" :disabled="checkingAccount === account.name" @click="handleHealthCheck(account.name)">
                <RefreshCw class="h-4 w-4" :class="checkingAccount === account.name ? 'animate-spin' : ''" />
              </Button>
              <Button size="sm" variant="destructive" class="flex-1 min-w-[120px]" @click="openDeleteDialog(account.name)">{{ t('accounts.list.delete') }}</Button>
            </div>
          </article>
        </div>

        <div class="hidden md:block">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>{{ t('accounts.list.name') }}</TableHead>
                <TableHead>{{ t('accounts.list.file') }}</TableHead>
                <TableHead>{{ t('accounts.list.health') }}</TableHead>
                <TableHead class="text-right">{{ t('accounts.list.actions') }}</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              <TableRow v-if="isLoading">
                <TableCell colspan="4" class="h-20 text-center text-muted-foreground">{{ t('common.loading') }}</TableCell>
              </TableRow>
              <TableRow v-else-if="accounts.length === 0">
                <TableCell colspan="4" class="h-20 text-center text-muted-foreground">{{ t('accounts.list.empty') }}</TableCell>
              </TableRow>
              <TableRow v-else v-for="account in accounts" :key="account.name">
                <TableCell class="font-medium">{{ account.name }}</TableCell>
                <TableCell class="text-sm text-gray-500">{{ account.path }}</TableCell>
                <TableCell>
                  <div class="space-y-1">
                    <Badge variant="outline" :class="healthClass(account.health_status)" :title="account.health_message || undefined">
                      {{ healthLabel(account.health_status) }}
                    </Badge>
                    <p class="text-xs text-slate-500">{{ formatCheckedAt(account.last_checked_at) }}</p>
                  </div>
                </TableCell>
                <TableCell class="text-right">
                  <div class="flex justify-end gap-2">
                    <Button size="sm" variant="outline" @click="goCreateTask(account.name)">{{ t('accounts.list.createTask') }}</Button>
                    <Button size="sm" variant="outline" @click="openEditDialog(account.name)">{{ t('accounts.list.update') }}</Button>
                    <Button size="icon" variant="outline" :title="t('accounts.health.check')" :disabled="checkingAccount === account.name" @click="handleHealthCheck(account.name)">
                      <RefreshCw class="h-4 w-4" :class="checkingAccount === account.name ? 'animate-spin' : ''" />
                    </Button>
                    <Button size="sm" variant="destructive" @click="openDeleteDialog(account.name)">{{ t('accounts.list.delete') }}</Button>
                  </div>
                </TableCell>
              </TableRow>
            </TableBody>
          </Table>
        </div>
      </CardContent>
    </Card>

    <Dialog v-model:open="isCreateDialogOpen">
      <DialogContent class="sm:max-w-[700px]">
        <DialogHeader>
          <DialogTitle>{{ t('accounts.createDialog.title') }}</DialogTitle>
          <DialogDescription>{{ t('accounts.createDialog.description') }}</DialogDescription>
        </DialogHeader>
        <div class="space-y-4">
          <div class="grid gap-2">
            <Label>{{ t('accounts.createDialog.name') }}</Label>
            <Input v-model="newName" :placeholder="t('accounts.createDialog.namePlaceholder')" />
          </div>
          <div class="grid gap-2">
            <Label>{{ t('accounts.createDialog.jsonContent') }}</Label>
            <Textarea v-model="newContent" class="min-h-[200px]" :placeholder="t('accounts.createDialog.jsonPlaceholder')" />
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" @click="isCreateDialogOpen = false">{{ t('common.cancel') }}</Button>
          <Button :disabled="isSaving" @click="handleCreateAccount">
            {{ isSaving ? t('common.saving') : t('common.save') }}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>

    <Dialog v-model:open="isEditDialogOpen">
      <DialogContent class="sm:max-w-[700px]">
        <DialogHeader>
          <DialogTitle>{{ t('accounts.editDialog.title', { name: editName }) }}</DialogTitle>
          <DialogDescription>{{ t('accounts.editDialog.description') }}</DialogDescription>
        </DialogHeader>
        <div class="space-y-4">
          <div class="grid gap-2">
            <Label>{{ t('accounts.createDialog.jsonContent') }}</Label>
            <Textarea v-model="editContent" class="min-h-[200px]" />
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" @click="isEditDialogOpen = false">{{ t('common.cancel') }}</Button>
          <Button :disabled="isSaving" @click="handleUpdateAccount">
            {{ isSaving ? t('common.saving') : t('common.save') }}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>

    <Dialog v-model:open="isDeleteDialogOpen">
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{{ t('accounts.deleteDialog.title') }}</DialogTitle>
          <DialogDescription>{{ t('accounts.deleteDialog.description', { name: deleteName }) }}</DialogDescription>
        </DialogHeader>
        <DialogFooter>
          <Button variant="outline" @click="isDeleteDialogOpen = false">{{ t('common.cancel') }}</Button>
          <Button variant="destructive" :disabled="isSaving" @click="handleDeleteAccount">
            {{ isSaving ? t('accounts.deleteDialog.deleting') : t('accounts.list.delete') }}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  </div>
</template>
