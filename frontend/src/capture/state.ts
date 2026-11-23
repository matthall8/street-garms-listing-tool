import type { components } from "../api-schema";

type ItemCreated = components['schemas']["ItemCreated"]

export type CaptureState =
  | { status: "idle" }
  | { status: "uploading" }
  | { status: "read"; id: ItemCreated["id"]; value_shown: NonNullable<ItemCreated["value_shown"]> }
  | { status: "empty" }
  | { status: "timedOut" }
  | { status: "failed"; errorMessage: string }

export type CaptureAction =
  | { type: "submitted" }
  | { type: "successfulResponse"; id: ItemCreated["id"]; value_shown: ItemCreated["value_shown"] }
  | { type: "failedResponse"; errorMessage: string }
  | { type: "timeout" }
  | { type: "reset" }

export type CaptureModel = {
    state: CaptureState
    failureCount: number 
}

export const initialCapture: CaptureModel = {
    state: { status:"idle" },
    failureCount: 0 
}

export function captureReducer(model: CaptureModel, action: CaptureAction): CaptureModel {
  switch (action.type) {
    case 'submitted':
        if(model.state.status === "uploading") {
            return model
        }
        return {...model, state: {status: "uploading" }}
    case 'successfulResponse':
        if(action.value_shown === null) {
            return { state: { status: "empty" }, failureCount: 0 }
        }
        return {
            state: { status: "read", id: action.id, value_shown: action.value_shown },
            failureCount: 0,
        }
    case 'failedResponse':
        return {
            state: {status: "failed", errorMessage: action.errorMessage },
            failureCount: model.failureCount + 1
        }
    case 'timeout':
        return {
            state: {status: "timedOut" },
            failureCount: model.failureCount + 1
        }
    case 'reset':
        return {
            state: {status: "idle" },
            failureCount: model.failureCount
        }
    default: {
        const unhandled: never = action
        throw new Error(`Unhandled action: ${JSON.stringify(unhandled)}`)
    }
  }
}