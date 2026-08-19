import { describe, it, expect } from 'vitest'
import {
  AUDIO_UPLOAD_ROLES,
  GENERATE_ROLES,
  REVIEWER_ROLES,
  SEND_OUTPUT_ROLES,
} from './roles'

// Cross-checks against app/core/permissions.py's ROLE_PERMISSIONS
// (Sprint 8/10) for the four permissions this frontend conditionally
// gates on — see that file for the authoritative source. A drift here
// means the frontend and backend disagree about which roles see which
// buttons, which is exactly the class of bug Deliverable 7 exists to
// prevent (a button that's shown but always 403s, or hidden but should
// work).

describe('role sets match app/core/permissions.py', () => {
  it('REVIEWER_ROLES: DAILY_LOG_APPROVE / DAILY_LOG_REJECT', () => {
    expect([...REVIEWER_ROLES].sort()).toEqual(
      ['admin', 'owner', 'project_manager', 'system_admin'].sort(),
    )
  })

  it('GENERATE_ROLES: DAILY_LOG_GENERATE', () => {
    expect([...GENERATE_ROLES].sort()).toEqual(
      ['admin', 'owner', 'project_manager', 'system_admin'].sort(),
    )
  })

  it('SEND_OUTPUT_ROLES: DAILY_LOG_SEND_OUTPUT', () => {
    expect([...SEND_OUTPUT_ROLES].sort()).toEqual(
      ['admin', 'owner', 'project_manager', 'system_admin'].sort(),
    )
  })

  it('AUDIO_UPLOAD_ROLES: AUDIO_UPLOAD (includes foreman, unlike the other three)', () => {
    expect([...AUDIO_UPLOAD_ROLES].sort()).toEqual(
      ['admin', 'foreman', 'owner', 'project_manager', 'system_admin'].sort(),
    )
  })

  it('client and safety_officer are excluded from every gated action', () => {
    for (const roleSet of [REVIEWER_ROLES, GENERATE_ROLES, SEND_OUTPUT_ROLES, AUDIO_UPLOAD_ROLES]) {
      expect(roleSet.has('client')).toBe(false)
      expect(roleSet.has('safety_officer')).toBe(false)
    }
  })
})
