import { useState, useMemo, useEffect, useRef } from 'react'
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
  show_troca_bht?: boolean
  show_troca_ts?: boolean
  /** Colega com quem foi feita a troca aceite (histórico), p.ex. troca serviço */
  swap_partner_name?: string | null
  swap_partner_employee_number?: string | null
}

type OnDutyPerson = {
  employee_number: string
  nome: string
  team: string | null
  origin_status?: string | null
  show_troca_bht?: boolean
  show_troca_ts?: boolean
}

type UserSearchResult = {
  id: number
  nome: string
  employee_number: string
  team_id?: number | null
}

type WantedOptionNotif = {
  date: string
  shift_types: string[]
}

type SwapPackageLegDto = {
  requester_code: string
  requester_date: string
  accepter_code: string
  accepter_date: string
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
  wanted_options?: WantedOptionNotif[] | null
  accepter_shift_date?: string | null
  accepter_shift_code?: string | null
  /** Pacote: várias pernas (mesmo aceitar/recusar) */
  accepter_package_legs?: { date: string; code: string }[] | null
  requester_package_legs?: { date: string; code: string }[] | null
  rejected_by_name?: string | null
  /** Resumo após aceitar troca (notification_kind = swap_accepted_summary) */
  body_text?: string | null
}

type SwapActionDto = {
  id: number
  swap_request_id: number
  action_type: string // ACCEPTED | REJECTED
  actor_id: number
  requester_id: number
  offered_shift_code: string
  offered_shift_date: string // YYYY-MM-DD
  /** Código do turno cedido pelo destinatário (ex. DC), se disponível. */
  accepter_shift_code?: string | null
  requester_name: string
  actor_name: string
  created_at: string
  package_legs?: SwapPackageLegDto[] | null
  /** Pedido de troca direta (só destinatários indicados) */
  direct_swap?: boolean
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

/** Códigos sugeridos na edição manual (inclui casos extra dos PDF). */
const SUGGESTED_SHIFT_CODES = [...SHIFT_CODES, 'IB', 'mE', 'AF', 'TR', 'BHT']

const MANUAL_COLOR_OPTIONS: { value: string; label: string }[] = [
  { value: '', label: 'Automático (folga = escuro; resto = claro)' },
  { value: 'gray_light', label: 'Cinzento claro' },
  { value: 'gray_dark', label: 'Cinzento escuro' },
  { value: 'red', label: 'Vermelho (BHT)' },
  { value: 'yellow', label: 'Amarelo (TS / suplementar)' },
  { value: 'pink', label: 'Rosa (mudança funções / extra)' },
  { value: 'lime', label: 'Verde lima (férias / ausência)' },
]

const MANUAL_ORIGIN_OPTIONS: { value: string; label: string }[] = [
  { value: '', label: 'Automático (rota)' },
  { value: 'rota', label: 'Rota' },
  { value: 'troca_nav', label: 'Troca NAV' },
  { value: 'troca_servico', label: 'Troca serviço' },
  { value: 'bht', label: 'BHT' },
  { value: 'ts', label: 'TS' },
  { value: 'mudanca_funcoes', label: 'Mudança de funções' },
  { value: 'outros', label: 'Outros' },
]

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

/** Backend em produção (Render) quando `VITE_API_URL` não está no build — evita POST para `*.vercel.app:8000` (405). */
const DEFAULT_PROD_API = 'https://atc-shift-swap-backend.onrender.com'

/**
 * Valor de VITE_API_URL no painel deve ser só o URL (ex.: https://api.onrender.com).
 * Se alguém colar "VITE_API_URL = https://..." no campo Valor, o fetch torna-se relativo ao Vercel → 405.
 */
function parseApiUrlFromEnv(raw: string | undefined): string | undefined {
  if (raw == null) return undefined
  let s = String(raw).trim()
  if (!s) return undefined
  const start = s.search(/https?:/i)
  if (start >= 0) s = s.slice(start)
  s = s.replace(/^https:\/(?!\/)/i, 'https://').replace(/^http:\/(?!\/)/i, 'http://')
  const sp = s.search(/\s/)
  if (sp >= 0) s = s.slice(0, sp)
  s = s.replace(/\/$/, '')
  if (!/^https?:\/\//i.test(s)) return undefined
  return s
}

function resolveApiBase(): string {
  const fromEnv = parseApiUrlFromEnv(import.meta.env.VITE_API_URL)
  if (fromEnv) return fromEnv
  if (typeof window === 'undefined') return 'http://127.0.0.1:8000'
  const { protocol, hostname } = window.location
  const isLocalDevHost =
    hostname === 'localhost' ||
    hostname === '127.0.0.1' ||
    /^192\.168\.\d{1,3}\.\d{1,3}$/.test(hostname) ||
    /^10\.\d{1,3}\.\d{1,3}\.\d{1,3}$/.test(hostname)
  if (isLocalDevHost) return `${protocol}//${hostname}:8000`
  // Hospedagem estática: nunca usar :8000 no mesmo host (Vercel/Netlify não é a API → 405 no POST).
  // Não depender só de import.meta.env.PROD — em alguns CI pode falhar e cair no :8000 errado.
  if (
    hostname.endsWith('.vercel.app') ||
    hostname.endsWith('.netlify.app') ||
    import.meta.env.PROD
  ) {
    return DEFAULT_PROD_API
  }
  return `${protocol}//${hostname}:8000`
}

const API_BASE = resolveApiBase()

// Só mostrar "Importar escalas" em local: em produção (Render) não há PDFs no servidor
const SHOW_IMPORT_BUTTON = API_BASE.includes('localhost') || API_BASE.includes('127.0.0.1')

/** Deve coincidir com `CLEAR_SCHEDULES_CONFIRM_PHRASE` no backend (`routers/importer.py`). */
const CLEAR_SCHEDULES_CONFIRM = 'APAGAR_TODAS_AS_ESCALAS'

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

/** Primeiros 10 chars YYYY-MM-DD (ignora sufixos inválidos no payload). */
function extractYmd(val: string | null | undefined): string | null {
  if (!val) return null
  const m = String(val).trim().match(/^(\d{4}-\d{2}-\d{2})/)
  return m ? m[1] : null
}

function formatSwapActionOfferedDatePt(isoDate: string | null | undefined): string {
  const ymd = extractYmd(isoDate)
  if (!ymd) return ''
  const day = Number(ymd.slice(8, 10))
  const monthIdx = Number(ymd.slice(5, 7)) - 1
  const monthName = MONTH_NAMES[monthIdx]?.toLowerCase() ?? ''
  if (!day || !monthName) return ymd
  return `dia ${day} ${monthName}`
}

/** Sufixo « por DC» (ou vários códigos) na linha de resumo — turno(s) do(s) destinatário(s). */
function directSwapTheirShiftsSuffix(
  targets:
    | Array<{ their_shift_code?: string | null; nome?: string; employee_number?: string }>
    | null
    | undefined,
): string {
  if (!targets?.length) return ''
  const codes = [
    ...new Set(
      targets
        .map((t) => String(t.their_shift_code ?? '').trim())
        .filter(Boolean),
    ),
  ]
  if (!codes.length) return ''
  return ` por ${codes.join(', ')}`
}

/** Data para notificações (capitalização do mês). */
function formatNotifCalendarDate(isoDate: string | null | undefined): string {
  if (!isoDate) return ''
  const day = Number(isoDate.slice(8, 10))
  const monthIdx = Number(isoDate.slice(5, 7)) - 1
  const monthName = MONTH_NAMES[monthIdx] ?? isoDate
  if (!day) return isoDate
  return `${day} ${monthName}`
}

function swapActionPackageLines(legs: SwapPackageLegDto[]) {
  return legs.map((leg, i) => (
    <span key={`${leg.requester_date}-${leg.accepter_date}-${i}`} style={{ display: 'block' }}>
      Troca <strong>{leg.requester_code}</strong> no dia {formatNotifCalendarDate(leg.requester_date)} pelo seu{' '}
      <strong>{leg.accepter_code}</strong> ({formatNotifCalendarDate(leg.accepter_date)}).
    </span>
  ))
}

function App() {
  const [employeeNumber, setEmployeeNumber] = useState('405541')
  /** Texto no campo (pode ser só n.º ou «nome (n.º)» após escolha na lista). */
  const [employeeInput, setEmployeeInput] = useState('405541')
  const [employeeScaleResults, setEmployeeScaleResults] = useState<UserSearchResult[]>([])
  const [year, setYear] = useState(2026)
  const [month, setMonth] = useState(3)
  const [shifts, setShifts] = useState<ShiftDto[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const [onDutyYear, setOnDutyYear] = useState(2026)
  const [onDutyMonth, setOnDutyMonth] = useState(3)
  const [onDutyDayInput, setOnDutyDayInput] = useState('5')
  const [onDutyCode, setOnDutyCode] = useState('M')
  const [onDutyList, setOnDutyList] = useState<OnDutyPerson[]>([])
  const [onDutyLoading, setOnDutyLoading] = useState(false)
  const [onDutyError, setOnDutyError] = useState<string | null>(null)
  const [onDutySearched, setOnDutySearched] = useState(false)

  const [selectedShift, setSelectedShift] = useState<ShiftDto | null>(null)
  const [sameDayTypes, setSameDayTypes] = useState<string[]>([])
  /** Troca outros dias: no dia do turno proposto, que turnos precisa receber dele (ex. DC, DS). */
  const [otherDaysReceiveOnOfferDate, setOtherDaysReceiveOnOfferDate] = useState<string[]>([])
  /** Noutros dias: por linha — data + turnos que pode fazer / aceita receber da escala dele. */
  const [otherDaysAvailabilityRows, setOtherDaysAvailabilityRows] = useState<
    { date: string; types: string[] }[]
  >([{ date: '', types: [] }])
  const [swapSubmitLoading, setSwapSubmitLoading] = useState(false)
  const [swapSubmitError, setSwapSubmitError] = useState<string | null>(null)
  const [swapSubmitSuccess, setSwapSubmitSuccess] = useState(false)
  /** Qual cartão mostra o feedback ao lado do botão «Criar pedido». */
  const [swapSubmitLastFlow, setSwapSubmitLastFlow] = useState<'same' | 'other' | 'direct' | null>(null)
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
  const [rejectSwapSuccessHint, setRejectSwapSuccessHint] = useState<string | null>(null)
  const [notificationsDetailsOpen, setNotificationsDetailsOpen] = useState(false)
  /** Após fechar o painel, o badge fica em 0 até o n.º de não lidas aumentar (nova notificação) ou chegar a 0. */
  const [notificationsBadgeClearedUntilNew, setNotificationsBadgeClearedUntilNew] = useState(false)
  const prevUnreadNotificationCountRef = useRef<number | null>(null)

  const [swapActions, setSwapActions] = useState<SwapActionDto[]>([])
  const [swapActionsLoading, setSwapActionsLoading] = useState(false)
  const [dismissHistoryId, setDismissHistoryId] = useState<number | null>(null)

  const [mySwapRequests, setMySwapRequests] = useState<MySwapRequestDto[]>([])
  const [mySwapsLoading, setMySwapsLoading] = useState(false)

  const [editScaleMode, setEditScaleMode] = useState(false)
  const [shiftEditTarget, setShiftEditTarget] = useState<ShiftDto | null>(null)
  const [shiftEditCodigo, setShiftEditCodigo] = useState('')
  const [shiftEditBucket, setShiftEditBucket] = useState('')
  const [shiftEditOrigin, setShiftEditOrigin] = useState('')
  const [shiftEditLoading, setShiftEditLoading] = useState(false)
  const [shiftEditError, setShiftEditError] = useState<string | null>(null)

  const [importLoading, setImportLoading] = useState(false)
  const [importResult, setImportResult] = useState<{
    teams: string[]
    warning?: string
    skippedFiles?: Array<{
      file: string
      message: string
      filename_year?: number
      filename_month?: number
      pdf_year?: number
      pdf_month?: number
    }>
  } | null>(null)
  const [clearSchedulesLoading, setClearSchedulesLoading] = useState(false)
  const [clearSchedulesMessage, setClearSchedulesMessage] = useState<string | null>(null)
  /** Aviso «com quem trocou» junto à célula (coordenadas em px relativas à viewport). */
  const [swapPartnerBubble, setSwapPartnerBubble] = useState<{
    message: string
    left: number
    top: number
    placement: 'above' | 'below'
  } | null>(null)

  const [loginEmail, setLoginEmail] = useState('')
  const [loginPassword, setLoginPassword] = useState('')
  const [loginError, setLoginError] = useState<string | null>(null)
  const [loginLoading, setLoginLoading] = useState(false)
  const [currentUser, setCurrentUser] = useState<{ id?: number; nome: string; email: string; employee_number: string } | null>(null)

  /** Evita carregar no 1.º render; depois, mudanças de mês/ano disparam o carregamento. */
  const skipMonthAutoLoad = useRef(true)
  /** Debounce ao digitar o n.º de funcionário (evita um pedido por tecla). */
  const employeeNumberLoadTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  /** Evita aplicar resultados de pesquisa antigos se o utilizador continuar a escrever. */
  const employeeSearchSeqRef = useRef(0)
  /** Após long press mostrar colega da troca, evita abrir o painel de troca no mesmo toque. */
  const suppressNextClickRef = useRef(false)

  const shiftsByDate = useMemo(() => {
    const map: Record<string, ShiftDto> = {}
    for (const s of shifts) {
      map[s.data] = s
    }
    return map
  }, [shifts])

  const viewingOwnScale = useMemo(() => {
    if (!currentUser?.employee_number) return false
    return (
      employeeNumber.trim() === String(currentUser.employee_number).trim()
    )
  }, [currentUser, employeeNumber])

  const myOpenSwaps = useMemo(
    () => mySwapRequests.filter((r) => r.status === 'OPEN'),
    [mySwapRequests],
  )
  const myClosedSwaps = useMemo(
    () => mySwapRequests.filter((r) => r.status !== 'OPEN'),
    [mySwapRequests],
  )

  const daysInMonth = getDaysInMonth(year, month)
  const firstWeekday = getFirstWeekday(year, month)

  /** Por defeito segue o mês do calendário; pode mudar só nesta secção. */
  useEffect(() => {
    setOnDutyYear(year)
    setOnDutyMonth(month)
  }, [year, month])

  const onDutyMaxDay = getDaysInMonth(onDutyYear, onDutyMonth)
  useEffect(() => {
    setOnDutyDayInput((prev) => {
      const d = parseInt(prev, 10)
      const num = Number.isNaN(d) ? 1 : d
      if (num > onDutyMaxDay) return String(onDutyMaxDay)
      if (num < 1) return '1'
      return prev
    })
  }, [onDutyYear, onDutyMonth])

  useEffect(() => {
    if (!swapPartnerBubble) return
    const t = setTimeout(() => setSwapPartnerBubble(null), 2000)
    return () => clearTimeout(t)
  }, [swapPartnerBubble])

  async function loadShifts(params?: { employeeNumber?: string; year?: number; month?: number }) {
    const empToLoad = (params?.employeeNumber ?? employeeNumber).trim()
    const yearToLoad = params?.year ?? year
    const monthToLoad = params?.month ?? month
    setLoading(true)
    setError(null)
    try {
      const url = `${API_BASE}/users/${encodeURIComponent(
        empToLoad,
      )}/shifts/${yearToLoad}/${monthToLoad}`
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

  /** Ao mudar mês/ano com as setas, carrega a escala (1.º render ignorado). */
  useEffect(() => {
    if (skipMonthAutoLoad.current) {
      skipMonthAutoLoad.current = false
      return
    }
    const emp = employeeNumber.trim()
    if (!emp) return
    void loadShifts({ employeeNumber: emp, year, month })
    // eslint-disable-next-line react-hooks/exhaustive-deps -- só reagir a year/month
  }, [year, month])

  /** Sem sessão: carrega a escala com o n.º/mês iniciais (o efeito do mês ignora o 1.º render). */
  useEffect(() => {
    if (localStorage.getItem('token')) return
    const emp = employeeNumber.trim()
    if (!emp) return
    void loadShifts({ employeeNumber: emp, year, month })
    // eslint-disable-next-line react-hooks/exhaustive-deps -- só montagem inicial sem token
  }, [])

  useEffect(() => {
    return () => {
      if (employeeNumberLoadTimerRef.current) clearTimeout(employeeNumberLoadTimerRef.current)
    }
  }, [])

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
        skippedFiles: data.skipped_files ?? undefined,
      })
    } catch (e) {
      const msg = isNetworkError(e) ? NETWORK_ERROR_MESSAGE : (e instanceof Error ? e.message : String(e))
      setImportResult({
        teams: [],
        warning: msg,
        skippedFiles: undefined,
      })
    } finally {
      setImportLoading(false)
    }
  }

  async function runClearSchedules() {
    if (
      !window.confirm(
        'Apagar TODAS as escalas na base de dados e todos os dados de trocas/notificações/histórico ligados a turnos? Utilizadores e equipas mantêm-se. Esta ação não tem anulação.',
      )
    ) {
      return
    }
    const typed = window.prompt(
      `Para confirmar, escreva exatamente (maiúsculas e underscores):\n${CLEAR_SCHEDULES_CONFIRM}`,
    )
    if (typed !== CLEAR_SCHEDULES_CONFIRM) {
      setClearSchedulesMessage(
        typed === null ? 'Operação cancelada.' : 'Frase incorreta — nada foi apagado.',
      )
      return
    }
    setClearSchedulesLoading(true)
    setClearSchedulesMessage(null)
    try {
      const res = await apiFetch(`${API_BASE}/import/clear-schedules`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ confirm: CLEAR_SCHEDULES_CONFIRM }),
      })
      const data = await res.json().catch(() => ({}))
      if (!res.ok) {
        const msg = Array.isArray(data.detail)
          ? data.detail.map((o: { msg?: string }) => o?.msg).filter(Boolean).join('; ')
          : (data.detail ?? data.message)
        throw new Error(msg || `HTTP ${res.status}`)
      }
      const extra =
        typeof data.shifts_removed === 'number' && typeof data.monthly_schedules_removed === 'number'
          ? ` (${data.shifts_removed} turnos, ${data.monthly_schedules_removed} escalas mensais removidas.)`
          : ''
      setClearSchedulesMessage((data.message as string) + extra)
      setShifts([])
    } catch (e) {
      const msg = isNetworkError(e) ? NETWORK_ERROR_MESSAGE : (e instanceof Error ? e.message : String(e))
      setClearSchedulesMessage(`Erro: ${msg}`)
    } finally {
      setClearSchedulesLoading(false)
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
    const maxD = getDaysInMonth(onDutyYear, onDutyMonth)
    const day = Math.min(maxD, Math.max(1, parseInt(onDutyDayInput, 10) || 1))
    const dateStr = `${onDutyYear}-${String(onDutyMonth).padStart(2, '0')}-${String(day).padStart(2, '0')}`
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

  function originStatusLabel(
    origin_status: string | null | undefined,
    team: string | null,
    showTrocaBht?: boolean,
    showTrocaTs?: boolean,
  ): string {
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
        return showTrocaTs ? 'TROCA TS' : 'TS'
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
          const now = new Date()
          const currentYear = now.getFullYear()
          const currentMonth = now.getMonth() + 1
          setCurrentUser({ id: data.id, nome: data.nome, email: data.email, employee_number: emp })
          if (emp) {
            setEmployeeNumber(emp)
            setEmployeeInput(emp)
            setYear(currentYear)
            setMonth(currentMonth)
            loadShifts({ employeeNumber: emp, year: currentYear, month: currentMonth })
          }
        })
        .catch(() => setCurrentUser(null))
    } else {
      setCurrentUser(null)
    }
  }, [])

  useEffect(() => {
    setRejectSwapSuccessHint(null)
  }, [currentUser?.id])

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
      if (!meRes.ok) {
        localStorage.removeItem('token')
        setCurrentUser(null)
        let detail = 'Não foi possível validar a sessão.'
        try {
          const errBody = (await meRes.json()) as { detail?: unknown }
          if (typeof errBody?.detail === 'string') detail = errBody.detail
        } catch {
          /* usar mensagem genérica */
        }
        setLoginError(
          `${detail} Tente outra vez; se o erro persistir, em Definições do browser apague os dados deste site (token antigo).`,
        )
        return
      }
      const me = await meRes.json()
      const emp = (me.employee_number ?? '').toString().trim()
      const now = new Date()
      const currentYear = now.getFullYear()
      const currentMonth = now.getMonth() + 1
      setCurrentUser({ id: me.id, nome: me.nome, email: me.email, employee_number: emp })
      if (emp) {
        setEmployeeNumber(emp)
        setEmployeeInput(emp)
        setYear(currentYear)
        setMonth(currentMonth)
        await loadShifts({ employeeNumber: emp, year: currentYear, month: currentMonth })
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
    setEmployeeScaleResults([])
    setSameDayTypes([])
    setOtherDaysReceiveOnOfferDate([])
    setOtherDaysAvailabilityRows([{ date: '', types: [] }])
    setSwapSubmitError(null)
    setSwapSubmitSuccess(false)
    setSwapSubmitLastFlow(null)
    setExistingSwapIdToCancel(null)
    setSwapActions([])
    setMySwapRequests([])
    setOnDutyList([])
    setOnDutyError(null)
    setOnDutyLoading(false)
    setOnDutySearched(false)
    setOnDutyDayInput('5')
    setOnDutyCode('M')
    setOnDutyYear(year)
    setOnDutyMonth(month)
    setEditScaleMode(false)
    setShiftEditTarget(null)
    setShiftEditError(null)
    setRejectSwapSuccessHint(null)
    setRejectSwapError(null)
    setAcceptSwapError(null)
    setNotifications([])
  }

  function openShiftEdit(shift: ShiftDto) {
    setSelectedShift(null)
    setShiftEditTarget(shift)
    setShiftEditCodigo(shift.codigo)
    setShiftEditBucket(shift.color_bucket || '')
    setShiftEditOrigin(shift.origin_status || '')
    setShiftEditError(null)
  }

  async function saveManualShift() {
    if (!shiftEditTarget || !currentUser) return
    const codigo = shiftEditCodigo.trim()
    if (!codigo) {
      setShiftEditError('Indique o código do turno.')
      return
    }
    setShiftEditLoading(true)
    setShiftEditError(null)
    try {
      const body: { codigo: string; color_bucket?: string; origin_status?: string } = {
        codigo,
      }
      if (shiftEditBucket) body.color_bucket = shiftEditBucket
      if (shiftEditOrigin) body.origin_status = shiftEditOrigin
      const res = await apiFetch(`${API_BASE}/shifts/${shiftEditTarget.id}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json', ...getAuthHeaders() },
        body: JSON.stringify(body),
      })
      if (res.status === 401) {
        setShiftEditError('Sessão expirou. Inicie sessão outra vez.')
        return
      }
      if (!res.ok) {
        let msg = await res.text()
        try {
          const j = JSON.parse(msg) as { detail?: unknown }
          if (j.detail != null)
            msg = typeof j.detail === 'string' ? j.detail : JSON.stringify(j.detail)
        } catch {
          /* usar texto */
        }
        throw new Error(msg || `HTTP ${res.status}`)
      }
      const editedId = shiftEditTarget.id
      setShiftEditTarget(null)
      if (selectedShift?.id === editedId) setSelectedShift(null)
      await loadShifts()
    } catch (e) {
      setShiftEditError(
        isNetworkError(e) ? NETWORK_ERROR_MESSAGE : e instanceof Error ? e.message : String(e),
      )
    } finally {
      setShiftEditLoading(false)
    }
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
      const res = await fetch(
        `${API_BASE}/swap-requests/mine?include_recent_closed=1&closed_limit=5`,
        { headers: getAuthHeaders() },
      )
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
  const unreadNotificationCount = visibleNotifications.length

  useEffect(() => {
    const prev = prevUnreadNotificationCountRef.current
    if (prev !== null && unreadNotificationCount > prev) {
      setNotificationsBadgeClearedUntilNew(false)
    }
    if (unreadNotificationCount === 0) {
      setNotificationsBadgeClearedUntilNew(false)
    }
    prevUnreadNotificationCountRef.current = unreadNotificationCount
  }, [unreadNotificationCount])

  const notificationsBadgeEffectiveZero =
    notificationsDetailsOpen ||
    (notificationsBadgeClearedUntilNew && unreadNotificationCount > 0)
  const notificationsBadgeShow =
    notificationsDetailsOpen || unreadNotificationCount > 0
  const notificationsBadgeDisplayCount = notificationsBadgeEffectiveZero ? 0 : unreadNotificationCount

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

  async function acceptSwapFromNotification(swapRequestId: number, notificationId: number) {
    setAcceptSwapError(null)
    setRejectSwapSuccessHint(null)
    setAcceptSwapLoading(notificationId)
    try {
      const q = new URLSearchParams({ notification_id: String(notificationId) })
      const res = await fetch(`${API_BASE}/swap-requests/${swapRequestId}/accept?${q}`, {
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

  async function rejectSwapFromNotification(swapRequestId: number, notificationId: number) {
    setRejectSwapError(null)
    setRejectSwapSuccessHint(null)
    setRejectSwapLoading(notificationId)
    try {
      const q = new URLSearchParams({ notification_id: String(notificationId) })
      const res = await fetch(`${API_BASE}/swap-requests/${swapRequestId}/reject?${q}`, {
        method: 'POST',
        headers: getAuthHeaders(),
      })
      if (!res.ok) {
        const text = await res.text()
        setRejectSwapError(text && text.length < 300 ? text : 'Não foi possível recusar a troca.')
        return
      }
      const data = await res.json().catch(() => ({} as { message?: string }))
      await loadNotifications()
      await loadSwapActions()
      setRejectSwapSuccessHint(
        typeof data.message === 'string'
          ? data.message
          : 'Indicou que não aceita este pedido para si. O pedido continua em aberto para outros colegas; só o proponente pode cancelá-lo.',
      )
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

  function toggleOtherDaysReceiveOnOffer(code: string) {
    setOtherDaysReceiveOnOfferDate((prev) =>
      prev.includes(code) ? prev.filter((c) => c !== code) : [...prev, code],
    )
  }

  function toggleOtherDaysAvailabilityType(rowIndex: number, code: string) {
    setOtherDaysAvailabilityRows((prev) => {
      const next = [...prev]
      const row = next[rowIndex]
      const types = row?.types.includes(code)
        ? row.types.filter((c) => c !== code)
        : [...(row?.types ?? []), code]
      next[rowIndex] = { ...row, types }
      return next
    })
  }

  function updateOtherDaysAvailabilityDate(rowIndex: number, date: string) {
    setOtherDaysAvailabilityRows((prev) => {
      const next = [...prev]
      if (next[rowIndex]) next[rowIndex] = { ...next[rowIndex], date }
      return next
    })
  }

  function addOtherDaysAvailabilityRow() {
    setOtherDaysAvailabilityRows((prev) => [...prev, { date: '', types: [] }])
  }

  function removeOtherDaysAvailabilityRow(i: number) {
    setOtherDaysAvailabilityRows((prev) =>
      prev.length <= 1 ? [{ date: '', types: [] }] : prev.filter((_, idx) => idx !== i),
    )
  }

  function buildOtherDaysWantedOptions(): { date: string; shift_types: string[] }[] {
    if (!selectedShift) return []
    const offerD = selectedShift.data
    const byDate = new Map<string, Set<string>>()
    if (otherDaysReceiveOnOfferDate.length > 0) {
      byDate.set(offerD, new Set(otherDaysReceiveOnOfferDate))
    }
    for (const row of otherDaysAvailabilityRows) {
      const d = row.date.trim()
      if (!d || row.types.length === 0) continue
      if (!byDate.has(d)) byDate.set(d, new Set())
      const s = byDate.get(d)!
      for (const t of row.types) s.add(t)
    }
    if (byDate.size === 0) return []
    return [...byDate.entries()]
      .map(([date, set]) => ({ date, shift_types: [...set].sort() }))
      .sort((a, b) => a.date.localeCompare(b.date))
  }

  async function handleSwap400(res: Response) {
    const existingId = res.headers.get('X-Existing-Swap-Id')
    if (existingId) setExistingSwapIdToCancel(parseInt(existingId, 10))
    const data = await res.json().catch(() => ({}))
    let msg = 'Já existe um pedido de troca em aberto para este turno.'
    if (typeof data.detail === 'string') {
      msg = data.detail
    } else if (Array.isArray(data.detail) && data.detail.length > 0) {
      const first = data.detail[0] as { msg?: string }
      if (first && typeof first.msg === 'string') msg = first.msg
    }
    setSwapSubmitError(msg)
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
    setSwapSubmitLastFlow('same')
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
    for (const row of otherDaysAvailabilityRows) {
      const d = row.date.trim()
      if (!d || row.types.length === 0) continue
      if (!shiftsByDate[d]) {
        setSwapSubmitLastFlow('other')
        setSwapSubmitError(
          `Na Proposta 2: em ${d} não há turno seu na escala visível (mude o mês/nº ou escolha um dia em que trabalha).`,
        )
        return
      }
    }
    const options = buildOtherDaysWantedOptions()
    if (options.length === 0) {
      setSwapSubmitLastFlow('other')
      setSwapSubmitError(
        'Use a Proposta 1 (turnos do colega no dia do turno que cede) e/ou a Proposta 2 (outro dia: o seu turno por turnos dele que marcar).',
      )
      return
    }
    setSwapSubmitLastFlow('other')
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
      setOtherDaysReceiveOnOfferDate([])
      setOtherDaysAvailabilityRows([{ date: '', types: [] }])
      loadNotifications()
      loadMySwapRequests()
    } catch (e) {
      setSwapSubmitError(e instanceof Error ? e.message : String(e))
    } finally {
      setSwapSubmitLoading(false)
    }
  }

  async function fetchUsersSearch(query: string): Promise<UserSearchResult[]> {
    const t = query.trim()
    if (t.length < 2) return []
    try {
      const res = await apiFetch(`${API_BASE}/users/search?q=${encodeURIComponent(t)}`, {
        headers: getAuthHeaders(),
      })
      if (!res.ok) return []
      return (await res.json()) as UserSearchResult[]
    } catch {
      return []
    }
  }

  function handleEmployeeInputChange(raw: string) {
    setEmployeeInput(raw)
    const t = raw.trim()
    if (!t) {
      setEmployeeNumber('')
      setEmployeeScaleResults([])
      return
    }
    const digitsOnly = t.replace(/\s/g, '')
    if (/^\d+$/.test(digitsOnly)) {
      setEmployeeNumber(digitsOnly)
      setEmployeeScaleResults([])
      if (employeeNumberLoadTimerRef.current) clearTimeout(employeeNumberLoadTimerRef.current)
      employeeNumberLoadTimerRef.current = setTimeout(() => {
        employeeNumberLoadTimerRef.current = null
        void loadShifts({ employeeNumber: digitsOnly, year, month })
      }, 400)
      return
    }
    setEmployeeNumber('')
    void (async () => {
      const seq = ++employeeSearchSeqRef.current
      const data = await fetchUsersSearch(raw)
      if (seq !== employeeSearchSeqRef.current) return
      setEmployeeScaleResults(data)
    })()
  }

  function pickEmployeeForScale(user: UserSearchResult) {
    const emp = String(user.employee_number ?? '').trim()
    if (employeeNumberLoadTimerRef.current) {
      clearTimeout(employeeNumberLoadTimerRef.current)
      employeeNumberLoadTimerRef.current = null
    }
    setEmployeeNumber(emp)
    setEmployeeInput(`${user.nome} (${emp})`)
    setEmployeeScaleResults([])
    void loadShifts({ employeeNumber: emp, year, month })
  }

  function goToMyScale() {
    if (!currentUser?.employee_number) return
    const emp = String(currentUser.employee_number).trim()
    if (!emp) return
    if (employeeNumberLoadTimerRef.current) {
      clearTimeout(employeeNumberLoadTimerRef.current)
      employeeNumberLoadTimerRef.current = null
    }
    setEmployeeNumber(emp)
    const nome = (currentUser.nome || '').trim()
    setEmployeeInput(nome ? `${nome} (${emp})` : emp)
    setEmployeeScaleResults([])
    void loadShifts({ employeeNumber: emp, year, month })
  }

  async function searchDirectUsers(query: string) {
    setDirectQuery(query)
    setDirectResults([])
    if (!query || query.trim().length < 2) {
      return
    }
    try {
      const data = await fetchUsersSearch(query)
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
      setSwapSubmitLastFlow('direct')
      setSwapSubmitError('Escolha pelo menos um colega para a troca direta.')
      return
    }
    setSwapSubmitLastFlow('direct')
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

  function mySwapStatusLabel(status: string): string {
    switch (status) {
      case 'OPEN':
        return 'Em aberto'
      case 'REJECTED':
        return 'Recusado'
      case 'ACCEPTED':
        return 'Aceite'
      case 'PROPOSED':
        return 'Em proposta'
      default:
        return status
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
              <p className="login-bar-hint">
                <strong>Email</strong> e <strong>palavra-passe</strong>. O campo abaixo só carrega escalas; com sessão pode
                pesquisar por nome — não substitui o login.
              </p>
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
        <div className="title-row-inline">
          <h1>Escala pessoal</h1>
          <details className="scale-intro-details">
            <summary className="scale-intro-summary">Clique para ver</summary>
            <p className="scale-subtitle scale-subtitle--intro">
              N.º de funcionário (ou pesquise por nome com sessão iniciada) e mês. A escala carrega ao mudar o mês, ao
              alterar o n.º ou ao escolher um nome na lista.
            </p>
          </details>
        </div>

        <div className="scale-controls">
          <div className="employee-scale-row">
            <label className="control-group employee-scale-field">
              <span>Nº funcionário / nome</span>
              <input
                type="text"
                value={employeeInput}
                onChange={(e) => handleEmployeeInputChange(e.target.value)}
                placeholder={
                  currentUser
                    ? 'Ex.: 405541 ou escreva o nome (ex.: Rui)…'
                    : 'Nº de funcionário (inicie sessão para pesquisar por nome)'
                }
                autoComplete="off"
              />
              {employeeScaleResults.length > 0 && (
                <ul className="direct-search-results employee-scale-search-results" role="listbox">
                  {employeeScaleResults.map((u) => (
                    <li key={u.id} role="presentation">
                      <button type="button" onClick={() => pickEmployeeForScale(u)}>
                        {u.nome} ({u.employee_number})
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </label>
            {currentUser && (
              <button
                type="button"
                className="btn-my-scale"
                onClick={goToMyScale}
                title="Mostrar a sua escala (o seu n.º de funcionário)"
              >
                Minha escala
              </button>
            )}
          </div>
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
          {loading && (
            <p className="scale-loading-hint" aria-live="polite">
              A carregar escala…
            </p>
          )}
          {currentUser && (
            <label
              className="edit-scale-toggle"
              title={
                viewingOwnScale
                  ? 'Corrija códigos/cores após import; não disponível com pedido de troca em aberto nesse dia.'
                  : 'Mude o n.º de funcionário acima para o seu para editar a sua escala.'
              }
            >
              <input
                type="checkbox"
                checked={editScaleMode}
                disabled={!viewingOwnScale}
                onChange={(e) => {
                  const on = e.target.checked
                  setEditScaleMode(on)
                  setSelectedShift(null)
                  setShiftEditTarget(null)
                  setShiftEditError(null)
                  setSwapSubmitError(null)
                  setSwapSubmitSuccess(false)
                  setSwapSubmitLastFlow(null)
                }}
              />
              <span>Editar a minha escala</span>
            </label>
          )}
          {SHOW_IMPORT_BUTTON && (
            <>
              <button
                type="button"
                className="btn-load btn-load--light"
                onClick={runImport}
                disabled={importLoading || clearSchedulesLoading}
                title="Lê os PDF das pastas 'atual' e 'seguinte' e importa para a base de dados. Depois mude o mês ou atualize o n.º para ver a escala."
              >
                {importLoading ? 'A importar...' : 'Importar escalas'}
              </button>
              <button
                type="button"
                className="btn-load btn-load--light"
                onClick={runClearSchedules}
                disabled={importLoading || clearSchedulesLoading}
                title="Apaga shifts e monthly_schedules e dados de trocas na BD. Utilizadores e equipas mantêm-se. Depois pode importar de novo."
                style={{
                  color: 'var(--danger, #b91c1c)',
                }}
              >
                {clearSchedulesLoading ? 'A limpar...' : 'Limpar escalas (BD)'}
              </button>
            </>
          )}
        </div>
        {SHOW_IMPORT_BUTTON && (
          <p className="scale-api-line">
            <strong>API (dev):</strong> {API_BASE}
          </p>
        )}
      </header>

      {clearSchedulesMessage && (
        <div className={clearSchedulesMessage.startsWith('Erro:') ? 'scale-error' : 'scale-success-msg'}>
          <p style={{ margin: 0 }}>{clearSchedulesMessage}</p>
        </div>
      )}

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
          {importResult.skippedFiles && importResult.skippedFiles.length > 0 && (
            <div style={{ margin: '0.75rem 0 0', fontSize: '0.85rem' }}>
              <strong>Ficheiros ignorados (nome ≠ mês no PDF):</strong>
              <ul style={{ margin: '0.35rem 0 0', paddingLeft: '1.25rem' }}>
                {importResult.skippedFiles.map((s) => (
                  <li key={s.file}>
                    <code>{s.file}</code>: {s.message}
                  </li>
                ))}
              </ul>
            </div>
          )}
          {importResult.teams.length > 0 && (
            <p style={{ margin: '0.5rem 0 0', fontSize: '0.9rem' }}>
              Pode agora escolher o mês (ex.: Abril) — a escala atualiza ao mudar o mês ou o n.º de funcionário.
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
              // Troca serviço no PDF usa gray_dark; se origin_status veio preenchido e o bucket faltou, não dizer «rota» (branco).
              const bucketForCalendar =
                shift?.origin_status === 'troca_servico'
                  ? shift.color_bucket || 'gray_dark'
                  : shift?.color_bucket
              const bg = shift ? backgroundColor(bucketForCalendar) : undefined
              const inconsistent = shift?.inconsistency_flag
              const msg = shift?.inconsistency_message
              const today = new Date()
              const isPast =
                year < today.getFullYear() ||
                (year === today.getFullYear() && month < today.getMonth() + 1) ||
                (year === today.getFullYear() && month === today.getMonth() + 1 && day < today.getDate())
              const canEditCell = Boolean(
                editScaleMode && viewingOwnScale && shift && currentUser,
              )
              const canOpenSwap = Boolean(shift && !isPast && viewingOwnScale && !editScaleMode)
              const isClickable = canEditCell || canOpenSwap
              // Célula dividida para trocas especiais:
              // - troca_servico: topo cinzento claro + base cinzento escuro (bucket omissão ⇒ gray_dark)
              // - TROCA BHT/TS: topo vermelho/amarelo + base cinzento escuro
              const isOriginTroca = shift?.origin_status === 'troca_servico'
              const isTrocaBht = shift?.origin_status === 'bht' && shift?.show_troca_bht === true
              const isTrocaTs = shift?.origin_status === 'ts' && shift?.show_troca_ts === true
              const isSplitCell = isOriginTroca || isTrocaBht || isTrocaTs
              const bottomHalfDark = true
              const splitBottomBg = (isTrocaBht || isTrocaTs) ? 'var(--shift-gray-dark)' : bg
              const showSwapPartnerLongPress =
                Boolean(isOriginTroca && shift?.swap_partner_name)
              const cellTitle = inconsistent
                ? msg || 'Inconsistência'
                : isPast && !canEditCell
                  ? 'Dia passado'
                  : canEditCell
                    ? 'Clique para editar este turno'
                    : canOpenSwap
                      ? 'Clique para opções de troca'
                      : undefined
              const cellTitleWithPartner =
                cellTitle && showSwapPartnerLongPress
                  ? `${cellTitle} · Pressione longo: com quem trocou`
                  : showSwapPartnerLongPress
                    ? 'Pressione longo para ver com quem trocou (troca serviço)'
                    : cellTitle
              function handleCellActivate() {
                if (suppressNextClickRef.current) {
                  suppressNextClickRef.current = false
                  return
                }
                if (canEditCell && shift) openShiftEdit(shift)
                else if (canOpenSwap && shift) setSelectedShift(shift)
              }
              function showSwapPartnerMessage(anchorEl: HTMLElement) {
                if (!shift?.swap_partner_name) return
                const name = shift.swap_partner_name.trim()
                const emp = (shift.swap_partner_employee_number || '').trim()
                const message = emp ? `Troca com ${name} (${emp})` : `Troca com ${name}`
                const rect = anchorEl.getBoundingClientRect()
                const left = rect.left + rect.width / 2
                // Pouco espaço no topo do ecrã → mostrar por baixo da célula
                const placement: 'above' | 'below' = rect.top < 72 ? 'below' : 'above'
                const top = placement === 'above' ? rect.top : rect.bottom
                setSwapPartnerBubble({ message, left, top, placement })
                if (typeof navigator !== 'undefined' && navigator.vibrate) navigator.vibrate(20)
              }
              return (
                <div
                  key={day}
                  role={isClickable ? 'button' : undefined}
                  tabIndex={isClickable ? 0 : undefined}
                  className={`calendar-cell ${isClickable ? 'calendar-cell--clickable' : ''} ${canEditCell ? 'calendar-cell--edit-mode' : ''} ${isPast ? 'calendar-cell--past' : ''} ${selectedShift?.id === shift?.id ? 'calendar-cell--selected' : ''} ${inconsistent ? 'calendar-cell--inconsistent' : ''} ${isSplitCell ? 'calendar-cell--split' : ''} ${(isTrocaBht || isTrocaTs) ? 'calendar-cell--split-bht' : ''} ${showSwapPartnerLongPress ? 'calendar-cell--swap-partner-hint' : ''} ${!isSplitCell && bucketForCalendar === 'gray_dark' ? 'calendar-cell--dark-bg' : ''} ${!isSplitCell && shift && (bucketForCalendar === 'gray_light' || (bucketForCalendar !== 'gray_dark' && bucketForCalendar !== 'gray_light')) ? 'calendar-cell--light-bg' : ''}`}
                  style={!isSplitCell && bg ? { backgroundColor: bg } : undefined}
                  title={cellTitleWithPartner}
                  onClick={isClickable ? handleCellActivate : undefined}
                  onKeyDown={isClickable ? (e) => e.key === 'Enter' && handleCellActivate() : undefined}
                  onPointerDown={
                    showSwapPartnerLongPress && shift
                      ? (e) => {
                          if (e.button !== 0) return
                          const pointerId = e.pointerId
                          let tid: ReturnType<typeof setTimeout> | null = null
                          const el = e.currentTarget
                          try {
                            el.setPointerCapture(pointerId)
                          } catch {
                            /* ignore */
                          }
                          tid = window.setTimeout(() => {
                            tid = null
                            suppressNextClickRef.current = true
                            try {
                              el.releasePointerCapture(pointerId)
                            } catch {
                              /* ignore */
                            }
                            showSwapPartnerMessage(el)
                          }, 480)
                          const cleanup = () => {
                            if (tid != null) {
                              clearTimeout(tid)
                              tid = null
                            }
                            try {
                              el.releasePointerCapture(pointerId)
                            } catch {
                              /* ignore */
                            }
                            el.removeEventListener('pointerup', cleanup)
                            el.removeEventListener('pointercancel', cleanup)
                            el.removeEventListener('lostpointercapture', cleanup)
                          }
                          el.addEventListener('pointerup', cleanup)
                          el.addEventListener('pointercancel', cleanup)
                          el.addEventListener('lostpointercapture', cleanup)
                        }
                      : undefined
                  }
                  onContextMenu={
                    showSwapPartnerLongPress && shift
                      ? (e) => {
                          e.preventDefault()
                          suppressNextClickRef.current = true
                          showSwapPartnerMessage(e.currentTarget)
                        }
                      : undefined
                  }
                >
                  {isSplitCell && shift ? (
                    <>
                      <div className="cell-half cell-half--top">
                        <span className="cell-day">{day}</span>
                      </div>
                      <div
                        className={`cell-half cell-half--bottom ${bottomHalfDark ? 'cell-half--dark' : 'cell-half--light'}`}
                        style={{ backgroundColor: splitBottomBg }}
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
          <details className="calendar-legend-details">
            <summary className="calendar-legend-summary">Legenda — clique para ver</summary>
            <div className="calendar-legend">
              <span><em>Fundo claro</em> Rotação normal</span>
              <span><em>Cinzento claro</em> Troca NAV</span>
              <span><em>Cinzento escuro</em> Troca serviço</span>
              <span>
                <em>Pressione longo</em> na troca serviço (com registo de troca aceite) para ver com quem trocou — mensagem 2 s por cima do dia · no PC: clique direito
              </span>
              <span><em>Vermelho</em> BHT</span>
              <span><em>Amarelo</em> TS</span>
              <span><em>Rosa</em> Mudança de Funções</span>
              <span><em>Verde</em> Outros</span>
              <span className="legend-flag">⚠ Turno trocado, escala ainda não atualizada</span>
              <span>
                · Clique num turno para {editScaleMode && viewingOwnScale ? 'editar' : 'ver opções de troca'}
              </span>
            </div>
          </details>
        </div>
      )}

      <section className="on-duty-section">
        <h2>Quem está de serviço?</h2>
        <div className="on-duty-controls">
          <label className="control-group">
            <span>Dia</span>
            <select
              className="on-duty-day-select"
              value={onDutyDayInput}
              onChange={(e) => setOnDutyDayInput(e.target.value)}
              aria-label="Dia do mês (1 a último dia)"
            >
              {Array.from({ length: onDutyMaxDay }, (_, i) => i + 1).map((d) => (
                <option key={d} value={String(d)}>
                  {d}
                </option>
              ))}
            </select>
          </label>
          <label className="control-group">
            <span>Mês</span>
            <select
              className="on-duty-month-select"
              value={onDutyMonth}
              onChange={(e) => setOnDutyMonth(Number(e.target.value))}
            >
              {MONTH_NAMES.map((name, idx) => (
                <option key={name} value={idx + 1}>
                  {name}
                </option>
              ))}
            </select>
          </label>
          <label className="control-group">
            <span>Ano</span>
            <input
              type="number"
              className="on-duty-year-input"
              min={2020}
              max={2035}
              value={onDutyYear}
              onChange={(e) => setOnDutyYear(Math.max(2020, Math.min(2035, Number(e.target.value) || onDutyYear)))}
            />
          </label>
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
                <span> · {originStatusLabel(p.origin_status, p.team, p.show_troca_bht, p.show_troca_ts)}</span>
              </li>
            ))}
          </ul>
        )}
        {onDutySearched && !onDutyLoading && !onDutyError && onDutyList.length === 0 && (
          <p className="scale-empty">Nenhuma pessoa encontrada para este dia e turno.</p>
        )}
      </section>

      {shiftEditTarget && (
        <section className="swap-panel shift-edit-panel">
          <div className="swap-panel-header">
            <h2>
              Editar turno — dia {shiftEditTarget.data} (atual: {shiftEditTarget.codigo})
            </h2>
            <button
              type="button"
              className="btn-close-panel"
              onClick={() => {
                setShiftEditTarget(null)
                setShiftEditError(null)
              }}
              aria-label="Fechar"
            >
              ✕
            </button>
          </div>
          <p className="swap-panel-intro">
            Corrija o código após um import ou um erro pontual. Não é possível se existir um pedido de troca{' '}
            <strong>em aberto</strong> para este dia.
          </p>
          <div className="shift-edit-fields">
            <label className="control-group">
              <span>Código do turno</span>
              <input
                type="text"
                value={shiftEditCodigo}
                onChange={(e) => setShiftEditCodigo(e.target.value)}
                list="suggested-shift-codes"
                autoComplete="off"
                placeholder="ex: M, IB, mE"
              />
              <datalist id="suggested-shift-codes">
                {SUGGESTED_SHIFT_CODES.map((c) => (
                  <option key={c} value={c} />
                ))}
              </datalist>
            </label>
            <label className="control-group">
              <span>Cor (opcional)</span>
              <select
                value={shiftEditBucket}
                onChange={(e) => setShiftEditBucket(e.target.value)}
              >
                {MANUAL_COLOR_OPTIONS.map((o) => (
                  <option key={o.label} value={o.value}>
                    {o.label}
                  </option>
                ))}
              </select>
            </label>
            <label className="control-group">
              <span>Origem (opcional)</span>
              <select
                value={shiftEditOrigin}
                onChange={(e) => setShiftEditOrigin(e.target.value)}
              >
                {MANUAL_ORIGIN_OPTIONS.map((o) => (
                  <option key={o.label} value={o.value}>
                    {o.label}
                  </option>
                ))}
              </select>
            </label>
          </div>
          {shiftEditError && <div className="scale-error" style={{ marginTop: '0.75rem' }}>{shiftEditError}</div>}
          <div className="shift-edit-actions">
            <button
              type="button"
              className="btn-load"
              onClick={() => void saveManualShift()}
              disabled={shiftEditLoading}
            >
              {shiftEditLoading ? 'A guardar...' : 'Guardar alterações'}
            </button>
            <button
              type="button"
              className="btn-load btn-load--light"
              onClick={() => {
                setShiftEditTarget(null)
                setShiftEditError(null)
              }}
              disabled={shiftEditLoading}
            >
              Cancelar
            </button>
          </div>
        </section>
      )}

      {selectedShift && !shiftEditTarget && (
        <section className="swap-panel">
          <div className="swap-panel-header">
            <h2>Trocar turno {selectedShift.codigo} do dia {selectedShift.data}</h2>
            <button
              type="button"
              className="btn-close-panel"
              onClick={() => {
                setSelectedShift(null)
                setSwapSubmitError(null)
                setSwapSubmitSuccess(false)
                setSwapSubmitLastFlow(null)
                setExistingSwapIdToCancel(null)
              }}
              aria-label="Fechar"
            >
              ✕
            </button>
          </div>
          <p className="swap-panel-intro">Escolha como quer propor a troca:</p>

          <div className="swap-option-card">
            <h3 className="swap-option-title">Troca no mesmo dia</h3>
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
            <div className="swap-create-row">
              <button type="button" className="btn-load btn-load--light" onClick={createSwapSameDay} disabled={swapSubmitLoading}>
                {swapSubmitLoading && swapSubmitLastFlow === 'same' ? 'A enviar...' : 'Criar pedido de troca'}
              </button>
              {swapSubmitLastFlow === 'same' && swapSubmitError && (
                <div className="scale-error swap-create-msg">{swapSubmitError}</div>
              )}
              {swapSubmitLastFlow === 'same' && swapSubmitSuccess && (
                <p className="swap-success swap-create-msg">Pedido de troca criado.</p>
              )}
            </div>
          </div>

          <div className="swap-option-card">
            <h3 className="swap-option-title">Troca direta</h3>
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
            <div className="swap-create-row">
              <button type="button" className="btn-load btn-load--light" onClick={createDirectSwap} disabled={swapSubmitLoading}>
                {swapSubmitLoading && swapSubmitLastFlow === 'direct' ? 'A enviar...' : 'Criar pedido de troca direta'}
              </button>
              {swapSubmitLastFlow === 'direct' && swapSubmitError && (
                <div className="scale-error swap-create-msg">{swapSubmitError}</div>
              )}
              {swapSubmitLastFlow === 'direct' && swapSubmitSuccess && (
                <p className="swap-success swap-create-msg">Pedido de troca criado.</p>
              )}
            </div>
          </div>

          <div className="swap-option-card">
            <h3 className="swap-option-title">Troca por outros dias / turnos</h3>
            <p className="swap-hint">
              <strong>Proposta 1</strong> — troca o turno que pretende trocar (ex.: T do dia 25) pelo turno ou
              turnos pretendidos (ex.: DC ou DS). <strong>Proposta 2</strong> — noutro dia, troca o seu turno
              nessa data por um ou mais turnos em que tenha disponibilidade (ex.: DC do dia 21 por M, MG ou Mt).
              Poderá colocar vários dias e vários turnos. Cada dia será uma opção. A troca só é validada pela
              aceitação das duas propostas.
            </p>

            <div className="swap-other-section swap-other-section--step swap-other-section--proposta1">
              <div className="swap-other-step swap-other-step--inline">
                <span className="swap-other-step__num">1</span>
                <h4 className="swap-other-section__title swap-other-step__title">Proposta 1</h4>
              </div>
              <p className="swap-other-section__intro">
                Troco o turno <strong>{selectedShift.codigo}</strong> do dia{' '}
                <strong>{formatNotifCalendarDate(selectedShift.data)}</strong> por um destes turnos:
              </p>
              <div className="swap-checkbox-group">
                {SHIFT_CODES.map((code) => (
                  <label key={code} className="swap-checkbox">
                    <input
                      type="checkbox"
                      checked={otherDaysReceiveOnOfferDate.includes(code)}
                      onChange={() => toggleOtherDaysReceiveOnOffer(code)}
                    />
                    <span>{code}</span>
                  </label>
                ))}
              </div>
            </div>

            <div className="swap-other-section swap-other-section--step">
              <div className="swap-other-step swap-other-step--inline">
                <span className="swap-other-step__num">2</span>
                <h4 className="swap-other-section__title swap-other-step__title">Proposta 2</h4>
              </div>
              <p className="swap-other-section__intro">
                Em cada opção: escolha o dia e marque os turnos que pretende fazer — é a troca do seu turno nesse
                dia (ex.: «troco dia 13 o meu DC por M ou Mt»). Se repetir o dia da Opção 1, as novas condições
                somam-se às da Opção 1.
              </p>
              {otherDaysAvailabilityRows.map((row, i) => {
                const myCodeOnRow = row.date.trim() ? shiftsByDate[row.date.trim()]?.codigo : undefined
                return (
                  <div key={i} className="wanted-row">
                    <div className="wanted-row-header">
                      <span className="wanted-row-title">Proposta 2 · opção {i + 1}</span>
                      {otherDaysAvailabilityRows.length > 1 && (
                        <button
                          type="button"
                          className="btn-remove-row"
                          onClick={() => removeOtherDaysAvailabilityRow(i)}
                        >
                          Remover
                        </button>
                      )}
                    </div>
                    <label className="control-group wanted-row-date-label">
                      <span>Data</span>
                      <input
                        type="date"
                        value={row.date}
                        onChange={(e) => updateOtherDaysAvailabilityDate(i, e.target.value)}
                        className="wanted-date"
                      />
                    </label>
                    <div className="wanted-row-shifts">
                      <span className="wanted-row-shifts-label">
                        {row.date.trim() ? (
                          <>
                            Troco dia <strong>{formatNotifCalendarDate(row.date.trim())}</strong>{' '}
                            <strong>{myCodeOnRow ?? '—'}</strong>
                            {myCodeOnRow ? '' : ' (sem turno seu neste dia na escala — ajuste mês ou data)'} por turnos{' '}
                            <strong>do colega</strong> (marque):
                          </>
                        ) : (
                          <>Escolha a data. Nesse dia está disponível para fazer os seguintes turnos:</>
                        )}
                      </span>
                      <div className="swap-checkbox-group">
                        {SHIFT_CODES.map((code) => (
                          <label key={code} className="swap-checkbox">
                            <input
                              type="checkbox"
                              checked={row.types.includes(code)}
                              onChange={() => toggleOtherDaysAvailabilityType(i, code)}
                            />
                            <span>{code}</span>
                          </label>
                        ))}
                      </div>
                    </div>
                  </div>
                )
              })}
              <button type="button" className="btn-secondary" onClick={addOtherDaysAvailabilityRow}>
                + Adicionar linha (outro dia)
              </button>
            </div>

            <div className="swap-create-row">
              <button type="button" className="btn-load btn-load--light" onClick={createSwapOtherDays} disabled={swapSubmitLoading}>
                {swapSubmitLoading && swapSubmitLastFlow === 'other' ? 'A enviar...' : 'Criar pedido de troca'}
              </button>
              {swapSubmitLastFlow === 'other' && swapSubmitError && (
                <div className="scale-error swap-create-msg">{swapSubmitError}</div>
              )}
              {swapSubmitLastFlow === 'other' && swapSubmitSuccess && (
                <p className="swap-success swap-create-msg">Pedido de troca criado.</p>
              )}
            </div>
          </div>

          {existingSwapIdToCancel != null && (
            <p style={{ marginTop: '0.5rem' }}>
              <button type="button" className="btn-load btn-load--light" onClick={() => cancelSwapRequest(existingSwapIdToCancel!)}>
                Cancelar pedido em aberto
              </button>
            </p>
          )}
        </section>
      )}

      {localStorage.getItem('token') && (
        <section className="my-swaps-section">
          <div className="title-row-inline">
            <h2>Os meus pedidos de troca</h2>
            <details className="scale-intro-details my-swaps-intro-details">
              <summary className="scale-intro-summary">Clique para ver</summary>
              <p className="scale-subtitle scale-subtitle--intro">
                <strong>Em aberto</strong>: à espera de resposta. <strong>Fechados recentemente</strong>: aceites ou
                recusados (detalhe também no histórico abaixo).
              </p>
            </details>
          </div>
          <button
            type="button"
            className="btn-load btn-load--light"
            onClick={loadMySwapRequests}
            disabled={mySwapsLoading}
            style={{ marginBottom: '1rem' }}
          >
            {mySwapsLoading ? 'A carregar...' : 'Atualizar lista'}
          </button>
          {!mySwapsLoading && myOpenSwaps.length === 0 && myClosedSwaps.length === 0 && (
            <p className="scale-empty">Não tem pedidos de troca (em aberto nem fechados recentes).</p>
          )}
          {myOpenSwaps.length > 0 && (
            <>
              <h3 className="my-swaps-subtitle">Em aberto</h3>
              <ul className="my-swaps-list">
                {myOpenSwaps.map((r) => (
                  <li key={r.id} className="my-swap-item">
                    <div className="my-swap-item-body">
                      <div className="my-swap-summary-line">
                        <strong>#{r.id}</strong> · {mySwapKindLabel(r.kind)} ·{' '}
                        <strong>{r.offered_shift_code}</strong> ·{' '}
                        {formatSwapActionOfferedDatePt(r.offered_shift_date)}
                        {r.kind === 'direct' ? directSwapTheirShiftsSuffix(r.direct_targets) : null}
                      </div>
                      {r.kind === 'direct' && r.direct_targets && r.direct_targets.length > 0 && (
                        <div className="my-swap-detail my-swap-detail--para">
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
                          {(() => {
                            const offeredIso = String(r.offered_shift_date).slice(0, 10)
                            const onOffer = r.wanted_options.filter(
                              (o) => String(o.date).slice(0, 10) === offeredIso,
                            )
                            const otherDays = r.wanted_options.filter(
                              (o) => String(o.date).slice(0, 10) !== offeredIso,
                            )
                            const offerTypesSet = new Set<string>()
                            for (const o of onOffer) {
                              for (const t of o.shift_types) offerTypesSet.add(t)
                            }
                            const offerTypesText =
                              offerTypesSet.size > 0
                                ? [...offerTypesSet].sort().join(', ')
                                : null
                            return (
                              <>
                                <div>
                                  <strong>Proponho</strong> {r.offered_shift_code} (
                                  {formatNotifCalendarDate(String(r.offered_shift_date))}
                                  ).
                                  {offerTypesText ? (
                                    <>
                                      {' '}
                                      Neste dia preciso de: {offerTypesText}
                                    </>
                                  ) : null}
                                </div>
                                {otherDays.length > 0 && (
                                  <>
                                    <div className="my-swap-proponho-fazer">
                                      <strong>Proponho fazer:</strong>
                                    </div>
                                    <ul className="my-swap-wanted-list">
                                      {otherDays.map((o) => (
                                        <li key={o.date}>
                                          Dia {formatNotifCalendarDate(o.date)} —{' '}
                                          {o.shift_types.join(', ')}
                                        </li>
                                      ))}
                                    </ul>
                                  </>
                                )}
                              </>
                            )
                          })()}
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
          {myClosedSwaps.length > 0 && (
            <div className="collapsible-with-title">
              <div className="title-row-inline">
                <h3 className="my-swaps-subtitle">Fechados recentemente</h3>
                <details className="closed-swaps-details">
                  <summary className="scale-intro-summary">Clique para ver</summary>
                  <div className="closed-swaps-details__body">
                  <ul className="my-swaps-list">
                  {myClosedSwaps.map((r) => (
                    <li key={r.id} className="my-swap-item my-swap-item--closed">
                    <div className="my-swap-item-body">
                      <div className="my-swap-summary-line">
                        <strong>#{r.id}</strong> · <span className="my-swap-status">{mySwapStatusLabel(r.status)}</span>{' '}
                        · {mySwapKindLabel(r.kind)} · <strong>{r.offered_shift_code}</strong> ·{' '}
                        {formatSwapActionOfferedDatePt(r.offered_shift_date)}
                        {r.kind === 'direct' ? directSwapTheirShiftsSuffix(r.direct_targets) : null}
                      </div>
                      {r.kind === 'direct' && r.direct_targets && r.direct_targets.length > 0 && (
                        <div className="my-swap-detail my-swap-detail--para">
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
                          {(() => {
                            const offeredIso = String(r.offered_shift_date).slice(0, 10)
                            const onOffer = r.wanted_options.filter(
                              (o) => String(o.date).slice(0, 10) === offeredIso,
                            )
                            const otherDays = r.wanted_options.filter(
                              (o) => String(o.date).slice(0, 10) !== offeredIso,
                            )
                            const offerTypesSet = new Set<string>()
                            for (const o of onOffer) {
                              for (const t of o.shift_types) offerTypesSet.add(t)
                            }
                            const offerTypesText =
                              offerTypesSet.size > 0
                                ? [...offerTypesSet].sort().join(', ')
                                : null
                            return (
                              <>
                                <div>
                                  <strong>Proponho</strong> {r.offered_shift_code} (
                                  {formatNotifCalendarDate(String(r.offered_shift_date))}
                                  ).
                                  {offerTypesText ? (
                                    <>
                                      {' '}
                                      Neste dia preciso de: {offerTypesText}
                                    </>
                                  ) : null}
                                </div>
                                {otherDays.length > 0 && (
                                  <>
                                    <div className="my-swap-proponho-fazer">
                                      <strong>Proponho fazer:</strong>
                                    </div>
                                    <ul className="my-swap-wanted-list">
                                      {otherDays.map((o) => (
                                        <li key={o.date}>
                                          Dia {formatNotifCalendarDate(o.date)} —{' '}
                                          {o.shift_types.join(', ')}
                                        </li>
                                      ))}
                                    </ul>
                                  </>
                                )}
                              </>
                            )
                          })()}
                        </div>
                      )}
                    </div>
                    </li>
                  ))}
                  </ul>
                  </div>
                </details>
              </div>
            </div>
          )}
        </section>
      )}

      {localStorage.getItem('token') && (
        <section className="notifications-section">
          <div className="title-row-inline">
            <h2>Notificações</h2>
            <details
              className="closed-swaps-details notifications-details"
              onToggle={(e) => {
                const open = (e.target as HTMLDetailsElement).open
                setNotificationsDetailsOpen(open)
                if (!open) {
                  setNotificationsBadgeClearedUntilNew(true)
                }
              }}
            >
            <summary className="scale-intro-summary">
              Clique para ver
              {notificationsBadgeShow && (
                <span className="notifications-new-badge" aria-live="polite">
                  {notificationsBadgeDisplayCount === 1
                    ? '1 nova notificação'
                    : `${notificationsBadgeDisplayCount} novas notificações`}
                </span>
              )}
            </summary>
            <div className="closed-swaps-details__body">
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
                        {n.notification_kind === 'swap_accepted_summary' && n.body_text && (
                          <span className="notifications-can-accept-text">{n.body_text}</span>
                        )}
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
                        {(!n.notification_kind || n.notification_kind === 'can_accept') &&
                          n.notification_kind !== 'swap_accepted_summary' && (
                          <>
                            {n.requester_name && n.offered_shift_code ? (
                              <span className="notifications-can-accept-text">
                                {n.accepter_package_legs &&
                                n.requester_package_legs &&
                                n.accepter_package_legs.length >= 2 &&
                                n.requester_package_legs.length === n.accepter_package_legs.length ? (
                                  <>
                                    <strong>{n.requester_name}</strong> propõe um{' '}
                                    <strong>pacote de trocas</strong> :
                                    <ul className="notifications-wanted-list" style={{ marginTop: '0.35rem' }}>
                                      {n.requester_package_legs.map((rq, i) => (
                                        <li key={`${rq.date}-${rq.code}-${i}`}>
                                          Troca <strong>{rq.code}</strong> no dia{' '}
                                          {formatNotifCalendarDate(rq.date)} pelo seu{' '}
                                          <strong>{n.accepter_package_legs![i].code}</strong> (
                                          {formatNotifCalendarDate(n.accepter_package_legs![i].date)}).
                                        </li>
                                      ))}
                                    </ul>
                                  </>
                                ) : n.accepter_shift_code && n.accepter_shift_date ? (
                                  <>
                                    <strong>{n.requester_name}</strong> quer trocar o turno{' '}
                                    <strong>{n.offered_shift_code}</strong>
                                    {n.offered_shift_date && (
                                      <> do dia {formatNotifCalendarDate(n.offered_shift_date)}</>
                                    )}{' '}
                                    {String(n.offered_shift_date ?? '').slice(0, 10) ===
                                    String(n.accepter_shift_date).slice(0, 10) ? (
                                      <>
                                        pelo seu <strong>{n.accepter_shift_code}</strong> do mesmo dia.
                                      </>
                                    ) : (
                                      <>
                                        pelo seu <strong>{n.accepter_shift_code}</strong> do dia{' '}
                                        {formatNotifCalendarDate(n.accepter_shift_date)}.
                                      </>
                                    )}
                                  </>
                                ) : (
                                  <>
                                    <strong>{n.requester_name}</strong> quer trocar o turno{' '}
                                    <strong>{n.offered_shift_code}</strong>
                                    {n.offered_shift_date && (
                                      <> do dia {formatNotifCalendarDate(n.offered_shift_date)}</>
                                    )}
                                    {n.wanted_options && n.wanted_options.length > 0 ? (
                                      <>
                                        . Para aceitar, precisa de ter <strong>em troca</strong> um destes
                                        turnos <strong>seus</strong>, nas datas indicadas:
                                        <ul className="notifications-wanted-list">
                                          {n.wanted_options.map((w) => (
                                            <li key={w.date}>
                                              <strong>{formatNotifCalendarDate(w.date)}</strong>
                                              {' — '}
                                              {w.shift_types.join(', ')}
                                            </li>
                                          ))}
                                        </ul>
                                        <span className="notifications-wanted-hint">
                                          Só poderá aceitar no dia em que a sua escala tiver um destes códigos
                                          nessa data.
                                        </span>
                                      </>
                                    ) : (
                                      <>
                                        {n.accepted_shift_types && n.accepted_shift_types.length > 0 ? (
                                          <> por um {n.accepted_shift_types.join(' ou ')} no mesmo dia.</>
                                        ) : (
                                          <> Aceita em troca qualquer turno seu nesse mesmo dia.</>
                                        )}
                                      </>
                                    )}
                                  </>
                                )}
                              </span>
                            ) : (
                              <span>Pedido de troca #{n.swap_request_id} que pode satisfazer.</span>
                            )}
                          </>
                        )}
                      </div>
                      <div className="notifications-item-actions">
                        {(!n.notification_kind || n.notification_kind === 'can_accept') &&
                          n.notification_kind !== 'swap_accepted_summary' && (
                          <>
                            <button
                              type="button"
                              className="btn-load btn-load--light"
                              onClick={() => acceptSwapFromNotification(n.swap_request_id, n.id)}
                              disabled={acceptSwapLoading === n.id}
                            >
                              {acceptSwapLoading === n.id ? 'A aceitar...' : 'Aceitar troca'}
                            </button>
                            <button
                              type="button"
                              className="btn-secondary"
                              onClick={() => rejectSwapFromNotification(n.swap_request_id, n.id)}
                              disabled={rejectSwapLoading === n.id}
                            >
                              {rejectSwapLoading === n.id ? 'A recusar...' : 'Recusar'}
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
            </div>
          </details>
          </div>
        </section>
      )}

      {localStorage.getItem('token') && rejectSwapSuccessHint && (
        <div
          className="scale-success-msg"
          style={{
            margin: '0.75rem 0',
            padding: '0.75rem 1rem',
            display: 'flex',
            flexWrap: 'wrap',
            alignItems: 'center',
            justifyContent: 'space-between',
            gap: '0.75rem',
            textAlign: 'left',
          }}
        >
          <span style={{ flex: '1 1 12rem' }}>{rejectSwapSuccessHint}</span>
          <button
            type="button"
            className="btn-secondary"
            onClick={() => setRejectSwapSuccessHint(null)}
          >
            Fechar
          </button>
        </div>
      )}

      {localStorage.getItem('token') && (
        <section className="my-swaps-section my-requester-history-section">
          <div className="title-row-inline">
            <h2>Histórico dos meus pedidos</h2>
            <details className="closed-swaps-details requester-history-details">
            <summary className="scale-intro-summary">Clique para ver</summary>
            <div className="closed-swaps-details__body">
              <p className="scale-subtitle">
                Respostas aos seus pedidos. Pode apagar linhas (só para si).
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
                      const offeredDate = formatSwapActionOfferedDatePt(a.offered_shift_date)
                      const packageAccepted =
                        a.action_type === 'ACCEPTED' && a.package_legs && a.package_legs.length >= 2
                      return (
                        <li key={a.id} className="notifications-item notifications-item--read">
                          <div className="notifications-item-body">
                            <span>
                              {packageAccepted ? (
                                <>
                                  Aceite pacote de troca por <strong>{a.actor_name || 'um colega'}</strong>:
                                  {swapActionPackageLines(a.package_legs!)}
                                </>
                              ) : a.action_type === 'REJECTED' ? (
                                <>
                                  <strong>{a.actor_name || 'Um colega'}</strong> indicou que não aceita este
                                  pedido para si ({a.offered_shift_code} {offeredDate}
                                  {a.accepter_shift_code ? (
                                    <>
                                      {' '}
                                      — turno dele <strong>{a.accepter_shift_code}</strong>
                                    </>
                                  ) : null}
                                  ).
                                  {a.direct_swap !== true &&
                                    ' O pedido pode continuar aberto para outros colegas.'}
                                </>
                              ) : (
                                <>
                                  Aceite troca {a.offered_shift_code} {offeredDate}
                                  {a.accepter_shift_code ? (
                                    <>
                                      {' '}
                                      por <strong>{a.accepter_shift_code}</strong>
                                    </>
                                  ) : null}{' '}
                                  por <strong>{a.actor_name || 'um colega'}</strong>.
                                </>
                              )}
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
            </div>
          </details>
          </div>
        </section>
      )}
      {swapPartnerBubble && (
        <div
          className={`swap-partner-toast swap-partner-toast--${swapPartnerBubble.placement}`}
          style={{ left: swapPartnerBubble.left, top: swapPartnerBubble.top }}
          role="status"
          aria-live="polite"
        >
          {swapPartnerBubble.message}
        </div>
      )}
    </div>
  )
}

export default App
