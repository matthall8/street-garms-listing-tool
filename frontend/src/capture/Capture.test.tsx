import { act, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { Capture } from './Capture'
import { FALLBACK_MESSAGE, UPLOAD_TIMEOUT_MS } from './upload'

// Invented values, made at runtime: no code-shaped literals in tracked files.
const ID = crypto.randomUUID()
const VALUE = 'NOT-A-REAL-VALUE'
const NO_PHOTO = 'Add a photo of the label showing the ART number.'

const photo = () => new File(['x'], 'label.jpg', { type: 'image/jpeg' })
const json = (body: unknown, status: number) => new Response(JSON.stringify(body), { status })

const choose = (file: File) =>
  fireEvent.change(screen.getByLabelText(/input image/i), { target: { files: [file] } })
const submit = () => fireEvent.click(screen.getByRole('button', { name: 'Submit' }))

// A fetch that answers with `response` at once.
const fetchResolving = (response: Response) => {
  const fake = vi.fn().mockResolvedValue(response)
  vi.stubGlobal('fetch', fake)
  return fake
}

// A fetch that stays pending until the test calls `respond`, and rejects only
// when its signal aborts, as the real fetch does.
const fetchPending = () => {
  let respond: (response: Response) => void = () => {}
  const fake = vi.fn(
    (_url: string, init: RequestInit) =>
      new Promise<Response>((resolve, reject) => {
        respond = resolve
        init.signal?.addEventListener('abort', () =>
          reject(new DOMException('The operation was aborted.', 'AbortError')),
        )
      }),
  )
  vi.stubGlobal('fetch', fake)
  return {
    fake,
    signal: () => (fake.mock.calls[0][1] as RequestInit).signal as AbortSignal,
    respond: (response: Response) => respond(response),
  }
}

afterEach(() => {
  vi.useRealTimers()
  vi.unstubAllGlobals()
})

describe('idle', () => {
  it('shows the photo input and submit, with no message', () => {
    render(<Capture />)
    expect(screen.getByLabelText(/input image/i)).toHaveAttribute('type', 'file')
    expect(screen.getByLabelText(/input image/i)).not.toHaveAttribute('capture')
    expect(screen.getByRole('button', { name: 'Submit' })).toBeEnabled()
    expect(screen.queryByText(NO_PHOTO)).not.toBeInTheDocument()
  })

  it('submit with no photo shows the message and sends nothing (decision 10)', () => {
    const fake = fetchResolving(json({ id: ID, value_shown: VALUE }, 200))
    render(<Capture />)

    submit()

    expect(screen.getByText(NO_PHOTO)).toBeInTheDocument()
    expect(fake).not.toHaveBeenCalled()
    expect(screen.getByRole('button', { name: 'Submit' })).toBeInTheDocument()
  })

  it('an empty file counts as no photo', () => {
    const fake = fetchResolving(json({ id: ID, value_shown: VALUE }, 200))
    render(<Capture />)

    choose(new File([], ''))
    submit()

    expect(screen.getByText(NO_PHOTO)).toBeInTheDocument()
    expect(fake).not.toHaveBeenCalled()
  })
})

describe('after a submit', () => {
  it('shows uploading while the request is in flight', () => {
    fetchPending()
    render(<Capture />)
    choose(photo())
    submit()
    expect(screen.getByText('Uploading')).toBeInTheDocument()
  })

  it('sends the chosen file itself', async () => {
    const fake = fetchResolving(json({ id: ID, value_shown: VALUE }, 200))
    const file = photo()
    render(<Capture />)
    choose(file)
    submit()
    await screen.findByText(`Read: ${VALUE}`)
    expect(((fake.mock.calls[0][1] as RequestInit).body as FormData).get('art_photo')).toBe(file)
  })

  it('a read reaches the read placeholder with its value', async () => {
    fetchResolving(json({ id: ID, value_shown: VALUE }, 200))
    render(<Capture />)
    choose(photo())
    submit()
    expect(await screen.findByText(`Read: ${VALUE}`)).toBeInTheDocument()
  })

  it('an empty read reaches the empty placeholder', async () => {
    fetchResolving(json({ id: ID, value_shown: null }, 200))
    render(<Capture />)
    choose(photo())
    submit()
    expect(await screen.findByText('Empty')).toBeInTheDocument()
  })

  it("a rejected upload shows the server's detail", async () => {
    fetchResolving(json({ detail: 'Message from the server.' }, 400))
    render(<Capture />)
    choose(photo())
    submit()
    expect(await screen.findByText('Failed: Message from the server.')).toBeInTheDocument()
  })

  it('a network error shows the fallback', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('Failed to fetch')))
    render(<Capture />)
    choose(photo())
    submit()
    expect(await screen.findByText(`Failed: ${FALLBACK_MESSAGE}`)).toBeInTheDocument()
  })

  it('upload again returns to the form, with no message', async () => {
    fetchResolving(json({ detail: 'Message from the server.' }, 400))
    render(<Capture />)
    submit() // first, the missing-photo message
    choose(photo())
    submit()
    fireEvent.click(await screen.findByRole('button', { name: 'Upload again' }))

    expect(screen.getByRole('button', { name: 'Submit' })).toBeInTheDocument()
    expect(screen.queryByText(NO_PHOTO)).not.toBeInTheDocument()
  })
})

describe('the 2-minute limit (decision 14)', () => {
  it('is 120,000 ms (ADR-0008, D2)', () => {
    expect(UPLOAD_TIMEOUT_MS).toBe(120_000)
  })

  it('aborts at 120,000 ms, not before, and shows timed out', async () => {
    vi.useFakeTimers()
    const request = fetchPending()
    render(<Capture />)
    choose(photo())
    submit()

    await act(() => vi.advanceTimersByTimeAsync(UPLOAD_TIMEOUT_MS - 1))
    expect(request.signal().aborted).toBe(false)
    expect(screen.getByText('Uploading')).toBeInTheDocument()

    await act(() => vi.advanceTimersByTimeAsync(1))
    expect(request.signal().aborted).toBe(true)
    expect(screen.getByText('Timed Out')).toBeInTheDocument()
  })

  it('a response before the limit clears the timer, so nothing aborts later', async () => {
    vi.useFakeTimers()
    const request = fetchPending()
    render(<Capture />)
    choose(photo())
    submit()

    await act(() => vi.advanceTimersByTimeAsync(30_000))
    await act(async () => {
      request.respond(json({ id: ID, value_shown: VALUE }, 200))
      await vi.advanceTimersByTimeAsync(0)
    })
    expect(screen.getByText(`Read: ${VALUE}`)).toBeInTheDocument()
    expect(vi.getTimerCount()).toBe(0)

    await act(() => vi.advanceTimersByTimeAsync(UPLOAD_TIMEOUT_MS))
    expect(request.signal().aborted).toBe(false)
    expect(screen.getByText(`Read: ${VALUE}`)).toBeInTheDocument()
  })

  it('while uploading, submit cannot start a second request', () => {
    vi.useFakeTimers()
    const request = fetchPending()
    render(<Capture />)
    const form = screen.getByRole('button', { name: 'Submit' }).closest('form') as HTMLFormElement
    choose(photo())
    submit()

    // The form is gone while uploading; submitting the old one does nothing.
    expect(screen.queryByRole('button', { name: 'Submit' })).not.toBeInTheDocument()
    fireEvent.submit(form)

    expect(request.fake).toHaveBeenCalledOnce()
    expect(vi.getTimerCount()).toBe(1)
  })
})
