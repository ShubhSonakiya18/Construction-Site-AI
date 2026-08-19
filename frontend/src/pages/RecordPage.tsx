import { useEffect, useRef, useState, type ChangeEvent, type DragEvent } from 'react'
import { Link } from 'react-router-dom'
import { getAudioStatus, uploadAudio } from '../api/endpoints'
import { extractErrorMessage } from '../api/client'
import { useAuth } from '../auth/AuthContext'
import { AUDIO_UPLOAD_ROLES } from '../auth/roles'
import type { AudioStatusResponseData } from '../api/types'

// Mirrors app/api/v1/audio.py's _ALLOWED_EXTENSIONS — kept here only to
// give the <input accept> attribute a hint and to reject an obviously
// wrong file before spending an upload round-trip; the backend's own
// check is still what actually enforces this.
const ACCEPTED_AUDIO_EXTENSIONS = ['.wav', '.mp3', '.m4a', '.flac', '.ogg', '.webm', '.mp4']

const PROJECT_ID_STORAGE_KEY = 'csa_active_project_id'

const STATUS_STEPS: AudioStatusResponseData['processing_status'][] = [
  'pending',
  'transcribing',
  'extracting',
  'generating',
  'complete',
]

const STATUS_LABELS: Record<string, string> = {
  pending: 'Queued',
  transcribing: 'Transcribing audio',
  extracting: 'Extracting daily log data',
  generating: 'Generating documents',
  complete: 'Complete',
  failed: 'Failed',
}

type RecorderState = 'idle' | 'recording' | 'recorded'

