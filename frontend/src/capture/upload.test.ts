import { afterEach, describe, expect, it, vi } from 'vitest'
import { FALLBACK_MESSAGE, uploadPhoto } from './upload'

// Invented values, made at runtime: no code-shaped literals in tracked files.
const ID = crypto.randomUUID()
const VALUE = 'NOT-A-REAL-VALUE'

const photo = () => new File(['x'], 'label.jpg', { type: 'image/jpeg' })
const json = (body: unknown, status: number) => new Response(JSON.stringify(body), { status })

// Installs a fake fetch that resolves to `response`, and returns it to inspect.
const fetchResolving = (response: Response) => {
  const fake = vi.fn().mockResolvedValue(response)
  vi.stubGlobal('fetch', fake)
  return fake
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('the request', () => {
  it('POSTs the original file as art_photo to /items, with the signal', async () => {
    const fake = fetchResolving(json({ id: ID, value_shown: VALUE }, 200))
    const file = photo()
    const signal = new AbortController().signal

    await uploadPhoto(file, signal)

    expect(fake).toHaveBeenCalledOnce()
    const [url, init] = fake.mock.calls[0]
    expect(url).toBe('/items')
    expect(init.method).toBe('POST')
    expect(init.signal).toBe(signal)
    expect(init.body).toBeInstanceOf(FormData)
    // The same File object, unchanged (decision 13), under the schema's field name.
    expect((init.body as FormData).get('art_photo')).toBe(file)
    // The browser sets the multipart boundary; a hand-set Content-Type would break it.
    expect(init.headers).toBeUndefined()
  })
})

describe('a 200', () => {
  it.each([VALUE, null])('becomes successfulResponse with the body (value %s)', async (value_shown) => {
    fetchResolving(json({ id: ID, value_shown }, 200))
    expect(await uploadPhoto(photo(), new AbortController().signal)).toEqual({
      type: 'successfulResponse',
      id: ID,
      value_shown,
    })
  })
})

describe('not a 200 (decision 9)', () => {
  it.each([400, 413, 502])('JSON with a string detail shows that detail (%i)', async (status) => {
    fetchResolving(json({ detail: 'Message from the server.' }, status))
    expect(await uploadPhoto(photo(), new AbortController().signal)).toEqual({
      type: 'failedResponse',
      errorMessage: 'Message from the server.',
    })
  })

  it('an HTML error page gets the fallback, never the raw body', async () => {
    fetchResolving(new Response('<html><body>Service Unavailable</body></html>', { status: 503 }))
    expect(await uploadPhoto(photo(), new AbortController().signal)).toEqual({
      type: 'failedResponse',
      errorMessage: FALLBACK_MESSAGE,
    })
  })

  it.each([{}, { detail: 5 }, { detail: null }, null, 'a string', ['detail']])(
    'JSON without a string detail gets the fallback (%j)',
    async (body) => {
      fetchResolving(json(body, 400))
      expect(await uploadPhoto(photo(), new AbortController().signal)).toEqual({
        type: 'failedResponse',
        errorMessage: FALLBACK_MESSAGE,
      })
    },
  )
})

describe('no response', () => {
  it('an aborted request becomes timeout', async () => {
    // Rejects only when its signal aborts, as the real fetch does.
    vi.stubGlobal(
      'fetch',
      vi.fn(
        (_url: string, init: RequestInit) =>
          new Promise<Response>((_resolve, reject) => {
            init.signal?.addEventListener('abort', () =>
              reject(new DOMException('The operation was aborted.', 'AbortError')),
            )
          }),
      ),
    )
    const controller = new AbortController()

    const result = uploadPhoto(photo(), controller.signal)
    controller.abort()

    expect(await result).toEqual({ type: 'timeout' })
  })

  it('a network error, with no abort, gets the fallback', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('Failed to fetch')))
    expect(await uploadPhoto(photo(), new AbortController().signal)).toEqual({
      type: 'failedResponse',
      errorMessage: FALLBACK_MESSAGE,
    })
  })
})
