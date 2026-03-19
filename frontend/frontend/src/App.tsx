import { useState, useMemo, useEffect } from 'react'
import './App.css'

type ShiftDto = {
  id: number
  user_id: number
  schedule_id: number
  data: string
  codigo: string
  color_bucket?: string | null
  inconsistency_flag?: boolean | null
  inconsistency_message?: string | null
  origin_status?: string | null
}

type OnDutyPerson = {
  employee_number: string
  nome: string
  team: string | null
  origin_status?: string | null
  show_troca_bht?: boolean
}

type UserSearchResult = {
  id: number
  nome: string
  employee_number: string
  team_id?: number | null
}

type NotificationDto = {
  id: number
  user_id: number
  swap_request_id: number
  created_at: string
  read_at: string | null
  notification_kind?: string
  requester_name: string | null
  offered_shift_date: string | null
  offered_shift_code: string | null
  accepted_shift_types: string[] | null
  rejected_by_name?: string | null
}

type SwapActionDto = {
  id: number
  swap_request_id: number
  action_type: string // ACCEPTED | REJECTED
  actor_id: number
  requester_id: number
  offered_shift_code: string
  offered_shift_date: string // YYYY-MM-DD
  requester_name: string
  actor_name: string
  created_at: string
}

type MySwapRequestDto = {
  id: number
  status: string
  kind: 'direct' | 'same_day' | 'other_days'
  offered_shift_date: string
  offered_shift_code: string
  acceptable_shift_types: string[] | null
  wanted_options: { date: string; shift_types: string[] }[] | null
  direct_targets: { nome: string; employee_number: string }[] | null
  accepter_name: string | null
}

const SHIFT_CODES = ['M', 'T', 'N', 'MG', 'Mt', 'DC', 'DS']

/** Timeout longo para dar tempo ao Render (free) acordar (~1 min). */
const API_FETCH_TIMEOUT_MS = 90000
/** Mensagem quando falha a ligação (servidor pode estar a iniciar). */
const NETWORK_ERROR_MESSAGE =
  'Ligação falhou. O servidor pode estar a iniciar (até 1 min). Por favor tente novamente.'

function isNetworkError(e: unknown): boolean {
  if (e instanceof TypeError) return true
  const msg = e instanceof Error ? e.message : String(e)
  const s = msg.toLowerCase()
  return (
    s.includes('networkerror') ||
    s.includes('failed to fetch') ||
    s.includes('load failed') ||
    s.includes('network request failed') ||
    s.includes('attempting to fetch') ||
    s.includes('fetch resource')
  )
}

/**
 * fetch com timeout e retry em caso de erro de rede (útil quando o backend está no Render free).
 */
async function apiFetch(
  url: string,
  options: RequestInit = {},
  retries = 2,
): Promise<Response> {
  const controller = new AbortController()
  const timeoutId = setTimeout(() => controller.abort(), API_FETCH_TIMEOUT_MS)
  let lastError: unknown
  for (let attempt = 0; attempt <= retries; attempt++) {
    try {
      const res = await fetch(url, {
        ...options,
        signal: controller.signal,
      })
      clearTimeout(timeoutId)
      return res
    } catch (e) {
      lastError = e
      clearTimeout(timeoutId)
      const isAbort = e instanceof Error && e.name === 'AbortError'
      const isNet = isNetworkError(e)
      if ((isAbort || isNet) && attempt < retries) {
        await new Promise((r) => setTimeout(r, 8000))
        continue
      }
      throw e
    }
  }
  throw lastError
}

// Em produção: definir VITE_API_URL no build (ex.: https://teu-backend.onrender.com)
const API_BASE =
  typeof import.meta.env !== 'undefined' && import.meta.env.VITE_API_URL
    ? import.meta.env.VITE_API_URL.replace(/\/$/, '')
    : typeof window !== 'undefined'
      ? `${window.location.protocol}//${window.location.hostname}:8000`
      : 'http://127.0.0.1:8000'

// Só mostrar "Importar escalas" em local: em produção (Render) não há PDFs no servidor
const SHOW_IMPORT_BUTTON = API_BASE.includes('localhost') || API_BASE.includes('127.0.0.1')

const MONTH_NAMES = [
  'Janeiro', 'Fevereiro', 'Março', 'Abril', 'Maio', 'Junho',
  'Julho', 'Agosto', 'Setembro', 'Outubro', 'Novembro', 'Dezembro',
]

function getDaysInMonth(year: number, month: number): number {
  return new Date(year, month, 0).getDate()
}

function getFirstWeekday(year: number, month: number): number {
  return new Date(year, month - 1, 1).getDay()
}

function backgroundColor(bucket: string | null | undefined): string {
  if (!bucket) return 'var(--shift-default)'
  switch (bucket) {
    case 'red': return 'var(--shift-red)'
    case 'pink': return 'var(--shift-pink)'
    case 'gray_light': return 'var(--shift-gray-light)'
    case 'gray_dark': return 'var(--shift-gray-dark)'
    case 'lime': return 'var(--shift-lime)'
    case 'yellow': return 'var(--shift-yellow)'
    default: return 'var(--shift-default)'
  }
}

function formatSwapActionOfferedDatePt(isoDate: string | null | undefined): string {
  if (!isoDate) return ''
  // Expected: YYYY-MM-DD
  const day = Number(isoDate.slice(8, 10))
  const monthIdx = Number(isoDate.slice(5, 7)) - 1
  const monthName = MONTH_NAMES[monthIdx]?.toLowerCase() ?? ''
  if (!day || !monthName) return isoDate
  return `dia ${day} ${monthName}`
}

