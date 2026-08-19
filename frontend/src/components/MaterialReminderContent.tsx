// Sprint 10, Deliverable 5: renders a material_reminder document's
// priority sections visually distinguished, per docs/NEXT_SPRINT.md ("the
// generated Markdown already includes priority levels... no new data
// needed, just render what's already there prominently").
//
// generation/prompts/material_reminder.md's REQUIRED SECTIONS are fixed
// ## headers naming each priority level exactly:
//   ## CRITICAL — Order Immediately
//   ## HIGH PRIORITY — Order Today (needed within 48 hours)
//   ## MEDIUM PRIORITY — Order This Week
//   ## LOW PRIORITY — Plan Ahead
//   ## Delivery Notes
// This is a small, purpose-built parser for exactly that fixed shape —
// not a general Markdown renderer — matching the same "hand-roll a
// parser for the shape we actually produce" choice
// app/services/pdf_export.py's module docstring explains for the PDF
// export feature.

interface PrioritySection {
  level: 'CRITICAL' | 'HIGH' | 'MEDIUM' | 'LOW' | 'OTHER'
  heading: string
  lines: string[]
}

const PRIORITY_BADGE_CLASS: Record<PrioritySection['level'], string> = {
  CRITICAL: 'badge-rejected', // red — matches the existing "rejected" badge color
  HIGH: 'badge-under_review', // amber
  MEDIUM: 'badge-under_review',
  LOW: 'badge-draft', // neutral gray
  OTHER: 'badge-draft',
}

function classifyHeading(heading: string): PrioritySection['level'] {
  const upper = heading.toUpperCase()
  if (upper.startsWith('CRITICAL')) return 'CRITICAL'
  if (upper.startsWith('HIGH')) return 'HIGH'
  if (upper.startsWith('MEDIUM')) return 'MEDIUM'
  if (upper.startsWith('LOW')) return 'LOW'
  return 'OTHER'
}

function parseSections(content: string): PrioritySection[] {
  const sections: PrioritySection[] = []
  let current: PrioritySection | null = null

  for (const rawLine of content.split('\n')) {
    const line = rawLine.trimEnd()
    if (line.startsWith('## ')) {
      const heading = line.slice(3).trim()
      current = { level: classifyHeading(heading), heading, lines: [] }
      sections.push(current)
    } else if (current && line.trim()) {
      current.lines.push(line.replace(/\*\*(.+?)\*\*/g, '$1').trim())
    }
  }
  return sections
}

export function MaterialReminderContent({ content }: { content: string }) {
  const sections = parseSections(content)

  // Fall back to the plain rendering DocumentsPanel already uses for
  // every other document type if this content doesn't actually match
  // the expected shape (e.g. a validation-failed output whose content
  // is an error string, not real sections) — never show an empty panel
  // for content that genuinely exists.
  if (sections.length === 0) {
    return <pre>{content}</pre>
  }

  return (
    <div className="material-reminder">
      {sections.map((section, i) => (
        <div key={i} className="material-reminder-section">
          <div className="material-reminder-heading">
            <span className={`badge ${PRIORITY_BADGE_CLASS[section.level]}`}>
              {section.level === 'OTHER' ? 'INFO' : section.level}
            </span>
            <span>{section.heading}</span>
          </div>
          {section.lines.length > 0 ? (
            <ul>
              {section.lines.map((line, j) => (
                <li key={j}>{line.replace(/^[-•]\s*/, '')}</li>
              ))}
            </ul>
          ) : (
            <p className="hint">None.</p>
          )}
        </div>
      ))}
    </div>
  )
}
