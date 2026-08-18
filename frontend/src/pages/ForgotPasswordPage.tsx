import { useState, type FormEvent } from 'react'
import { Link } from 'react-router-dom'
import { forgotPassword } from '../api/endpoints'
import { extractErrorMessage } from '../api/client'

export function ForgotPasswordPage() {
  const [email, setEmail] = useState('')
  const [submitted, setSubmitted] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [isSubmitting, setIsSubmitting] = useState(false)

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    setError(null)
    setIsSubmitting(true)
    try {
      await forgotPassword(email)
      // Always shown regardless of whether the email exists — matches the
      // backend's own account-enumeration-avoidance design
      // (AuthService.forgot_password()'s docstring): the frontend must not
      // add a distinguishing signal the backend deliberately omits.
      setSubmitted(true)
    } catch (err) {
      setError(extractErrorMessage(err))
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <div className="auth-page">
      <div className="auth-card">
        <h1>Reset your password</h1>
        {submitted ? (
          <>
            <p className="auth-subtitle">
              If that email is registered, a reset link has been sent. Check your inbox.
            </p>
            <Link to="/login" className="auth-link">
              Back to sign in
            </Link>
          </>
        ) : (
          <form onSubmit={(e) => void handleSubmit(e)}>
            <p className="auth-subtitle">
              Enter your email and we'll send you a link to reset your password.
            </p>
            {error && (
              <div className="alert alert-error" role="alert">
                {error}
              </div>
            )}
            <label htmlFor="email">Email</label>
            <input
              id="email"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
              autoFocus
            />
            <button type="submit" className="btn-primary" disabled={isSubmitting}>
              {isSubmitting ? 'Sending…' : 'Send reset link'}
            </button>
            <Link to="/login" className="auth-link">
              Back to sign in
            </Link>
          </form>
        )}
      </div>
    </div>
  )
}