function App() {
  const [employeeNumber, setEmployeeNumber] = useState('405541')
  const [year, setYear] = useState(2026)
  const [month, setMonth] = useState(3)
  const [shifts, setShifts] = useState<ShiftDto[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const [onDutyDayInput, setOnDutyDayInput] = useState('5')
  const [onDutyCode, setOnDutyCode] = useState('M')
  const [onDutyList, setOnDutyList] = useState<OnDutyPerson[]>([])
  const [onDutyLoading, setOnDutyLoading] = useState(false)
  const [onDutyError, setOnDutyError] = useState<string | null>(null)
  const [onDutySearched, setOnDutySearched] = useState(false)

  const [selectedShift, setSelectedShift] = useState<ShiftDto | null>(null)
  const [sameDayTypes, setSameDayTypes] = useState<string[]>([])
  const [wantedRows, setWantedRows] = useState<{ date: string; shift_types: string[] }[]>([{ date: '', shift_types: [] }])
  const [swapSubmitLoading, setSwapSubmitLoading] = useState(false)
  const [swapSubmitError, setSwapSubmitError] = useState<string | null>(null)
  const [swapSubmitSuccess, setSwapSubmitSuccess] = useState(false)
  const [existingSwapIdToCancel, setExistingSwapIdToCancel] = useState<number | null>(null)

  const [directQuery, setDirectQuery] = useState('')
  const [directResults, setDirectResults] = useState<UserSearchResult[]>([])
  const [directTargets, setDirectTargets] = useState<UserSearchResult[]>([])

  const [notifications, setNotifications] = useState<NotificationDto[]>([])
  const [notificationsLoading, setNotificationsLoading] = useState(false)
  const [notificationsEnabled, setNotificationsEnabled] = useState(true)
  const [acceptSwapLoading, setAcceptSwapLoading] = useState<number | null>(null)
  const [acceptSwapError, setAcceptSwapError] = useState<string | null>(null)
  const [rejectSwapLoading, setRejectSwapLoading] = useState<number | null>(null)
  const [rejectSwapError, setRejectSwapError] = useState<string | null>(null)

  const [swapActions, setSwapActions] = useState<SwapActionDto[]>([])
  const [swapActionsLoading, setSwapActionsLoading] = useState(false)
  const [dismissHistoryId, setDismissHistoryId] = useState<number | null>(null)

  const [mySwapRequests, setMySwapRequests] = useState<MySwapRequestDto[]>([])
  const [mySwapsLoading, setMySwapsLoading] = useState(false)

  const [importLoading, setImportLoading] = useState(false)
  const [importResult, setImportResult] = useState<{ teams: string[]; warning?: string } | null>(null)

  const [loginEmail, setLoginEmail] = useState('')
  const [loginPassword, setLoginPassword] = useState('')
  const [loginError, setLoginError] = useState<string | null>(null)
  const [loginLoading, setLoginLoading] = useState(false)
  const [currentUser, setCurrentUser] = useState<{ id?: number; nome: string; email: string; employee_number: string } | null>(null)

  const shiftsByDate = useMemo(() => {
    const map: Record<string, ShiftDto> = {}
    for (const s of shifts) {
      map[s.data] = s
    }
    return map
  }, [shifts])

  const daysInMonth = getDaysInMonth(year, month)
  const firstWeekday = getFirstWeekday(year, month)

  async function loadShifts() {
    setLoading(true)
    setError(null)
    try {
      const url = `${API_BASE}/users/${encodeURIComponent(
        employeeNumber,
      )}/shifts/${year}/${month}`
      const res = await apiFetch(url)
      if (!res.ok) {
        const text = await res.text()
        throw new Error(text || `HTTP ${res.status}`)
      }
      const data: ShiftDto[] = await res.json()
      setShifts(data)
    } catch (e) {
      const msg = isNetworkError(e) ? NETWORK_ERROR_MESSAGE : (e instanceof Error ? e.message : String(e))
      setError(msg)
      setShifts([])
    } finally {
      setLoading(false)
    }
  }

  async function runImport() {
    setImportLoading(true)
    setImportResult(null)
    try {
      const res = await apiFetch(`${API_BASE}/import/schedules`, { method: 'POST' })
      const data = await res.json().catch(() => ({}))
      if (!res.ok) {
        const msg = Array.isArray(data.detail) ? data.detail.map((o: { msg?: string }) => o?.msg).filter(Boolean).join('; ') : (data.detail ?? data.message)
        throw new Error(msg || `HTTP ${res.status}`)
      }
      setImportResult({
        teams: data.teams_processed || [],
        warning: data.warning ?? undefined,
      })
    } catch (e) {
      const msg = isNetworkError(e) ? NETWORK_ERROR_MESSAGE : (e instanceof Error ? e.message : String(e))
      setImportResult({
        teams: [],
        warning: msg,
      })
    } finally {
      setImportLoading(false)
    }
  }

  function prevMonth() {
    if (month === 1) {
      setMonth(12)
      setYear((y) => y - 1)
    } else {
      setMonth((m) => m - 1)
    }
  }

  function nextMonth() {
    if (month === 12) {
      setMonth(1)
      setYear((y) => y + 1)
    } else {
      setMonth((m) => m + 1)
    }
  }

  async function loadOnDuty() {
    const maxDay = getDaysInMonth(year, month)
    const day = Math.min(maxDay, Math.max(1, parseInt(onDutyDayInput, 10) || 1))
    const dateStr = `${year}-${String(month).padStart(2, '0')}-${String(day).padStart(2, '0')}`
    setOnDutyLoading(true)
    setOnDutyError(null)
    setOnDutySearched(true)
    try {
      const url = `${API_BASE}/shifts/on-duty?date_q=${dateStr}&code=${encodeURIComponent(onDutyCode)}`
      const res = await apiFetch(url)
      if (!res.ok) throw new Error(await res.text() || `HTTP ${res.status}`)
      const data: OnDutyPerson[] = await res.json()
      setOnDutyList(data)
    } catch (e) {
      const msg = isNetworkError(e) ? NETWORK_ERROR_MESSAGE : (e instanceof Error ? e.message : String(e))
      setOnDutyError(msg)
      setOnDutyList([])
    } finally {
      setOnDutyLoading(false)
    }
  }

  const maxDay = getDaysInMonth(year, month)

  function originStatusLabel(origin_status: string | null | undefined, team: string | null, showTrocaBht?: boolean): string {
    if (!origin_status) {
      return team ? `ROTA – ${team}` : 'ROTA'
    }
    switch (origin_status) {
      case 'rota':
        return team ? `ROTA – ${team}` : 'ROTA'
      case 'troca_nav':
        return 'TROCA NAV'
      case 'troca_servico':
        return 'TROCA SERVIÇO'
      case 'bht':
        return showTrocaBht ? 'TROCA BHT' : 'BHT'
      case 'ts':
        return 'TROCA TS'
      case 'mudanca_funcoes':
        return 'Mudança de Funções'
      case 'outros':
        return 'Outros'
      default:
        return 'Outros'
    }
  }

  useEffect(() => {
    if (localStorage.getItem('token')) {
      loadUserPreferences()
      loadNotifications()
      loadSwapActions()
      loadMySwapRequests()
      // Carregar perfil para mostrar "Sessão: ..."
      fetch(`${API_BASE}/users/me`, { headers: getAuthHeaders() })
        .then((res) => (res.ok ? res.json() : null))
        .then((data) => {
          if (!data) return
          const emp = (data.employee_number ?? '').toString().trim()
          setCurrentUser({ id: data.id, nome: data.nome, email: data.email, employee_number: emp })
          if (emp) setEmployeeNumber(emp)
        })
        .catch(() => setCurrentUser(null))
    } else {
      setCurrentUser(null)
    }
  }, [])

  async function doLogin(e: React.FormEvent) {
    e.preventDefault()
    setLoginError(null)
    setLoginLoading(true)
    try {
      const body = new URLSearchParams({ username: loginEmail.trim(), password: loginPassword })
      const res = await fetch(`${API_BASE}/users/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
        body: body.toString(),
      })
      if (!res.ok) {
        const text = await res.text()
        setLoginError(text && text.length < 200 ? text : 'Email ou palavra-passe incorretos.')
        return
      }
      const data: { access_token: string } = await res.json()
      localStorage.setItem('token', data.access_token)
      const meRes = await fetch(`${API_BASE}/users/me`, {
        headers: { Authorization: `Bearer ${data.access_token}` },
      })
      if (meRes.ok) {
        const me = await meRes.json()
        const emp = (me.employee_number ?? '').toString().trim()
        setCurrentUser({ id: me.id, nome: me.nome, email: me.email, employee_number: emp })
        if (emp) setEmployeeNumber(emp)
      } else {
        setCurrentUser({ id: undefined, nome: loginEmail, email: loginEmail, employee_number: '' })
      }
      setLoginEmail('')
      setLoginPassword('')
      loadUserPreferences()
      loadNotifications()
      loadSwapActions()
      loadMySwapRequests()
    } catch (e) {
      setLoginError(isNetworkError(e) ? NETWORK_ERROR_MESSAGE : (e instanceof Error ? e.message : String(e)))
    } finally {
      setLoginLoading(false)
    }
  }

  function doLogout() {
    localStorage.removeItem('token')
    setCurrentUser(null)
    // manter employeeNumber (o utilizador pode querer comparar) ou pode limpar se preferires
    setSelectedShift(null)
    setDirectTargets([])
    setDirectQuery('')
    setDirectResults([])
    setSameDayTypes([])
    setWantedRows([{ date: '', shift_types: [] }])
    setSwapSubmitError(null)
    setSwapSubmitSuccess(false)
    setExistingSwapIdToCancel(null)
    setSwapActions([])
    setMySwapRequests([])
  }

  function getAuthHeaders(): HeadersInit {
    const token = localStorage.getItem('token')
    if (token) return { Authorization: `Bearer ${token}` }
    return {}
  }

  async function loadUserPreferences() {
    const token = localStorage.getItem('token')
    if (!token) return
    try {
      const res = await fetch(`${API_BASE}/users/me`, { headers: getAuthHeaders() })
      if (res.ok) {
        const data = await res.json()
        setNotificationsEnabled(data.notifications_enabled !== false)
      }
    } catch {
      // ignore
    }
  }

  async function loadNotifications() {
    const token = localStorage.getItem('token')
    if (!token) return
    setNotificationsLoading(true)
    try {
      const res = await fetch(`${API_BASE}/notifications/`, { headers: getAuthHeaders() })
      if (res.ok) {
        const data: NotificationDto[] = await res.json()
        setNotifications(data)
      }
    } catch {
      // ignore
    } finally {
      setNotificationsLoading(false)
    }
  }

  async function dismissSwapActionHistory(actionId: number) {
    const token = localStorage.getItem('token')
    if (!token) return
    setDismissHistoryId(actionId)
    try {
      const res = await fetch(`${API_BASE}/swap-requests/actions/${actionId}/dismiss`, {
        method: 'POST',
        headers: getAuthHeaders(),
      })
      if (res.ok) {
        setSwapActions((prev) => prev.filter((a) => a.id !== actionId))
      }
    } catch {
      // ignore
    } finally {
      setDismissHistoryId(null)
    }
  }

  async function loadSwapActions() {
    const token = localStorage.getItem('token')
    if (!token) return
    setSwapActionsLoading(true)
    try {
      const res = await fetch(`${API_BASE}/swap-requests/actions/me`, { headers: getAuthHeaders() })
      if (res.ok) {
        const data: SwapActionDto[] = await res.json()
        setSwapActions(data)
      }
    } catch {
      // ignore
    } finally {
      setSwapActionsLoading(false)
    }
  }

  async function loadMySwapRequests() {
    const token = localStorage.getItem('token')
    if (!token) return
    setMySwapsLoading(true)
    try {
      const res = await fetch(`${API_BASE}/swap-requests/mine`, { headers: getAuthHeaders() })
      if (res.ok) {
        const data: MySwapRequestDto[] = await res.json()
        setMySwapRequests(data)
      }
    } catch {
      // ignore
    } finally {
      setMySwapsLoading(false)
    }
  }

  const visibleNotifications = notifications.filter((n) => !n.read_at)

  async function markNotificationRead(id: number) {
    const token = localStorage.getItem('token')
    if (!token) return
    try {
      const res = await fetch(`${API_BASE}/notifications/${id}/read`, {
        method: 'PATCH',
        headers: getAuthHeaders(),
      })
      if (res.ok) {
        setNotifications((prev) =>
          prev.map((n) => (n.id === id ? { ...n, read_at: new Date().toISOString() } : n)),
        )
      }
    } catch {
      // ignore
    }
  }

  async function acceptSwapFromNotification(swapRequestId: number) {
    setAcceptSwapError(null)
    setAcceptSwapLoading(swapRequestId)
    try {
      const res = await fetch(`${API_BASE}/swap-requests/${swapRequestId}/accept`, {
        method: 'POST',
        headers: getAuthHeaders(),
      })
      if (!res.ok) {
        const text = await res.text()
        setAcceptSwapError(text && text.length < 300 ? text : 'Não foi possível aceitar a troca.')
        return
      }
      await loadNotifications()
      await loadSwapActions()
      if (employeeNumber.trim()) loadShifts()
    } catch (e) {
      setAcceptSwapError(e instanceof Error ? e.message : 'Erro de ligação.')
    } finally {
      setAcceptSwapLoading(null)
    }
  }

  async function rejectSwapFromNotification(swapRequestId: number) {
    setRejectSwapError(null)
    setRejectSwapLoading(swapRequestId)
    try {
      const res = await fetch(`${API_BASE}/swap-requests/${swapRequestId}/reject`, {
        method: 'POST',
        headers: getAuthHeaders(),
      })
      if (!res.ok) {
        const text = await res.text()
        setRejectSwapError(text && text.length < 300 ? text : 'Não foi possível recusar a troca.')
        return
      }
      await loadNotifications()
      await loadSwapActions()
    } catch (e) {
      setRejectSwapError(e instanceof Error ? e.message : 'Erro de ligação.')
    } finally {
      setRejectSwapLoading(null)
    }
  }

  async function toggleNotificationsPreference(enabled: boolean) {
    const token = localStorage.getItem('token')
    if (!token) return
    try {
      const res = await fetch(`${API_BASE}/users/me`, {
        method: 'PATCH',
        headers: { ...getAuthHeaders(), 'Content-Type': 'application/json' },
        body: JSON.stringify({ notifications_enabled: enabled }),
      })
      if (res.ok) {
        setNotificationsEnabled(enabled)
      }
    } catch {
      // ignore
    }
  }

  function toggleSameDayType(code: string) {
    setSameDayTypes((prev) =>
      prev.includes(code) ? prev.filter((c) => c !== code) : [...prev, code]
    )
  }

  function addWantedRow() {
    setWantedRows((prev) => [...prev, { date: '', shift_types: [] }])
  }

  function updateWantedRow(i: number, field: 'date' | 'shift_types', value: string | string[]) {
    setWantedRows((prev) => {
      const next = [...prev]
      next[i] = { ...next[i], [field]: value }
      return next
    })
  }

  function toggleWantedShift(rowIndex: number, code: string) {
    setWantedRows((prev) => {
      const row = prev[rowIndex]
      const types = row.shift_types.includes(code)
        ? row.shift_types.filter((c) => c !== code)
        : [...row.shift_types, code]
      const next = [...prev]
      next[rowIndex] = { ...row, shift_types: types }
      return next
    })
  }

  function removeWantedRow(i: number) {
    setWantedRows((prev) => prev.filter((_, idx) => idx !== i))
  }

  async function handleSwap400(res: Response) {
    const existingId = res.headers.get('X-Existing-Swap-Id')
    if (existingId) setExistingSwapIdToCancel(parseInt(existingId, 10))
    const data = await res.json().catch(() => ({}))
    setSwapSubmitError(typeof data.detail === 'string' ? data.detail : 'Já existe um pedido de troca em aberto para este turno.')
  }

  async function cancelSwapRequest(swapId: number) {
    try {
      const res = await fetch(`${API_BASE}/swap-requests/${swapId}`, {
        method: 'DELETE',
        headers: getAuthHeaders(),
      })
      if (res.ok) {
        setExistingSwapIdToCancel(null)
        setSwapSubmitError(null)
        setSwapSubmitSuccess(true)
        setTimeout(() => setSwapSubmitSuccess(false), 3000)
        loadMySwapRequests()
      } else {
        setSwapSubmitError(await res.text() || 'Erro ao cancelar.')
      }
    } catch (e) {
      setSwapSubmitError(e instanceof Error ? e.message : String(e))
    }
  }

  async function createSwapSameDay() {
    if (!selectedShift) return
    setSwapSubmitLoading(true)
    setSwapSubmitError(null)
    setSwapSubmitSuccess(false)
    setExistingSwapIdToCancel(null)
    try {
      const res = await fetch(`${API_BASE}/swap-requests/`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...getAuthHeaders() },
        body: JSON.stringify({
          shift_id: selectedShift.id,
          acceptable_shift_types: sameDayTypes.length ? sameDayTypes : undefined,
        }),
      })
      if (res.status === 401) {
        setSwapSubmitError('Para criar pedidos de troca é necessário iniciar sessão.')
        return
      }
      if (res.status === 400) {
        await handleSwap400(res)
        return
      }
      if (!res.ok) throw new Error(await res.text() || `HTTP ${res.status}`)
      setSwapSubmitSuccess(true)
      setSelectedShift(null)
      setSameDayTypes([])
      loadMySwapRequests()
    } catch (e) {
      setSwapSubmitError(e instanceof Error ? e.message : String(e))
    } finally {
      setSwapSubmitLoading(false)
    }
  }

  async function createSwapOtherDays() {
    if (!selectedShift) return
    const options = wantedRows.filter((r) => r.date && r.shift_types.length > 0)
    if (options.length === 0) {
      setSwapSubmitError('Indique pelo menos um dia e os turnos aceites.')
      return
    }
    setSwapSubmitLoading(true)
    setSwapSubmitError(null)
    setSwapSubmitSuccess(false)
    setExistingSwapIdToCancel(null)
    try {
      const res = await fetch(`${API_BASE}/swap-requests/`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...getAuthHeaders() },
        body: JSON.stringify({
          shift_id: selectedShift.id,
          wanted_options: options.map((r) => ({ date: r.date, shift_types: r.shift_types })),
        }),
      })
      if (res.status === 401) {
        setSwapSubmitError('Para criar pedidos de troca é necessário iniciar sessão.')
        return
      }
      if (res.status === 400) {
        await handleSwap400(res)
        return
      }
      if (!res.ok) throw new Error(await res.text() || `HTTP ${res.status}`)
      setSwapSubmitSuccess(true)
      setSelectedShift(null)
      setWantedRows([{ date: '', shift_types: [] }])
      loadNotifications()
      loadMySwapRequests()
    } catch (e) {
      setSwapSubmitError(e instanceof Error ? e.message : String(e))
    } finally {
      setSwapSubmitLoading(false)
    }
  }

  async function searchDirectUsers(query: string) {
    setDirectQuery(query)
    setDirectResults([])
    if (!query || query.trim().length < 2) {
      return
    }
    try {
      const res = await apiFetch(`${API_BASE}/users/search?q=${encodeURIComponent(query.trim())}`, {
        headers: getAuthHeaders(),
      })
      if (!res.ok) {
        return
      }
      const data: UserSearchResult[] = await res.json()
      setDirectResults(data.filter((u) => !directTargets.some((t) => t.id === u.id)))
    } catch {
      // silêncio: autocomplete é best-effort
    }
  }

  function addDirectTarget(user: UserSearchResult) {
    if (user.id === currentUser?.id) return
    if (directTargets.some((t) => t.id === user.id)) return
    setDirectTargets((prev) => [...prev, user])
    setDirectResults((prev) => prev.filter((u) => u.id !== user.id))
    setDirectQuery('')
  }

  function removeDirectTarget(userId: number) {
    setDirectTargets((prev) => prev.filter((u) => u.id !== userId))
  }

  async function createDirectSwap() {
    if (!selectedShift) return
    if (directTargets.length === 0) {
      setSwapSubmitError('Escolha pelo menos um colega para a troca direta.')
      return
    }
    setSwapSubmitLoading(true)
    setSwapSubmitError(null)
    setSwapSubmitSuccess(false)
    setExistingSwapIdToCancel(null)
    try {
      const res = await fetch(`${API_BASE}/swap-requests/`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...getAuthHeaders() },
        body: JSON.stringify({
          shift_id: selectedShift.id,
          direct_target_ids: directTargets.map((u) => u.id),
        }),
      })
      if (res.status === 401) {
        setSwapSubmitError('Para criar pedidos de troca é necessário iniciar sessão.')
        return
      }
      if (res.status === 400) {
        await handleSwap400(res)
        return
      }
      if (!res.ok) throw new Error(await res.text() || `HTTP ${res.status}`)
      setSwapSubmitSuccess(true)
      setSelectedShift(null)
      setDirectTargets([])
      setDirectQuery('')
      loadMySwapRequests()
    } catch (e) {
      setSwapSubmitError(e instanceof Error ? e.message : String(e))
    } finally {
      setSwapSubmitLoading(false)
    }
  }

  function mySwapKindLabel(kind: MySwapRequestDto['kind']): string {
    switch (kind) {
      case 'direct':
        return 'Troca direta'
      case 'same_day':
        return 'Mesmo dia'
      case 'other_days':
        return 'Outros dias'
      default:
        return kind
    }
  }

  return (
    <div className="app-scale">
      <header className="scale-header">
        <div className="login-bar">
          {currentUser ? (
            <div className="login-bar-session">
              <span>Sessão: {currentUser.nome || currentUser.email}</span>
              <button type="button" className="btn-logout" onClick={doLogout}>
                Terminar sessão
              </button>
            </div>
          ) : (
            <form className="login-form" onSubmit={doLogin}>
              <label className="control-group">
                <span>Email</span>
                <input
                  type="email"
                  value={loginEmail}
                  onChange={(e) => setLoginEmail(e.target.value)}
                  placeholder="ex: a405856@demo.local"
                  required
                  autoComplete="username"
                />
              </label>
              <label className="control-group">
                <span>Palavra-passe</span>
                <input
                  type="password"
                  value={loginPassword}
                  onChange={(e) => setLoginPassword(e.target.value)}
                  placeholder="ex: test"
                  required
                  autoComplete="current-password"
                />
              </label>
              <button type="submit" className="btn-load btn-load--light" disabled={loginLoading}>
                {loginLoading ? 'A iniciar...' : 'Iniciar sessão'}
              </button>
              {loginError && <p className="scale-error" style={{ marginTop: '0.5rem', marginBottom: 0 }}>{loginError}</p>}
            </form>
          )}
        </div>
        <h1>Escala pessoal</h1>
        <p className="scale-subtitle">
          Número de funcionário, mês e ano. Use as setas para mudar o mês.
        </p>

        <div className="scale-controls">
          <label className="control-group">
            <span>Nº funcionário</span>
            <input
              type="text"
              value={employeeNumber}
              onChange={(e) => setEmployeeNumber(e.target.value)}
              placeholder="ex: 405541"
            />
          </label>
          <div className="month-nav">
            <button type="button" onClick={prevMonth} aria-label="Mês anterior">
              ‹
            </button>
            <span className="month-label">
              {MONTH_NAMES[month - 1]} {year}
            </span>
            <button type="button" onClick={nextMonth} aria-label="Mês seguinte">
              ›
            </button>
          </div>
          <button
            type="button"
            className="btn-load btn-load--light"
            onClick={loadShifts}
            disabled={loading}
          >
            {loading ? 'A carregar...' : 'Carregar escala'}
          </button>
          {SHOW_IMPORT_BUTTON && (
            <button
              type="button"
              className="btn-load btn-load--light"
              onClick={runImport}
              disabled={importLoading}
              title="Lê os PDF das pastas 'atual' e 'seguinte' e importa para a base de dados. Depois use 'Carregar escala' para o mês desejado."
            >
              {importLoading ? 'A importar...' : 'Importar escalas'}
            </button>
          )}
        </div>
        <p className="scale-subtitle" style={{ marginTop: '0.5rem', padding: '0.35rem 0.5rem', background: 'var(--code-bg)', borderRadius: 6, fontSize: '0.8rem' }}>
          <strong>API:</strong> {API_BASE}
        </p>
      </header>

      {importResult && (
        <div className={importResult.warning && importResult.teams.length < 5 ? 'scale-error' : 'scale-success-msg'}>
          {importResult.teams.length > 0 ? (
            <p style={{ margin: 0 }}>
              Importadas {importResult.teams.length} equipas: {importResult.teams.join(', ')}.
            </p>
          ) : (
            <p style={{ margin: 0 }}>
              Nenhum PDF foi processado. Verifique as pastas &quot;atual&quot; e &quot;seguinte&quot; e o formato dos ficheiros (ex.: A_2026_4.pdf).
            </p>
          )}
          {importResult.warning && <p style={{ margin: '0.5rem 0 0' }}>{importResult.warning}</p>}
          {importResult.teams.length > 0 && (
            <p style={{ margin: '0.5rem 0 0', fontSize: '0.9rem' }}>
              Pode agora escolher o mês (ex.: Abril) e carregar em &quot;Carregar escala&quot;.
            </p>
          )}
        </div>
      )}

      {error && (
        <div className="scale-error">
          Erro ao carregar: {error}
        </div>
      )}

      {!loading && !error && shifts.length === 0 && (
        <p className="scale-empty">Sem turnos para os parâmetros indicados.</p>
      )}

      {shifts.length > 0 && (
        <div className="calendar-wrap">
          <div className="calendar-weekdays">
            {['Dom', 'Seg', 'Ter', 'Qua', 'Qui', 'Sex', 'Sáb'].map((d) => (
              <span key={d} className="weekday">{d}</span>
            ))}
          </div>
          <div className="calendar-grid" style={{ gridTemplateColumns: 'repeat(7, 1fr)' }}>
            {Array.from({ length: firstWeekday }, (_, i) => (
              <div key={`empty-${i}`} className="calendar-cell calendar-cell--empty" />
            ))}
            {Array.from({ length: daysInMonth }, (_, i) => {
              const day = i + 1
              const dateStr = `${year}-${String(month).padStart(2, '0')}-${String(day).padStart(2, '0')}`
              const shift = shiftsByDate[dateStr]
              const bg = shift ? backgroundColor(shift.color_bucket) : undefined
              const inconsistent = shift?.inconsistency_flag
              const msg = shift?.inconsistency_message
              const today = new Date()
              const isPast =
                year < today.getFullYear() ||
                (year === today.getFullYear() && month < today.getMonth() + 1) ||
                (year === today.getFullYear() && month === today.getMonth() + 1 && day < today.getDate())
              const isClickable = shift && !isPast
              // Célula dividida só para troca de serviço entre colegas: metade superior cinzenta clara, metade inferior cinzenta escura (bandas de largura total).
              const isOriginTroca =
                shift?.origin_status === 'troca_servico' && shift?.color_bucket === 'gray_dark'
              const bottomHalfDark = shift?.color_bucket === 'gray_dark'
              return (
                <div
                  key={day}
                  role={isClickable ? 'button' : undefined}
                  tabIndex={isClickable ? 0 : undefined}
                  className={`calendar-cell ${isClickable ? 'calendar-cell--clickable' : ''} ${isPast ? 'calendar-cell--past' : ''} ${selectedShift?.id === shift?.id ? 'calendar-cell--selected' : ''} ${inconsistent ? 'calendar-cell--inconsistent' : ''} ${isOriginTroca ? 'calendar-cell--split' : ''} ${!isOriginTroca && shift?.color_bucket === 'gray_dark' ? 'calendar-cell--dark-bg' : ''} ${!isOriginTroca && shift && (shift.color_bucket === 'gray_light' || (shift.color_bucket !== 'gray_dark' && shift.color_bucket !== 'gray_light')) ? 'calendar-cell--light-bg' : ''}`}
                  style={!isOriginTroca && bg ? { backgroundColor: bg } : undefined}
                  title={inconsistent ? msg || 'Inconsistência' : isPast ? 'Dia passado' : isClickable ? 'Clique para opções de troca' : undefined}
                  onClick={isClickable ? () => setSelectedShift(shift) : undefined}
                  onKeyDown={isClickable ? (e) => e.key === 'Enter' && setSelectedShift(shift) : undefined}
                >
                  {isOriginTroca && shift ? (
                    <>
                      <div className="cell-half cell-half--top">
                        <span className="cell-day">{day}</span>
                      </div>
                      <div
                        className={`cell-half cell-half--bottom ${bottomHalfDark ? 'cell-half--dark' : 'cell-half--light'}`}
                        style={{ backgroundColor: bg }}
                      >
                        <span className="cell-code">{shift.codigo}</span>
                        {inconsistent && (
                          <span className="cell-flag" title={msg || ''} aria-label="Inconsistência">
                            ⚠
                          </span>
                        )}
                      </div>
                    </>
                  ) : (
                    <>
                      <span className="cell-day">{day}</span>
                      {shift ? (
                        <>
                          <span className="cell-code">{shift.codigo}</span>
                          {inconsistent && (
                            <span className="cell-flag" title={msg || ''} aria-label="Inconsistência">
                              ⚠
                            </span>
                          )}
                        </>
                      ) : (
                        <span className="cell-code cell-code--empty">–</span>
                      )}
                    </>
                  )}
                </div>
              )
            })}
          </div>
          <div className="calendar-legend">
            <span><em>Fundo claro</em> Rotação normal</span>
            <span><em>Cinzento claro</em> Troca NAV</span>
            <span><em>Cinzento escuro</em> Troca serviço</span>
            <span><em>Vermelho</em> BHT</span>
            <span><em>Amarelo</em> TS</span>
            <span><em>Rosa</em> Mudança de Funções</span>
            <span><em>Verde</em> Outros</span>
            <span className="legend-flag">⚠ Turno trocado, escala ainda não atualizada</span>
            <span>· Clique num turno para ver opções de troca</span>
          </div>
        </div>
      )}

      {selectedShift && (
        <section className="swap-panel">
          <div className="swap-panel-header">
            <h2>Trocar turno {selectedShift.codigo} do dia {selectedShift.data}</h2>
            <button type="button" className="btn-close-panel" onClick={() => { setSelectedShift(null); setSwapSubmitError(null); setSwapSubmitSuccess(false); setExistingSwapIdToCancel(null); }} aria-label="Fechar">
              ✕
            </button>
          </div>
          <p className="swap-panel-intro">Escolha como quer propor a troca:</p>

          <div className="swap-option-card">
            <h3>Troca no mesmo dia</h3>
            {(selectedShift.codigo === 'DC' || selectedShift.codigo === 'DS') && (
              <p className="swap-dc-ds-note">
                Está de folga ({selectedShift.codigo}) neste dia. Pode indicar que fica disponível para trabalhar, aceitando em troca um dos turnos abaixo.
              </p>
            )}
            <p>Aceito em troca qualquer um destes turnos no mesmo dia:</p>
            <div className="swap-checkbox-group">
              {SHIFT_CODES.filter((c) => c !== selectedShift.codigo).map((code) => (
                <label key={code} className="swap-checkbox">
                  <input
                    type="checkbox"
                    checked={sameDayTypes.includes(code)}
                    onChange={() => toggleSameDayType(code)}
                  />
                  <span>{code}</span>
                </label>
              ))}
            </div>
            <p className="swap-hint">Se não escolher nenhum, aceita qualquer turno nesse dia.</p>
            <button type="button" className="btn-load btn-load--light" onClick={createSwapSameDay} disabled={swapSubmitLoading}>
              {swapSubmitLoading ? 'A enviar...' : 'Criar pedido de troca (mesmo dia)'}
            </button>
          </div>

          <div className="swap-option-card">
            <h3>Troca por outros dias / turnos</h3>
            <p>Quero receber em troca (pode indicar vários dias e turnos aceites):</p>
            {wantedRows.map((row, i) => (
              <div key={i} className="wanted-row">
                <input
                  type="date"
                  value={row.date}
                  onChange={(e) => updateWantedRow(i, 'date', e.target.value)}
                  className="wanted-date"
                />
                <div className="swap-checkbox-group">
                  {SHIFT_CODES.map((code) => (
                    <label key={code} className="swap-checkbox">
                      <input
                        type="checkbox"
                        checked={row.shift_types.includes(code)}
                        onChange={() => toggleWantedShift(i, code)}
                      />
                      <span>{code}</span>
                    </label>
                  ))}
                </div>
                {wantedRows.length > 1 && (
                  <button type="button" className="btn-remove-row" onClick={() => removeWantedRow(i)}>Remover</button>
                )}
              </div>
            ))}
            <button type="button" className="btn-secondary" onClick={addWantedRow}>+ Adicionar outro dia</button>
            <button type="button" className="btn-load btn-load--light" onClick={createSwapOtherDays} disabled={swapSubmitLoading} style={{ marginTop: '0.75rem' }}>
              {swapSubmitLoading ? 'A enviar...' : 'Criar pedido de troca (outros dias)'}
            </button>
          </div>

          <div className="swap-option-card">
            <h3>Troca direta</h3>
            <p>Quer trocar este turno diretamente com colegas específicos.</p>
            <label className="control-group">
              <span>Nome ou número</span>
              <input
                type="text"
                value={directQuery}
                onChange={(e) => searchDirectUsers(e.target.value)}
                placeholder="Comece a escrever o nome (ex.: João)..."
              />
            </label>
            {directResults.filter((u) => u.id !== currentUser?.id).length > 0 && (
              <ul className="direct-search-results">
                {directResults
                  .filter((u) => u.id !== currentUser?.id)
                  .map((u) => (
                    <li key={u.id}>
                      <button type="button" onClick={() => addDirectTarget(u)}>
                        {u.nome} ({u.employee_number})
                      </button>
                    </li>
                  ))}
              </ul>
            )}
            {directTargets.length > 0 && (
              <div className="direct-targets">
                <p>Pedido dirigido a:</p>
                <ul>
                  {directTargets.map((u) => (
                    <li key={u.id}>
                      {u.nome} ({u.employee_number}){' '}
                      <button type="button" className="btn-remove-row" onClick={() => removeDirectTarget(u.id)}>
                        remover
                      </button>
                    </li>
                  ))}
                </ul>
              </div>
            )}
            <button
              type="button"
              className="btn-load btn-load--light"
              onClick={createDirectSwap}
              disabled={swapSubmitLoading}
              style={{ marginTop: '0.75rem' }}
            >
              {swapSubmitLoading ? 'A enviar...' : 'Criar pedido de troca direta'}
            </button>
          </div>

          {swapSubmitError && <div className="scale-error">{swapSubmitError}</div>}
          {existingSwapIdToCancel != null && (
            <p style={{ marginTop: '0.5rem' }}>
              <button type="button" className="btn-load btn-load--light" onClick={() => cancelSwapRequest(existingSwapIdToCancel!)}>
                Cancelar pedido em aberto
              </button>
            </p>
          )}
          {swapSubmitSuccess && <p className="swap-success">Pedido de troca criado.</p>}
        </section>
      )}

      {localStorage.getItem('token') && (
        <section className="my-swaps-section">
          <h2>Os meus pedidos de troca</h2>
          <p className="scale-subtitle">
            Apenas pedidos <strong>em aberto</strong>. Quando forem aceites ou recusados, deixam de aparecer aqui —
            consulte o histórico abaixo.
          </p>
          <button
            type="button"
            className="btn-load btn-load--light"
            onClick={loadMySwapRequests}
            disabled={mySwapsLoading}
            style={{ marginBottom: '1rem' }}
          >
            {mySwapsLoading ? 'A carregar...' : 'Atualizar lista'}
          </button>
          {!mySwapsLoading && mySwapRequests.length === 0 && (
            <p className="scale-empty">Não tem pedidos de troca em aberto.</p>
          )}
          {mySwapRequests.length > 0 && (
            <>
              <h3 className="my-swaps-subtitle">Em aberto</h3>
              <ul className="my-swaps-list">
                {mySwapRequests.map((r) => (
                    <li key={r.id} className="my-swap-item">
                      <div className="my-swap-item-body">
                        <strong>#{r.id}</strong> · {mySwapKindLabel(r.kind)} ·{' '}
                        <strong>{r.offered_shift_code}</strong> ·{' '}
                        {formatSwapActionOfferedDatePt(r.offered_shift_date)}
                        {r.kind === 'direct' && r.direct_targets && r.direct_targets.length > 0 && (
                          <div className="my-swap-detail">
                            Para:{' '}
                            {r.direct_targets.map((t) => `${t.nome} (${t.employee_number})`).join(', ')}
                          </div>
                        )}
                        {r.kind === 'same_day' && (
                          <div className="my-swap-detail">
                            Aceita trocar por:{' '}
                            {r.acceptable_shift_types && r.acceptable_shift_types.length > 0
                              ? r.acceptable_shift_types.join(' ou ')
                              : 'qualquer turno no mesmo dia'}
                          </div>
                        )}
                        {r.kind === 'other_days' && r.wanted_options && r.wanted_options.length > 0 && (
                          <div className="my-swap-detail">
                            {r.wanted_options.map((o) => (
                              <div key={o.date}>
                                {o.date}: {o.shift_types.join(' ou ')}
                              </div>
                            ))}
                          </div>
                        )}
                      </div>
                      <button
                        type="button"
                        className="btn-secondary"
                        onClick={() => cancelSwapRequest(r.id)}
                      >
                        Cancelar pedido
                      </button>
                    </li>
                  ))}
              </ul>
            </>
          )}
        </section>
      )}

      {localStorage.getItem('token') && (
        <section className="my-swaps-section my-requester-history-section">
          <h2>Histórico dos meus pedidos (aceites e recusas)</h2>
          <p className="scale-subtitle">
            Respostas aos pedidos que criou. Pode apagar linhas individualmente (só desaparecem para si).
          </p>
          <button
            type="button"
            className="btn-load btn-load--light"
            onClick={loadSwapActions}
            disabled={swapActionsLoading}
            style={{ marginBottom: '1rem' }}
          >
            {swapActionsLoading ? 'A carregar...' : 'Atualizar histórico'}
          </button>
          {!swapActionsLoading &&
            swapActions.filter((a) => a.requester_id === currentUser?.id).length === 0 && (
              <p className="scale-empty">Ainda não há aceitações nem recusas aos seus pedidos.</p>
            )}
          {swapActions.filter((a) => a.requester_id === currentUser?.id).length > 0 && (
            <ul className="notifications-list">
              {swapActions
                .filter((a) => a.requester_id === currentUser?.id)
                .map((a) => {
                  const verb = a.action_type === 'REJECTED' ? 'Recusada' : 'Aceite'
                  const offeredDate = formatSwapActionOfferedDatePt(a.offered_shift_date)
                  return (
                    <li key={a.id} className="notifications-item notifications-item--read">
                      <div className="notifications-item-body">
                        <span>
                          {verb} troca {a.offered_shift_code} {offeredDate} por{' '}
                          <strong>{a.actor_name || 'um colega'}</strong>.
                        </span>
                      </div>
                      <div className="notifications-item-actions">
                        <button
                          type="button"
                          className="btn-secondary"
                          onClick={() => dismissSwapActionHistory(a.id)}
                          disabled={dismissHistoryId === a.id}
                        >
                          {dismissHistoryId === a.id ? 'A apagar...' : 'Apagar'}
                        </button>
                      </div>
                    </li>
                  )
                })}
            </ul>
          )}
        </section>
      )}

      {localStorage.getItem('token') && (
        <section className="notifications-section">
          <h2>Notificações</h2>
          <p className="scale-subtitle">
            Pedidos de troca que pode satisfazer (ex.: um colega quer trocar o turno dele por um turno que tem nesse dia).
          </p>
          <label className="notifications-toggle">
            <input
              type="checkbox"
              checked={notificationsEnabled}
              onChange={(e) => toggleNotificationsPreference(e.target.checked)}
            />
            <span>Receber notificações quando um colega criar um pedido que eu possa satisfazer</span>
          </label>
          <button
            type="button"
            className="btn-load btn-load--light"
            onClick={loadNotifications}
            disabled={notificationsLoading}
            style={{ marginBottom: '1rem' }}
          >
            {notificationsLoading ? 'A carregar...' : 'Atualizar notificações'}
          </button>
          {visibleNotifications.length === 0 && !notificationsLoading && (
            <p className="scale-empty">Nenhuma notificação.</p>
          )}
          {acceptSwapError && (
            <div className="scale-error" style={{ marginBottom: '0.5rem' }}>{acceptSwapError}</div>
          )}
          {rejectSwapError && (
            <div className="scale-error" style={{ marginBottom: '0.5rem' }}>{rejectSwapError}</div>
          )}
          {visibleNotifications.length > 0 && (
            <ul className="notifications-list">
              {visibleNotifications.map((n) => (
                <li
                  key={n.id}
                  className={n.read_at ? 'notifications-item notifications-item--read' : 'notifications-item'}
                >
                  <div className="notifications-item-body">
                    {n.notification_kind === 'request_fulfilled' && (
                      <span>
                        O pedido de troca
                        {n.offered_shift_code && n.offered_shift_date && (
                          <> ({n.offered_shift_code} do dia {n.offered_shift_date})</>
                        )}{' '}
                        foi satisfeito por outro colega.
                      </span>
                    )}
                    {n.notification_kind === 'request_rejected' && (
                      <span>
                        O seu pedido de troca
                        {n.offered_shift_code && n.offered_shift_date && (
                          <> ({n.offered_shift_code} do dia {n.offered_shift_date})</>
                        )}{' '}
                        foi recusado por {n.rejected_by_name ? n.rejected_by_name : 'um colega'}.
                      </span>
                    )}
                    {(!n.notification_kind || n.notification_kind === 'can_accept') && (
                      <>
                        {n.requester_name && n.offered_shift_code ? (
                          <span>
                            <strong>{n.requester_name}</strong> quer trocar o turno{' '}
                            <strong>{n.offered_shift_code}</strong>
                            {n.offered_shift_date && ` do dia ${n.offered_shift_date}`}
                            {n.accepted_shift_types && n.accepted_shift_types.length > 0 && (
                              <> por um {n.accepted_shift_types.join(' ou ')}.</>
                            )}
                          </span>
                        ) : (
                          <span>Pedido de troca #{n.swap_request_id} que pode satisfazer.</span>
                        )}
                      </>
                    )}
                  </div>
                  <div className="notifications-item-actions">
                    {(!n.notification_kind || n.notification_kind === 'can_accept') && (
                      <>
                        <button
                          type="button"
                          className="btn-load btn-load--light"
                          onClick={() => acceptSwapFromNotification(n.swap_request_id)}
                          disabled={acceptSwapLoading === n.swap_request_id}
                        >
                          {acceptSwapLoading === n.swap_request_id ? 'A aceitar...' : 'Aceitar troca'}
                        </button>
                        <button
                          type="button"
                          className="btn-secondary"
                          onClick={() => rejectSwapFromNotification(n.swap_request_id)}
                          disabled={rejectSwapLoading === n.swap_request_id}
                        >
                          {rejectSwapLoading === n.swap_request_id ? 'A recusar...' : 'Recusar'}
                        </button>
                      </>
                    )}
                    <button
                      type="button"
                      className="btn-secondary"
                      onClick={() => markNotificationRead(n.id)}
                    >
                      Apagar
                    </button>
                  </div>
                </li>
              ))}
            </ul>
          )}

          <div style={{ marginTop: '1rem' }}>
            {swapActionsLoading && <p className="scale-subtitle">A carregar histórico...</p>}
            {!swapActionsLoading &&
              swapActions.filter((a) => a.actor_id === currentUser?.id).length === 0 && (
                <p className="scale-empty" style={{ marginTop: '0.5rem' }}>
                  Sem histórico como destinatário (aceitar/recusar pedidos de outros).
                </p>
              )}
            {!swapActionsLoading && swapActions.filter((a) => a.actor_id === currentUser?.id).length > 0 && (
              <>
                <h3 style={{ marginTop: '0.5rem' }}>Histórico como destinatário</h3>
                <p className="scale-subtitle" style={{ marginBottom: '0.75rem' }}>
                  Pedidos em que aceitou ou recusou. Pode apagar linhas individualmente.
                </p>
                <ul className="notifications-list">
                  {swapActions
                    .filter((a) => a.actor_id === currentUser?.id)
                    .map((a) => {
                      const verb = a.action_type === 'REJECTED' ? 'Recusada' : 'Aceite'
                      const offeredDate = formatSwapActionOfferedDatePt(a.offered_shift_date)
                      return (
                        <li key={a.id} className="notifications-item notifications-item--read">
                          <div className="notifications-item-body">
                            <span>
                              {verb} troca {a.offered_shift_code} {offeredDate} a pedido do{' '}
                              <strong>{a.requester_name || 'um colega'}</strong>.
                            </span>
                          </div>
                          <div className="notifications-item-actions">
                            <button
                              type="button"
                              className="btn-secondary"
                              onClick={() => dismissSwapActionHistory(a.id)}
                              disabled={dismissHistoryId === a.id}
                            >
                              {dismissHistoryId === a.id ? 'A apagar...' : 'Apagar'}
                            </button>
                          </div>
                        </li>
                      )
                    })}
                </ul>
              </>
            )}
          </div>
        </section>
      )}

      <section className="on-duty-section">
        <h2>Quem está de serviço</h2>
        <p className="scale-subtitle">
          Escolha o dia e o turno para ver quem está de serviço nesse dia (todas as equipas).
        </p>
        <div className="on-duty-controls">
          <label className="control-group">
            <span>Dia</span>
            <input
              type="number"
              min={1}
              max={maxDay}
              value={onDutyDayInput}
              onChange={(e) => setOnDutyDayInput(e.target.value)}
              placeholder="Dia"
            />
          </label>
          <span className="on-duty-context">{MONTH_NAMES[month - 1]}</span>
          <label className="control-group">
            <span>Turno</span>
            <select
              value={onDutyCode}
              onChange={(e) => setOnDutyCode(e.target.value)}
            >
              {SHIFT_CODES.map((c) => (
                <option key={c} value={c}>{c}</option>
              ))}
            </select>
          </label>
          <button
            type="button"
            className="btn-load btn-load--light"
            onClick={loadOnDuty}
            disabled={onDutyLoading}
          >
            {onDutyLoading ? 'A carregar...' : 'Ver quem está'}
          </button>
        </div>
        {onDutyError && (
          <div className="scale-error">Erro: {onDutyError}</div>
        )}
        {onDutyList.length > 0 && (
          <ul className="on-duty-list">
            {onDutyList.map((p) => (
              <li key={p.employee_number}>
                <strong>{p.nome}</strong>
                <span> {p.employee_number}</span>
                {p.team && <span> · {p.team}</span>}
                <span> · {originStatusLabel(p.origin_status, p.team, p.show_troca_bht)}</span>
              </li>
            ))}
          </ul>
        )}
        {onDutySearched && !onDutyLoading && !onDutyError && onDutyList.length === 0 && (
          <p className="scale-empty">Nenhuma pessoa encontrada para este dia e turno.</p>
        )}
      </section>
    </div>
  )
}

export default App
