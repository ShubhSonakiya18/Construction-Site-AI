import { describe, it, expect, beforeEach } from 'vitest'
import { AxiosError } from 'axios'
import { extractErrorMessage, getAccessToken, setTokens, clearTokens } from './client'

beforeEach(() => {
  localStorage.clear()
})

describe('token storage', () => {
  it('stores and retrieves the access token', () => {
    setTokens('access-1', 'refresh-1')
    expect(getAccessToken()).toBe('access-1')
  })

  it('clears both tokens', () => {
    setTokens('access-1', 'refresh-1')
    clearTokens()
    expect(getAccessToken()).toBeNull()
  })
})

describe('extractErrorMessage', () => {
  it('extracts the envelope message from a failed AxiosError', () => {
    const error = new AxiosError('Request failed')
    error.response = {
      status: 401,
      data: { message: 'Incorrect email or password.' },
      statusText: '',
      headers: {},
      // @ts-expect-error - minimal fake config, not exercised
      config: {},
    }
    expect(extractErrorMessage(error)).toBe('Incorrect email or password.')
  })

  it('returns a specific message for 429', () => {
    const error = new AxiosError('Too many requests')
    error.response = {
      status: 429,
      data: {},
      statusText: '',
      headers: {},
      // @ts-expect-error - minimal fake config, not exercised
      config: {},
    }
    expect(extractErrorMessage(error)).toMatch(/too many attempts/i)
  })

  it('returns a network-error message when there is no response at all', () => {
    const error = new AxiosError('Network Error')
    expect(extractErrorMessage(error)).toMatch(/could not reach the server/i)
  })

  it('falls back to a generic message for a non-axios error', () => {
    expect(extractErrorMessage(new Error('boom'))).toBe('Something went wrong.')
  })
})
