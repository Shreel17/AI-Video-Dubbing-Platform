import { useCallback, useEffect, useRef, useState } from 'react'
import type { FormEvent } from 'react'
import './App.css'

const languages = [
  { code: 'hi', name: 'Hindi' },
  { code: 'en', name: 'English' },
  { code: 'es', name: 'Spanish' },
  { code: 'fr', name: 'French' },
  { code: 'de', name: 'German' },
  { code: 'ja', name: 'Japanese' },
  { code: 'pt', name: 'Portuguese' },
  { code: 'ar', name: 'Arabic' },
  { code: 'bn', name: 'Bengali' },
  { code: 'ta', name: 'Tamil' },
  { code: 'te', name: 'Telugu' },
  { code: 'mr', name: 'Marathi' },
]

type JobStatus =
  | 'queued'
  | 'processing'
  | 'completed'
  | 'failed'
  | 'cancelled'

type ProjectJob = {
  job_id: string
  status: JobStatus
  progress: number
  message: string
  output_path?: string | null
  created_at?: string | null
  completed_at?: string | null
  processing_time_seconds?: number | null
}

type CreatedJob = {
  job_id: string
  status: string
  message: string
}

type QualityCheck = {
  id?: string
  label?: string
  name?: string
  status?: string
  summary?: string
  message?: string
  details?: string
}

type QualityReport = {
  overall_status?: string
  checks?: QualityCheck[]
  metrics?: Record<string, unknown>
  warnings?: string[]
  note?: string
}

type Page = 'create' | 'recent' | 'how-it-works'
type Theme = 'light' | 'dark' | 'system'

const getInitialTheme = (): Theme => {
  try {
    const saved = localStorage.getItem('dubly-theme')

    if (saved === 'light' || saved === 'dark' || saved === 'system') {
      return saved
    }
  } catch {
    // Use the default theme if storage is unavailable.
  }

  return 'dark'
}

const API_BASE = (
  import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000/api/v1'
).replace(/\/+$/, '')

const getStatusLabel = (status: string) => {
  switch (status) {
    case 'queued':
      return 'Queued'
    case 'processing':
      return 'Processing'
    case 'completed':
      return 'Completed'
    case 'failed':
      return 'Failed'
    case 'cancelled':
      return 'Cancelled'
    default:
      return status
  }
}

const getProgress = (job: ProjectJob) => {
  if (job.status === 'completed') return 100

  const value = Number(job.progress)
  if (!Number.isFinite(value)) return 0

  return Math.max(0, Math.min(100, value))
}