export function RecordPage() {
  const { user } = useAuth()
  // The AppLayout nav hides the /record link for roles without
  // Permission.AUDIO_UPLOAD, but a direct URL visit would still reach
  // this component — this guard is the second half of that gating
  // (Sprint 10, Deliverable 7), not the real authorization boundary,
  // which is still the backend's 403 on POST /audio/upload regardless.
  const canRecord = AUDIO_UPLOAD_ROLES.has(user?.role ?? '')

  const [recorderState, setRecorderState] = useState<RecorderState>('idle')
  const [isDragActive, setIsDragActive] = useState(false)
  // Holds the file that will actually be uploaded, regardless of whether
  // it came from the microphone (wrapped into a File once recording
  // stops) or a file picker (used as-is, keeping its real name/extension
  // instead of being renamed to "recording.webm") — handleUpload() below
  // no longer needs to know which source it came from.
  const [audioFile, setAudioFile] = useState<File | null>(null)
  const [audioUrl, setAudioUrl] = useState<string | null>(null)
  const [elapsedSeconds, setElapsedSeconds] = useState(0)
  const [micError, setMicError] = useState<string | null>(null)
  const [fileError, setFileError] = useState<string | null>(null)

  const [uploadedId, setUploadedId] = useState<string | null>(null)
  const [status, setStatus] = useState<AudioStatusResponseData | null>(null)
  const [uploadError, setUploadError] = useState<string | null>(null)
  const [isUploading, setIsUploading] = useState(false)

  const mediaRecorderRef = useRef<MediaRecorder | null>(null)
  const chunksRef = useRef<Blob[]>([])
  const streamRef = useRef<MediaStream | null>(null)
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null)

  const projectId = localStorage.getItem(PROJECT_ID_STORAGE_KEY) ?? ''

  useEffect(() => {
    return () => {
      // Stop any live mic stream on unmount — a page navigation must not
      // leave the browser's recording indicator active in the background.
      streamRef.current?.getTracks().forEach((t) => t.stop())
      if (timerRef.current) clearInterval(timerRef.current)
      if (audioUrl) URL.revokeObjectURL(audioUrl)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // Poll GET /audio/{id}/status until the pipeline finishes — matches
  // exactly what app/api/v1/audio.py's own docstring says the client is
  // expected to do (no WebSocket/SSE push channel exists in this backend).
  useEffect(() => {
    if (!uploadedId) return
    if (status && (status.processing_status === 'complete' || status.processing_status === 'failed')) {
      return
    }
    const interval = setInterval(() => {
      getAudioStatus(uploadedId)
        .then(setStatus)
        .catch(() => {
          /* transient poll failure — next tick retries; don't surface a
             flickering error for a single missed poll */
        })
    }, 2000)
    return () => clearInterval(interval)
  }, [uploadedId, status])

  async function startRecording() {
    setMicError(null)
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      streamRef.current = stream
      chunksRef.current = []
      const recorder = new MediaRecorder(stream)
      recorder.ondataavailable = (e) => {
        if (e.data.size > 0) chunksRef.current.push(e.data)
      }
      recorder.onstop = () => {
        const blob = new Blob(chunksRef.current, { type: recorder.mimeType || 'audio/webm' })
        const extension = blob.type.includes('webm') ? 'webm' : 'wav'
        const file = new File([blob], `recording.${extension}`, { type: blob.type })
        setAudioFile(file)
        setAudioUrl(URL.createObjectURL(blob))
        stream.getTracks().forEach((t) => t.stop())
      }
      mediaRecorderRef.current = recorder
      recorder.start()
      setRecorderState('recording')
      setElapsedSeconds(0)
      timerRef.current = setInterval(() => setElapsedSeconds((s) => s + 1), 1000)
    } catch {
      setMicError(
        'Could not access the microphone. Check browser permissions and that a microphone is connected.',
      )
    }
  }

  function stopRecording() {
    mediaRecorderRef.current?.stop()
    if (timerRef.current) clearInterval(timerRef.current)
    setRecorderState('recorded')
  }

  function discardRecording() {
    if (audioUrl) URL.revokeObjectURL(audioUrl)
    setAudioFile(null)
    setAudioUrl(null)
    setRecorderState('idle')
    setElapsedSeconds(0)
  }

  function acceptFile(file: File) {
    setFileError(null)
    const extension = file.name.slice(file.name.lastIndexOf('.')).toLowerCase()
    if (!ACCEPTED_AUDIO_EXTENSIONS.includes(extension)) {
      setFileError(
        `Unsupported file type "${extension || '(none)'}". Accepted: ${ACCEPTED_AUDIO_EXTENSIONS.join(', ')}.`,
      )
      return
    }

    if (audioUrl) URL.revokeObjectURL(audioUrl)
    setAudioFile(file)
    setAudioUrl(URL.createObjectURL(file))
    setRecorderState('recorded')
  }

  function handleFileSelected(e: ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]
    e.target.value = '' // allow re-selecting the same file later
    if (!file) return
    acceptFile(file)
  }

  function handleDragOver(e: DragEvent<HTMLDivElement>) {
    e.preventDefault()
    setIsDragActive(true)
  }

  function handleDragLeave(e: DragEvent<HTMLDivElement>) {
    e.preventDefault()
    setIsDragActive(false)
  }

  function handleDrop(e: DragEvent<HTMLDivElement>) {
    e.preventDefault()
    setIsDragActive(false)
    const file = e.dataTransfer.files?.[0]
    if (!file) return
    acceptFile(file)
  }

  async function handleUpload() {
    if (!audioFile) return
    setIsUploading(true)
    setUploadError(null)
    try {
      const result = await uploadAudio(audioFile, projectId || undefined)
      setUploadedId(result.id)
      setStatus({
        id: result.id,
        original_filename: result.original_filename,
        processing_status: 'pending',
        is_valid: null,
        validation_errors: null,
        duration_seconds: null,
        daily_log_id: null,
        error_message: null,
      })
    } catch (err) {
      setUploadError(extractErrorMessage(err))
    } finally {
      setIsUploading(false)
    }
  }

  const currentStepIndex = status ? STATUS_STEPS.indexOf(status.processing_status) : -1

  if (!canRecord) {
    return (
      <div className="card">
        <h1>Record a site update</h1>
        <p className="hint">
          Your role does not have permission to upload recordings.{' '}
          <Link to="/">Back to Dashboard</Link>.
        </p>
      </div>
    )
  }

  return (
    <div className="record-page">
      <div className="card">
        <h1>Record a site update</h1>
        {!projectId && (
          <p className="hint">
            No active project set — go to the{' '}
            <Link to="/">Dashboard</Link> and load a project first if this recording should be
            linked to one. You can still record and upload without one.
          </p>
        )}

        {micError && <div className="alert alert-error">{micError}</div>}
        {fileError && <div className="alert alert-error">{fileError}</div>}

        {recorderState === 'idle' && (
          <div
            className={`record-dropzone${isDragActive ? ' record-dropzone-active' : ''}`}
            onDragOver={handleDragOver}
            onDragLeave={handleDragLeave}
            onDrop={handleDrop}
          >
            <div className="record-idle-options">
              <button type="button" className="btn-primary btn-record" onClick={() => void startRecording()}>
                ● Start Recording
              </button>
              <span className="record-or">or</span>
              <label className="btn-secondary btn-file-upload">
                Upload a recording
                <input
                  type="file"
                  accept={ACCEPTED_AUDIO_EXTENSIONS.join(',')}
                  onChange={handleFileSelected}
                  hidden
                />
              </label>
            </div>
            <p className="record-dropzone-hint">or drag and drop an audio file here</p>
          </div>
        )}

        {recorderState === 'recording' && (
          <div className="recording-active">
            <div className="recording-indicator">
              <span className="recording-dot" /> Recording — {elapsedSeconds}s
            </div>
            <button type="button" className="btn-danger" onClick={stopRecording}>
              ■ Stop
            </button>
          </div>
        )}

        {recorderState === 'recorded' && audioUrl && (
          <div className="recording-review">
            <audio controls src={audioUrl} />
            <div className="review-actions">
              <button type="button" className="btn-secondary" onClick={discardRecording}>
                Discard & start over
              </button>
              <button
                type="button"
                className="btn-primary"
                disabled={isUploading}
                onClick={() => void handleUpload()}
              >
                {isUploading ? 'Uploading…' : 'Upload & Process'}
              </button>
            </div>
            {uploadError && <div className="alert alert-error">{uploadError}</div>}
          </div>
        )}
      </div>

      {status && (
        <div className="card">
          <h2>Processing status</h2>
          {status.processing_status === 'failed' ? (
            <div className="alert alert-error">
              Processing failed: {status.error_message ?? 'Unknown error.'}
              {status.validation_errors && status.validation_errors.length > 0 && (
                <ul>
                  {status.validation_errors.map((e, i) => (
                    <li key={i}>{e}</li>
                  ))}
                </ul>
              )}
            </div>
          ) : (
            <ol className="status-steps">
              {STATUS_STEPS.map((step, i) => (
                <li
                  key={step}
                  className={
                    i < currentStepIndex
                      ? 'step-done'
                      : i === currentStepIndex
                        ? 'step-active'
                        : 'step-pending'
                  }
                >
                  {STATUS_LABELS[step]}
                </li>
              ))}
            </ol>
          )}

          {status.processing_status === 'complete' && status.daily_log_id && (
            <Link to={`/logs/${status.daily_log_id}`} className="btn-primary">
              View the generated daily log
            </Link>
          )}
        </div>
      )}
    </div>
  )
}
