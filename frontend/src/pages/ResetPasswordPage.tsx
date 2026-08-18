import { useState, type FormEvent } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { resetPassword } from '../api/endpoints'
import { extractErrorMessage } from '../api/client'

// The link app/services/auth_service.py's forgot_password() emails is
// `${frontend_password_reset_url}?token=${raw_token}` — this route (see
// App.tsx: /reset-password) is exactly that URL's path, and `token` here
// is that same query param name.
export function ResetPasswordPage() {
  const [searchParams] = useSearchParams()
  const navigate = useNavigate()
  const token = searchParams.get('token') ?? ''
  const [newPassword, setNewPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [succeeded, setSucceeded] = useState(false)

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    setError(null)
    if (newPassword !== confirmPassword) {
      setError('Passwords do not match.')
      return
    }
    setIsSubmitting(true)
    try {
      await resetPassword(token, newPassword)
      setSucceeded(true)
      setTimeout(() => navigate('/login', { replace: true }), 2000)
    } catch (err) {
      setError(extractErrorMessage(err))
    } finally {
      setIsSubmitting(false)
    }
  }

  if (!token) {
    return (
      <div className="auth-page">
        <div className="auth-card">
          <h1>Invalid reset link</h1>
          <p className="auth-subtitle">This link is missing its reset token.</p>
          <Link to="/forgot-password" className="auth-link">
            Request a new link
          </Link>
        </div>
      </div>
    )
  }

  return (
    <div className="auth-page">
      <div className="auth-card">
        <h1>Choose a new password</h1>
        {succeeded ? (
          <p className="auth-subtitle">
            Password updated. Every other session was signed out. Redirecting to sign in…
          </p>
        ) : (
          <form onSubmit={(e) => void handleSubmit(e)}>
            {error && (
              <div className="alert alert-error" role="alert">
                {error}
              </div>
            )}
            <label htmlFor="new_password">New password</label>
            <input
              id="new_password"
              type="password"
              value={newPassword}
              onChange={(e) => setNewPassword(e.target.value)}
              minLength={8}
              required
              autoFocus
            />
            <label htmlFor="confirm_password">Confirm new password</label>
            <input
              id="confirm_password"
              type="password"
              value={confirmPassword}
              onChange={(e) => setConfirmPassword(e.target.value)}
              minLength={8}
              required
            />
            <button type="submit" className="btn-primary" disabled={isSubmitting}>
              {isSubmitting ? 'Updating…' : 'Update password'}
            </button>
          </form>
        )}
      </div>
    </div>
  )
}