function App() {
  const fileInput = useRef<HTMLInputElement>(null)

  const [theme, setTheme] = useState<Theme>(getInitialTheme)
  const [activePage, setActivePage] = useState<Page>('create')

  const [videoUrl, setVideoUrl] = useState('')
  const [sourceLanguage, setSourceLanguage] = useState('auto')
  const [targetLanguage, setTargetLanguage] = useState('hi')
  const [selectedFile, setSelectedFile] = useState<File | null>(null)

  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [dragging, setDragging] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [createdJob, setCreatedJob] = useState<CreatedJob | null>(null)

  const [projects, setProjects] = useState<ProjectJob[]>([])
  const [loadingProjects, setLoadingProjects] = useState(true)
  const [projectsError, setProjectsError] = useState('')
  const [refreshingProjects, setRefreshingProjects] = useState(false)
  const [projectAction, setProjectAction] = useState<string | null>(null)

  const [qualityReports, setQualityReports] = useState<
    Record<string, QualityReport>
  >({})
  const [qualityReportErrors, setQualityReportErrors] = useState<
    Record<string, string>
  >({})
  const [loadingQualityReport, setLoadingQualityReport] = useState<
    string | null
  >(null)

  useEffect(() => {
    const root = document.documentElement

    const applyTheme = () => {
      const resolvedTheme =
        theme === 'system'
          ? window.matchMedia('(prefers-color-scheme: dark)').matches
            ? 'dark'
            : 'light'
          : theme

      root.dataset.theme = resolvedTheme
      root.style.colorScheme = resolvedTheme
    }

    applyTheme()

    try {
      localStorage.setItem('dubly-theme', theme)
    } catch {
      // The theme still works for the current session.
    }

    if (theme !== 'system') return

    const mediaQuery = window.matchMedia('(prefers-color-scheme: dark)')
    mediaQuery.addEventListener('change', applyTheme)

    return () => mediaQuery.removeEventListener('change', applyTheme)
  }, [theme])

  const loadQualityReport = async (jobId: string) => {
    setLoadingQualityReport(jobId)

    setQualityReportErrors((current) => {
      const next = { ...current }
      delete next[jobId]
      return next
    })

    try {
      const response = await fetch(
        `${API_BASE}/jobs/${encodeURIComponent(jobId)}/quality-report`,
      )

      const data: unknown = await response.json().catch(() => null)

      if (!response.ok) {
        const detail =
          data &&
          typeof data === 'object' &&
          'detail' in data &&
          typeof data.detail === 'string'
            ? data.detail
            : 'Could not load the quality report.'

        throw new Error(detail)
      }

      if (!data || typeof data !== 'object' || Array.isArray(data)) {
        throw new Error('The quality report has an invalid format.')
      }

      setQualityReports((current) => ({
        ...current,
        [jobId]: data as QualityReport,
      }))
    } catch (err) {
      setQualityReportErrors((current) => ({
        ...current,
        [jobId]:
          err instanceof Error
            ? err.message
            : 'Could not load the quality report.',
      }))
    } finally {
      setLoadingQualityReport((current) =>
        current === jobId ? null : current,
      )
    }
  }

  const loadProjects = useCallback(async (showLoading = false) => {
    if (showLoading) {
      setRefreshingProjects(true)
    }

    try {
      const response = await fetch(`${API_BASE}/jobs?limit=10&offset=0`)

      if (!response.ok) {
        throw new Error('Could not load recent projects.')
      }

      const data: unknown = await response.json()

      let jobs: unknown[] | null = null

      if (Array.isArray(data)) {
        jobs = data
      } else if (data && typeof data === 'object') {
        const result = data as {
          items?: unknown
          jobs?: unknown
          results?: unknown
        }

        if (Array.isArray(result.items)) {
          jobs = result.items
        } else if (Array.isArray(result.jobs)) {
          jobs = result.jobs
        } else if (Array.isArray(result.results)) {
          jobs = result.results
        }
      }

      if (!jobs) {
        throw new Error(
          'The backend returned an unexpected job list format.',
        )
      }

      setProjects(jobs as ProjectJob[])
      setProjectsError('')
    } catch (err) {
      setProjectsError(
        err instanceof Error
          ? err.message
          : 'Could not load recent projects.',
      )
    } finally {
      setLoadingProjects(false)
      setRefreshingProjects(false)
    }
  }, [])

  useEffect(() => {
    let isMounted = true
    let requestInProgress = false
    let intervalId: number

    const refreshProjects = async () => {
      if (!isMounted || requestInProgress) return

      requestInProgress = true

      try {
        await loadProjects()
      } finally {
        requestInProgress = false
      }
    }

    void refreshProjects()

    intervalId = window.setInterval(() => {
      void refreshProjects()
    }, 5000)

    return () => {
      isMounted = false
      window.clearInterval(intervalId)
    }
  }, [loadProjects])

  const chooseFile = (file?: File) => {
    setError('')
    setNotice('')
    setCreatedJob(null)

    if (!file) return

    if (!file.type.startsWith('video/')) {
      setError('Please select a valid video file.')
      return
    }

    if (file.size > 500 * 1024 * 1024) {
      setError('Please choose a video smaller than 500 MB.')
      return
    }

    setSelectedFile(file)
    setVideoUrl('')
  }

  const submitJob = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()

    if (submitting) return

    setError('')
    setNotice('')
    setCreatedJob(null)

    if (!selectedFile && !videoUrl.trim()) {
      setError('Choose a video file or enter a video URL.')
      return
    }

    if (
      sourceLanguage !== 'auto' &&
      sourceLanguage === targetLanguage
    ) {
      setError('Source and target languages must be different.')
      return
    }

    if (!selectedFile) {
      try {
        const url = new URL(videoUrl.trim())

        if (!['http:', 'https:'].includes(url.protocol)) {
          throw new Error('Invalid protocol')
        }
      } catch {
        setError(
          'Enter a valid video URL beginning with https:// or http://.',
        )
        return
      }
    }

    setSubmitting(true)

    try {
      let response: Response

      if (selectedFile) {
        const formData = new FormData()

        formData.append('file', selectedFile)
        formData.append('target_language', targetLanguage)

        if (sourceLanguage !== 'auto') {
          formData.append('source_language', sourceLanguage)
        }

        response = await fetch(`${API_BASE}/jobs/upload`, {
          method: 'POST',
          body: formData,
        })
      } else {
        const payload: {
          video_url: string
          target_language: string
          source_language?: string
        } = {
          video_url: videoUrl.trim(),
          target_language: targetLanguage,
        }

        if (sourceLanguage !== 'auto') {
          payload.source_language = sourceLanguage
        }

        response = await fetch(`${API_BASE}/jobs`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify(payload),
        })
      }

      const data: unknown = await response.json().catch(() => null)

      const result =
        data && typeof data === 'object'
          ? (data as {
              job_id?: unknown
              status?: unknown
              message?: unknown
              detail?: unknown
            })
          : null

      if (!response.ok) {
        const detail = result?.detail

        const message =
          typeof detail === 'string'
            ? detail
            : Array.isArray(detail)
              ? detail
                  .map((item: { msg?: string }) =>
                    item.msg ?? 'Invalid request',
                  )
                  .join('; ')
              : 'The backend could not create your dubbing job.'

        throw new Error(message)
      }

      if (
        !result ||
        typeof result.job_id !== 'string' ||
        typeof result.status !== 'string'
      ) {
        throw new Error(
          'The backend response is missing the job ID or status.',
        )
      }

      const job: CreatedJob = {
        job_id: result.job_id,
        status: result.status,
        message:
          typeof result.message === 'string'
            ? result.message
            : 'Your dubbing job has been accepted.',
      }

      setCreatedJob(job)
      setNotice(
        selectedFile
          ? 'Your video was uploaded and the dubbing job was submitted.'
          : 'Your dubbing job was submitted successfully.',
      )

      const newProject: ProjectJob = {
        job_id: job.job_id,
        status: job.status as JobStatus,
        progress: job.status === 'completed' ? 100 : 0,
        message: job.message,
      }

      setProjects((current) => [
        newProject,
        ...current.filter(
          (project) => project.job_id !== newProject.job_id,
        ),
      ])

      setSelectedFile(null)
      setVideoUrl('')

      if (fileInput.current) {
        fileInput.current.value = ''
      }

      void loadProjects()
    } catch (err) {
      const message =
        err instanceof Error
          ? err.message
          : 'An unexpected error occurred.'

      if (message.includes('Failed to fetch')) {
        setError(
          'Could not reach the backend. Check that FastAPI is running and CORS allows this frontend origin.',
        )
      } else {
        setError(message)
      }
    } finally {
      setSubmitting(false)
    }
  }

  const resetForm = () => {
    setVideoUrl('')
    setSelectedFile(null)
    setSourceLanguage('auto')
    setTargetLanguage('hi')
    setError('')
    setNotice('')
    setCreatedJob(null)
    setDragging(false)

    if (fileInput.current) {
      fileInput.current.value = ''
    }
  }

  const performProjectAction = async (
    job: ProjectJob,
    action: 'retry' | 'cancel',
  ) => {
    if (projectAction) return

    setProjectAction(`${action}:${job.job_id}`)
    setProjectsError('')
    setNotice('')

    try {
      const response = await fetch(
        `${API_BASE}/jobs/${encodeURIComponent(job.job_id)}/${action}`,
        { method: 'POST' },
      )

      const data: unknown = await response.json().catch(() => null)

      const result =
        data && typeof data === 'object'
          ? (data as { detail?: unknown; message?: unknown })
          : null

      if (!response.ok) {
        const detail =
          typeof result?.detail === 'string'
            ? result.detail
            : `Could not ${action} this job.`

        throw new Error(detail)
      }

      await loadProjects()

      setNotice(
        action === 'retry'
          ? 'The job retry request was accepted.'
          : 'The cancellation request was accepted.',
      )
    } catch (err) {
      setNotice('')
      setProjectsError(
        err instanceof Error
          ? err.message
          : `Could not ${action} this job.`,
      )
    } finally {
      setProjectAction(null)
    }
  }

  const navigateTo = (page: Page) => {
    setActivePage(page)
    setProjectsError('')
  }

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <a
          className="brand"
          href="#create"
          aria-label="Dubly home"
          onClick={() => navigateTo('create')}
        >
          <span className="brand-icon">
            d<span>.</span>
          </span>
          <span className="brand-name">
            dubly<span>studio</span>
          </span>
        </a>

        <div className="workspace-label">WORKSPACE</div>

        <nav className="side-nav" aria-label="Main navigation">
          <a
            href="#create"
            className={`nav-item ${activePage === 'create' ? 'active' : ''}`}
            onClick={() => navigateTo('create')}
            aria-current={activePage === 'create' ? 'page' : undefined}
          >
            <span className="nav-icon">✳</span>
            Create dubbing
            <span className="nav-arrow">↗</span>
          </a>

          <a
            href="#recent"
            className={`nav-item ${activePage === 'recent' ? 'active' : ''}`}
            onClick={() => navigateTo('recent')}
            aria-current={activePage === 'recent' ? 'page' : undefined}
          >
            <span className="nav-icon">▤</span>
            My projects
          </a>

          <a
            href="#how-it-works"
            className={`nav-item ${activePage === 'how-it-works' ? 'active' : ''}`}
            onClick={() => navigateTo('how-it-works')}
            aria-current={
              activePage === 'how-it-works' ? 'page' : undefined
            }
          >
            <span className="nav-icon">▷</span>
            How it works
          </a>
        </nav>

        <div className="sidebar-bottom">
          <div className="help-card">
            <div className="help-symbol">✦</div>
            <strong>Your voice, every language.</strong>
            <p>
              Make your videos understandable to everyone, everywhere.
            </p>
          </div>

          <div className="profile">
            <div className="avatar">DS</div>
            <div className="profile-copy">
              <strong>My workspace</strong>
              <span>Personal account</span>
            </div>
            <span className="profile-menu">•••</span>
          </div>
        </div>
      </aside>

      <main className="main-content">
        <header className="topbar">
          <div className="breadcrumb">
            Workspace <span>/</span>{' '}
            <strong>
              {activePage === 'create'
                ? 'Create dubbing'
                : activePage === 'recent'
                  ? 'My projects'
                  : 'How it works'}
            </strong>
          </div>

          <div className="topbar-right">
            <label className="theme-control">
              <span className="theme-control-label">Theme</span>
              <select
                aria-label="Choose appearance theme"
                value={theme}
                onChange={(event) =>
                  setTheme(event.target.value as Theme)
                }
                className="theme-select"
              >
                <option value="system">System</option>
                <option value="light">Light</option>
                <option value="dark">Dark</option>
              </select>
            </label>

            <span className="status-dot" />
            <span className="system-status">Workspace ready</span>
            <div className="top-avatar">DS</div>
          </div>
        </header>

        <div className="page-content">
          {activePage === 'create' && (
            <>
              <section className="welcome" id="create">
                <div className="eyebrow">
                  <span /> AI-POWERED VIDEO TRANSLATION
                </div>

                <h1>
                  Your content.
                  <br />
                  <span>Every language.</span>
                </h1>

                <p className="welcome-copy">
                  Give your videos a global voice. Translate and dub your
                  content with AI, without losing the story.
                </p>

                <div className="benefits">
                  <span><b>✓</b> AI-powered dubbing</span>
                  <span><b>✓</b> Multiple languages</span>
                  <span><b>✓</b> Simple workflow</span>
                </div>
              </section>

              <section className="creator-card">
                <div className="card-heading">
                  <div>
                    <div className="section-kicker">LET'S GET STARTED</div>
                    <h2>Create a new dub</h2>
                    <p>
                      Choose your video and tell us where it needs to go.
                    </p>
                  </div>

                  <div className="step-indicator">
                    <span>01</span> / 03
                  </div>
                </div>

                <form onSubmit={submitJob}>
                  <div className="field-label">
                    <span>01</span>
                    <label>Choose your video</label>
                    <span className="optional-tag">ONE VIDEO</span>
                  </div>

                  <div
                    className={`upload-zone ${dragging ? 'dragging' : ''} ${selectedFile ? 'has-file' : ''}`}
                    onDragOver={(event) => {
                      event.preventDefault()
                      setDragging(true)
                    }}
                    onDragLeave={() => setDragging(false)}
                    onDrop={(event) => {
                      event.preventDefault()
                      setDragging(false)
                      chooseFile(event.dataTransfer.files[0])
                    }}
                  >
                    <input
                      ref={fileInput}
                      type="file"
                      accept="video/*"
                      hidden
                      onChange={(event) =>
                        chooseFile(event.target.files?.[0])
                      }
                    />

                    <div className="upload-icon">
                      {selectedFile ? '✓' : <span>↑</span>}
                    </div>

                    <div className="upload-title">
                      {selectedFile
                        ? selectedFile.name
                        : 'Drop your video here'}
                    </div>

                    <p className="upload-subtitle">
                      {selectedFile
                        ? `${(selectedFile.size / (1024 * 1024)).toFixed(1)} MB · Selected locally`
                        : 'or browse files from your computer'}
                    </p>

                    <button
                      type="button"
                      className="browse-button"
                      onClick={() => fileInput.current?.click()}
                    >
                      {selectedFile ? 'Choose another file' : 'Browse files'}
                    </button>

                    <div className="upload-footnote">
                      Video files · Maximum 500 MB
                    </div>
                  </div>

                  <div className="or-divider">
                    <span>OR USE A VIDEO LINK</span>
                  </div>

                  <label className="input-label" htmlFor="video-url">
                    YouTube or direct video URL
                  </label>

                  <div className="url-input-wrap">
                    <span className="link-icon">↗</span>

                    <input
                      id="video-url"
                      type="url"
                      placeholder="https://www.youtube.com/watch?v=..."
                      value={videoUrl}
                      onChange={(event) => {
                        setVideoUrl(event.target.value)

                        if (event.target.value) {
                          setSelectedFile(null)

                          if (fileInput.current) {
                            fileInput.current.value = ''
                          }
                        }

                        setError('')
                        setNotice('')
                        setCreatedJob(null)
                      }}
                    />

                    {videoUrl && (
                      <button
                        type="button"
                        className="clear-url"
                        onClick={() => {
                          setVideoUrl('')
                          setError('')
                          setNotice('')
                          setCreatedJob(null)
                        }}
                        aria-label="Clear URL"
                      >
                        ×
                      </button>
                    )}
                  </div>

                  <div className="language-section">
                    <div className="field-label">
                      <span>02</span>
                      <label>Set your languages</label>
                    </div>

                    <div className="language-grid">
                      <div className="language-field">
                        <label htmlFor="source-language">FROM</label>

                        <div className="select-wrap">
                          <span className="language-icon">◎</span>

                          <select
                            id="source-language"
                            value={sourceLanguage}
                            onChange={(event) => {
                              setSourceLanguage(event.target.value)
                              setError('')
                              setNotice('')
                              setCreatedJob(null)
                            }}
                          >
                            <option value="auto">Auto-detect language</option>
                            {languages.map((language) => (
                              <option
                                key={language.code}
                                value={language.code}
                              >
                                {language.name}
                              </option>
                            ))}
                          </select>

                          <span className="select-chevron">⌄</span>
                        </div>
                      </div>

                      <div className="language-connector">→</div>

                      <div className="language-field">
                        <label htmlFor="target-language">DUB INTO</label>

                        <div className="select-wrap target-select">
                          <span className="language-icon">文</span>

                          <select
                            id="target-language"
                            value={targetLanguage}
                            onChange={(event) => {
                              setTargetLanguage(event.target.value)
                              setError('')
                              setNotice('')
                              setCreatedJob(null)
                            }}
                          >
                            {languages.map((language) => (
                              <option
                                key={language.code}
                                value={language.code}
                              >
                                {language.name}
                              </option>
                            ))}
                          </select>

                          <span className="select-chevron">⌄</span>
                        </div>
                      </div>
                    </div>

                    <p className="language-note">
                      <span>✦</span> Not sure about the original language?
                      Let AI detect it for you.
                    </p>
                  </div>

                  {error && (
                    <div className="feedback error-message" role="alert">
                      {error}
                    </div>
                  )}

                  {notice && (
                    <div className="feedback success-message" role="status">
                      {notice}
                    </div>
                  )}

                  {createdJob && (
                    <div className="feedback success-message" role="status">
                      <strong>Dubbing job: {createdJob.status}</strong>
                      <p>{createdJob.message}</p>
                      <p>
                        Job ID: <code>{createdJob.job_id}</code>
                      </p>
                      <button
                        type="button"
                        className="project-action-button"
                        onClick={() => navigateTo('recent')}
                      >
                        View My Projects →
                      </button>
                    </div>
                  )}

                  <div className="form-footer">
                    <div className="privacy-note">
                      <span>♧</span> Your content stays yours.
                    </div>

                    <div className="form-actions">
                      <button
                        type="button"
                        className="reset-button"
                        onClick={resetForm}
                        disabled={submitting}
                      >
                        Reset
                      </button>

                      <button
                        type="submit"
                        className="submit-button"
                        disabled={submitting}
                      >
                        {submitting ? 'Submitting...' : 'Continue'}{' '}
                        <span>→</span>
                      </button>
                    </div>
                  </div>
                </form>
              </section>
            </>
          )}

          {activePage === 'recent' && (
            <section className="recent-section" id="recent">
              <div className="recent-heading">
                <div>
                  <div className="section-kicker">YOUR WORKSPACE</div>
                  <h2>My projects</h2>
                </div>

                <button
                  type="button"
                  className="coming-soon"
                  onClick={() => void loadProjects(true)}
                  disabled={refreshingProjects}
                >
                  {refreshingProjects ? 'REFRESHING…' : '↻ REFRESH'}
                </button>
              </div>

              {projectsError && (
                <div className="feedback error-message" role="alert">
                  {projectsError}
                  <p>
                    Check that FastAPI is running and the jobs list endpoint
                    is available.
                  </p>
                </div>
              )}

              {notice && (
                <div className="feedback success-message" role="status">
                  {notice}
                </div>
              )}

              {loadingProjects ? (
                <div className="empty-projects">
                  <div className="empty-icon">◌</div>
                  <strong>Loading your projects…</strong>
                  <p>Fetching your latest dubbing jobs.</p>
                </div>
              ) : projects.length === 0 ? (
                <div className="empty-projects">
                  <div className="empty-icon">▤</div>
                  <strong>No projects yet</strong>
                  <p>
                    Submit a video from Create Dubbing. Your jobs will appear
                    here.
                  </p>
                  <button
                    type="button"
                    className="project-action-button"
                    onClick={() => navigateTo('create')}
                  >
                    Create a dub →
                  </button>
                </div>
              ) : (
                <div className="project-list">
                  {projects.map((job) => {
                    const progress = getProgress(job)
                    const busy =
                      projectAction?.endsWith(job.job_id) ?? false
                    const qualityReport = qualityReports[job.job_id]

                    return (
                      <article className="project-card" key={job.job_id}>
                        <div className="project-card-heading">
                          <div className="project-icon">▤</div>

                          <div className="project-main">
                            <strong>
                              Dubbing job · {job.job_id.slice(0, 8)}
                            </strong>
                            <span>
                              {job.created_at
                                ? new Date(job.created_at).toLocaleString()
                                : 'Date unavailable'}
                            </span>
                          </div>

                          <span
                            className={`project-status status-${job.status}`}
                          >
                            {getStatusLabel(job.status)}
                          </span>
                        </div>

                        <p className="project-message">
                          {job.message || 'No additional details.'}
                        </p>

                        <div
                          className="progress-track"
                          role="progressbar"
                          aria-label={`Job progress: ${progress}%`}
                          aria-valuemin={0}
                          aria-valuemax={100}
                          aria-valuenow={progress}
                        >
                          <div
                            className={`progress-fill progress-${job.status}`}
                            style={{ width: `${progress}%` }}
                          />
                        </div>

                        <div className="project-progress-caption">
                          <span>
                            {job.status === 'queued'
                              ? 'Waiting in the queue'
                              : job.status === 'processing'
                                ? 'Dubbing in progress'
                                : job.status === 'completed'
                                  ? 'Your dubbed video is ready'
                                  : job.status === 'failed'
                                    ? 'Dubbing failed — retry available'
                                    : job.status === 'cancelled'
                                      ? 'Job cancelled'
                                      : getStatusLabel(job.status)}
                          </span>
                          <span>{progress}%</span>
                        </div>

                        <div className="project-actions">
                          {job.status === 'completed' && (
                            <>
                              <a
                                className="project-action-button"
                                href={`${API_BASE}/jobs/${encodeURIComponent(job.job_id)}/download`}
                              >
                                Download video ↓
                              </a>

                              <button
                                type="button"
                                className="project-action-button"
                                disabled={
                                  loadingQualityReport === job.job_id
                                }
                                onClick={() => {
                                  if (qualityReports[job.job_id]) {
                                    setQualityReports((current) => {
                                      const next = { ...current }
                                      delete next[job.job_id]
                                      return next
                                    })
                                  } else {
                                    void loadQualityReport(job.job_id)
                                  }
                                }}
                              >
                                {loadingQualityReport === job.job_id
                                  ? 'Loading report…'
                                  : qualityReport
                                    ? 'Hide quality report'
                                    : 'View quality report'}
                              </button>
                            </>
                          )}

                          {job.status === 'failed' && (
                            <button
                              type="button"
                              className="project-action-button"
                              disabled={Boolean(projectAction)}
                              onClick={() =>
                                void performProjectAction(job, 'retry')
                              }
                            >
                              {busy ? 'Retrying…' : 'Retry job ↻'}
                            </button>
                          )}

                          {job.status === 'queued' && (
                            <button
                              type="button"
                              className="project-action-button"
                              disabled={Boolean(projectAction)}
                              onClick={() => {
                                const confirmed = window.confirm(
                                  'Are you sure you want to cancel this queued job? This action cannot be undone.',
                                )

                                if (confirmed) {
                                  void performProjectAction(job, 'cancel')
                                }
                              }}
                            >
                              {busy ? 'Cancelling…' : 'Cancel job ×'}
                            </button>
                          )}

                          {job.processing_time_seconds != null && (
                            <span className="project-duration">
                              Processing time:{' '}
                              {job.processing_time_seconds.toFixed(1)} s
                            </span>
                          )}
                        </div>

                        {qualityReportErrors[job.job_id] && (
                          <p role="alert" className="project-report-error">
                            {qualityReportErrors[job.job_id]}
                          </p>
                        )}

                        {qualityReport && (
                          <section
                            className="quality-report"
                            aria-label="Dubbing quality report"
                          >
                            <h4>Quality inspection</h4>

                            <p>
                              Overall status:{' '}
                              <strong>
                                {(
                                  qualityReport.overall_status ?? 'unknown'
                                ).replaceAll('_', ' ')}
                              </strong>
                            </p>

                            {qualityReport.checks?.map((check, index) => {
                              const checkLabel =
                                check.label ?? check.name ?? check.id ?? 'Quality check'
                              const checkSummary =
                                check.summary ?? check.message ?? check.details

                              return (
                                <div
                                  className="quality-report-check"
                                  key={`${check.id ?? check.name ?? check.label ?? 'check'}-${index}`}
                                >
                                  <strong>{checkLabel.replaceAll('_', ' ')}</strong>

                                  <span>{check.status ?? 'unknown'}</span>

                                  {checkSummary && <p>{checkSummary}</p>}
                                </div>
                              )
                            })}

                            {qualityReport.metrics && (
                              <>
                                <h5>Metrics</h5>
                                <ul>
                                  {Object.entries(
                                    qualityReport.metrics,
                                  ).map(([key, value]) => (
                                    <li key={key}>
                                      {key.replaceAll('_', ' ')}:{' '}
                                      {String(value)}
                                    </li>
                                  ))}
                                </ul>
                              </>
                            )}

                            {(qualityReport.warnings?.length ?? 0) > 0 && (
                              <>
                                <h5>Warnings</h5>
                                <ul>
                                  {qualityReport.warnings?.map(
                                    (warning, index) => (
                                      <li key={`${index}-${warning}`}>
                                        {warning}
                                      </li>
                                    ),
                                  )}
                                </ul>
                              </>
                            )}

                            {qualityReport.note && (
                              <p>{qualityReport.note}</p>
                            )}
                          </section>
                        )}

                        <details className="project-details">
                          <summary>View job ID</summary>
                          <code>{job.job_id}</code>
                        </details>
                      </article>
                    )
                  })}
                </div>
              )}
            </section>
          )}

          {activePage === 'how-it-works' && (
            <section className="bottom-info" id="how-it-works">
              <div className="info-heading">
                <span className="info-sparkle">✳</span>
                <div>
                  <strong>Made for creators, built for the world.</strong>
                  <p>
                    A simple workflow to help your videos travel further.
                  </p>
                </div>
              </div>

              <div className="workflow">
                <div className="workflow-item">
                  <span>01</span>
                  <div>
                    <strong>Choose</strong>
                    <p>Add your video URL</p>
                  </div>
                </div>

                <div className="workflow-line" />

                <div className="workflow-item">
                  <span>02</span>
                  <div>
                    <strong>Translate</strong>
                    <p>Select the target language</p>
                  </div>
                </div>

                <div className="workflow-line" />

                <div className="workflow-item">
                  <span>03</span>
                  <div>
                    <strong>Dub & export</strong>
                    <p>Track the job and get your video</p>
                  </div>
                </div>
              </div>

              <button
                type="button"
                className="submit-button"
                onClick={() => navigateTo('create')}
              >
                Create your first dub <span>→</span>
              </button>
            </section>
          )}

          <footer className="page-footer">
            <span>
              dubly studio <span className="footer-dot">·</span> AI video
              dubbing
            </span>
            <span>Built to help stories travel.</span>
          </footer>
        </div>
      </main>
    </div>
  )
}

export default App