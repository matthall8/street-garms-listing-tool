import { describe, expect, it } from 'vitest'
import { captureReducer, initialCapture, type CaptureAction, type CaptureModel } from './state'

// Invented values: not a real item or a real read. The ID is made at runtime,
// since code-shaped literals stay out of tracked files (CLAUDE.md).
const ID = crypto.randomUUID()
const VALUE = 'NOT-A-REAL-VALUE'

const model = (state: CaptureModel['state'], failureCount = 0): CaptureModel => ({ state, failureCount })

const run = (start: CaptureModel, ...actions: CaptureAction[]): CaptureModel =>
  actions.reduce(captureReducer, start)

it('starts idle with no failures', () => {
  expect(initialCapture).toEqual(model({ status: 'idle' }, 0))
})

describe('submitted', () => {
  it('moves idle to uploading', () => {
    expect(captureReducer(initialCapture, { type: 'submitted' })).toEqual(model({ status: 'uploading' }))
  })

  it('keeps the failure count', () => {
    const failed = model({ status: 'failed', errorMessage: 'x' }, 2)
    expect(captureReducer(failed, { type: 'submitted' }).failureCount).toBe(2)
  })

  it('while uploading, changes nothing', () => {
    const uploading = model({ status: 'uploading' }, 1)
    expect(captureReducer(uploading, { type: 'submitted' })).toBe(uploading)
  })
})

describe('successfulResponse', () => {
  it('with a value, moves to read carrying the id and value', () => {
    const next = captureReducer(model({ status: 'uploading' }), {
      type: 'successfulResponse',
      id: ID,
      value_shown: VALUE,
    })
    expect(next.state).toEqual({ status: 'read', id: ID, value_shown: VALUE })
  })

  it('with a null value, moves to empty, which holds no id (decision 7)', () => {
    const next = captureReducer(model({ status: 'uploading' }), {
      type: 'successfulResponse',
      id: ID,
      value_shown: null,
    })
    expect(next.state).toEqual({ status: 'empty' })
  })

  it.each([VALUE, null])('resets the failure count, an empty read included (value %s)', (value_shown) => {
    const next = captureReducer(model({ status: 'uploading' }, 3), {
      type: 'successfulResponse',
      id: ID,
      value_shown,
    })
    expect(next.failureCount).toBe(0)
  })
})

describe('failures count (decision 8)', () => {
  it('a failed response moves to failed with its message and counts one', () => {
    const next = captureReducer(model({ status: 'uploading' }, 1), {
      type: 'failedResponse',
      errorMessage: 'message',
    })
    expect(next).toEqual(model({ status: 'failed', errorMessage: 'message' }, 2))
  })

  it('a timeout moves to timed out and counts one', () => {
    expect(captureReducer(model({ status: 'uploading' }, 1), { type: 'timeout' })).toEqual(
      model({ status: 'timedOut' }, 2),
    )
  })

  it('the count outlives failed → uploading → failed', () => {
    const fail: CaptureAction = { type: 'failedResponse', errorMessage: 'message' }
    const end = run(initialCapture, { type: 'submitted' }, fail, { type: 'submitted' }, { type: 'timeout' }, { type: 'reset' }, { type: 'submitted' }, fail)
    expect(end.failureCount).toBe(3)
  })
})

describe('reset', () => {
  it('moves back to idle and keeps the failure count', () => {
    const failed = model({ status: 'failed', errorMessage: 'x' }, 2)
    expect(captureReducer(failed, { type: 'reset' })).toEqual(model({ status: 'idle' }, 2))
  })
})

it('never changes the model it is given', () => {
  const start = Object.freeze(model(Object.freeze({ status: 'uploading' as const }), 1))
  const actions: CaptureAction[] = [
    { type: 'submitted' },
    { type: 'successfulResponse', id: ID, value_shown: VALUE },
    { type: 'failedResponse', errorMessage: 'message' },
    { type: 'timeout' },
    { type: 'reset' },
  ]
  for (const action of actions) {
    expect(() => captureReducer(start, action)).not.toThrow()
  }
  expect(start).toEqual(model({ status: 'uploading' }, 1))
})
