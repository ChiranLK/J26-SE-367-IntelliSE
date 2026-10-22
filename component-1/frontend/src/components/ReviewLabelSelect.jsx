import { useEffect, useId, useRef, useState } from 'react'
import { createPortal } from 'react-dom'

const labelChoices = [
  { value: '', title: 'Clear selection', description: 'Leave this label unselected' },
  { value: 'FR', title: 'Functional', description: 'What the system does' },
  { value: 'NFR', title: 'Non-functional', description: 'Quality, performance or constraints' },
]

function menuPosition(rect) {
  const width = Math.min(Math.max(rect.width, 260), window.innerWidth - 16)
  const height = 210
  return { width, left: Math.max(8, Math.min(rect.left, window.innerWidth - width - 8)),
    top: window.innerHeight - rect.bottom >= height + 12 ? rect.bottom + 7 : Math.max(8, rect.top - height - 7) }
}

export default function ReviewLabelSelect({ value, onChange, disabled, displayId, options = labelChoices, ariaLabel, menuLabel, placeholder = 'Select a label', className = '' }) {
  const choices = options
  const [open, setOpen] = useState(false)
  const [active, setActive] = useState(0)
  const [position, setPosition] = useState(null)
  const trigger = useRef(null)
  const menu = useRef(null)
  const id = useId()
  const selected = Math.max(0, choices.findIndex((choice) => choice.value === value))

  function show(index = selected) {
    if (disabled) return
    setPosition(menuPosition(trigger.current.getBoundingClientRect()))
    setActive(index)
    setOpen(true)
  }

  function choose(index) {
    onChange(choices[index].value)
    setOpen(false)
    trigger.current?.focus()
  }

  useEffect(() => {
    if (!open) return
    const close = () => setOpen(false)
    const outside = (event) => {
      if (!trigger.current?.contains(event.target) && !menu.current?.contains(event.target)) close()
    }
    const reposition = () => {
      const rect = trigger.current?.getBoundingClientRect()
      if (!rect || rect.bottom <= 0 || rect.top >= window.innerHeight || rect.right <= 0 || rect.left >= window.innerWidth) close()
      else setPosition(menuPosition(rect))
    }
    document.addEventListener('pointerdown', outside, true)
    window.addEventListener('resize', close)
    window.addEventListener('scroll', reposition, true)
    return () => {
      document.removeEventListener('pointerdown', outside, true)
      window.removeEventListener('resize', close)
      window.removeEventListener('scroll', reposition, true)
    }
  }, [open])

  function keyboard(event) {
    if (disabled) return
    if (event.key === 'Tab') { setOpen(false); return }
    if (event.key === 'Escape') { if (open) event.preventDefault(); setOpen(false); return }
    if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault()
      if (open) choose(active)
      else show()
    } else if (['ArrowDown', 'ArrowUp', 'Home', 'End'].includes(event.key)) {
      event.preventDefault()
      const index = event.key === 'Home' ? 0 : event.key === 'End' ? choices.length - 1
        : open ? (active + (event.key === 'ArrowDown' ? 1 : -1) + choices.length) % choices.length
          : value ? selected : event.key === 'ArrowDown' ? 1 : 2
      if (open) setActive(index)
      else show(index)
    } else if (options === labelChoices && ['f', 'n'].includes(event.key.toLowerCase())) {
      event.preventDefault()
      const index = event.key.toLowerCase() === 'f' ? 1 : 2
      if (open) setActive(index)
      else show(index)
    }
  }

  return <div className={`review-label-field ${className}`}>
    <span className="sr-only" id={`${id}-value`}>{value ? `Selected: ${value}, ${choices[selected].title}` : 'No reviewed label selected'}</span>
    <button ref={trigger} type="button" role="combobox" className={`review-label-trigger ${value ? value.toLowerCase() : 'placeholder'}`}
      aria-label={ariaLabel ?? `Reviewed label for ${displayId}`} aria-haspopup="listbox" aria-required="true" aria-describedby={`${id}-value`} aria-expanded={open} aria-controls={open ? id : undefined}
      aria-activedescendant={open ? `${id}-${active}` : undefined} data-value={value} disabled={disabled}
      onKeyDown={keyboard} onBlur={() => setOpen(false)} onClick={() => { if (open) setOpen(false); else show() }}>
      {value && <span className={`label-choice-badge ${value.toLowerCase()}`} aria-hidden="true">{choices[selected].badge ?? value}</span>}
      <span className="label-choice-title">{value ? choices[selected].title : placeholder}</span>
      <svg className={open ? 'label-chevron open' : 'label-chevron'} aria-hidden="true" viewBox="0 0 16 16" fill="none"><path d="m4 6 4 4 4-4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" /></svg>
    </button>
    {open && !disabled && createPortal(<div ref={menu} id={id} role="listbox" aria-label={menuLabel ?? `Review label choices for ${displayId}`} className="review-label-menu" style={position}
      onPointerDown={(event) => event.preventDefault()}>
      {choices.map((choice, index) => <div key={choice.value} id={`${id}-${index}`} role="option" data-value={choice.value} aria-selected={value === choice.value}
        className={`review-label-option ${index === active ? 'active' : ''}`} onPointerMove={() => setActive(index)} onClick={() => choose(index)}>
        <span className={`label-choice-badge ${choice.value ? choice.value.toLowerCase() : 'empty'}`} aria-hidden="true">{choice.badge ?? (choice.value || '—')}</span>
        <span className="label-option-copy"><strong>{choice.title}</strong><small>{choice.description}</small></span>
        {value === choice.value && <span className="label-choice-check" aria-hidden="true">✓</span>}
      </div>)}
    </div>, document.body)}
  </div>
}
