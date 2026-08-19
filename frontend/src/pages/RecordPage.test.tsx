import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { RecordPage } from './RecordPage'
import { AuthProvider } from '../auth/AuthContext'
import * as endpoints from '../api/endpoints'

vi.mock('../api/endpoints', async (importOriginal) => {
  const actual = await importOriginal<typeof endpoints>()
  return { ...actual, uploadAudio: vi.fn(), getAudioStatus: vi.fn() }
})

function renderAsRole(role: string) {
  localStorage.setItem('csa_access_token', 'fake-token')
  localStorage.setItem('csa_refresh_token', 'fake-refresh')
  localStorage.setItem(
    'csa_user',
    JSON.stringify({ userId: 'u1', companyId: 'c1', email: 'a@b.com', role }),
  )
  return render(
    <MemoryRouter>
      <AuthProvider>
        <RecordPage />
      </AuthProvider>
    </MemoryRouter>,
  )
}

beforeEach(() => {
  localStorage.clear()
  vi.mocked(endpoints.uploadAudio).mockReset()
  vi.mocked(endpoints.getAudioStatus).mockReset()
})

function makeAudioFile(name = 'site-note.mp3', type = 'audio/mpeg') {
  return new File(['fake audio bytes'], name, { type })
}

describe('RecordPage — direct-navigation guard (Sprint 10, Deliverable 7)', () => {
  it('shows a permission message instead of the recorder for a client role', async () => {
    renderAsRole('client')
    expect(await screen.findByText(/does not have permission to upload/i)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /start recording/i })).not.toBeInTheDocument()
  })

  it('shows the recorder for a foreman (has AUDIO_UPLOAD)', async () => {
    renderAsRole('foreman')
    expect(await screen.findByRole('button', { name: /start recording/i })).toBeInTheDocument()
  })
})

describe('RecordPage — upload a file instead of recording', () => {
  it('shows an "Upload a recording" option alongside Start Recording', async () => {
    renderAsRole('foreman')
    expect(await screen.findByText(/upload a recording/i)).toBeInTheDocument()
  })

  it('accepting a valid audio file moves straight to the review/upload step', async () => {
    renderAsRole('foreman')
    const user = userEvent.setup()
    const input = document.querySelector('input[type="file"]') as HTMLInputElement
    const file = makeAudioFile('site-note.mp3', 'audio/mpeg')

    await user.upload(input, file)

    expect(await screen.findByRole('button', { name: /upload & process/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /discard & start over/i })).toBeInTheDocument()
    // Start Recording is no longer shown once a file has moved the page
    // into the review state — same as after stopping a live recording.
    expect(screen.queryByRole('button', { name: /start recording/i })).not.toBeInTheDocument()
  })

  it('rejects a file with an unsupported extension before ever uploading', async () => {
    renderAsRole('foreman')
    const input = document.querySelector('input[type="file"]') as HTMLInputElement
    const badFile = new File(['not audio'], 'notes.txt', { type: 'text/plain' })

    // The <input accept> attribute stops user-event's upload() from ever
    // firing onChange for a mismatched file (it mirrors real browser picker
    // filtering) — fireEvent bypasses that to simulate a drag-and-drop or
    // programmatic file delivery that skips the picker dialog entirely.
    fireEvent.change(input, { target: { files: [badFile] } })

    expect(await screen.findByText(/unsupported file type/i)).toBeInTheDocument()
    // Must not have advanced to the review/upload step for a rejected file.
    expect(screen.queryByRole('button', { name: /upload & process/i })).not.toBeInTheDocument()
    expect(endpoints.uploadAudio).not.toHaveBeenCalled()
  })

  it('clicking "Upload & Process" after picking a file calls uploadAudio with that file', async () => {
    vi.mocked(endpoints.uploadAudio).mockResolvedValue({
      id: 'audio-1',
      original_filename: 'site-note.mp3',
      processing_status: 'pending',
      project_id: null,
      created_at: '2026-01-01T00:00:00Z',
    })
    renderAsRole('foreman')
    const user = userEvent.setup()
    const input = document.querySelector('input[type="file"]') as HTMLInputElement
    const file = makeAudioFile()

    await user.upload(input, file)
    await user.click(await screen.findByRole('button', { name: /upload & process/i }))

    await waitFor(() => {
      expect(endpoints.uploadAudio).toHaveBeenCalledTimes(1)
    })
    const [uploadedFile] = vi.mocked(endpoints.uploadAudio).mock.calls[0]
    expect(uploadedFile.name).toBe('site-note.mp3')
  })

  it('dropping a valid audio file onto the dropzone moves straight to the review step', async () => {
    renderAsRole('foreman')
    const dropzone = document.querySelector('.record-dropzone') as HTMLElement
    const file = makeAudioFile()

    fireEvent.drop(dropzone, { dataTransfer: { files: [file] } })

    expect(await screen.findByRole('button', { name: /upload & process/i })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /start recording/i })).not.toBeInTheDocument()
  })

  it('dropping an unsupported file shows the same error as the file picker', async () => {
    renderAsRole('foreman')
    const dropzone = document.querySelector('.record-dropzone') as HTMLElement
    const badFile = new File(['not audio'], 'notes.txt', { type: 'text/plain' })

    fireEvent.drop(dropzone, { dataTransfer: { files: [badFile] } })

    expect(await screen.findByText(/unsupported file type/i)).toBeInTheDocument()
    expect(endpoints.uploadAudio).not.toHaveBeenCalled()
  })

  it('"Discard & start over" returns to the idle state with both options visible again', async () => {
    renderAsRole('foreman')
    const user = userEvent.setup()
    const input = document.querySelector('input[type="file"]') as HTMLInputElement
    await user.upload(input, makeAudioFile())

    await user.click(await screen.findByRole('button', { name: /discard & start over/i }))

    expect(await screen.findByRole('button', { name: /start recording/i })).toBeInTheDocument()
    expect(screen.getByText(/upload a recording/i)).toBeInTheDocument()
  })
})
