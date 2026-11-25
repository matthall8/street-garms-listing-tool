import type { CaptureAction, ItemCreated } from "./state"

export const FALLBACK_MESSAGE = "Something went wrong. Please try again."
export const UPLOAD_TIMEOUT_MS = 120000

export const uploadPhoto = async (file: File, abortSignal: AbortSignal): Promise<CaptureAction> => {
  const formData = new FormData()
  formData.append("art_photo", file)
  try {
    const response = await fetch("/items", {
      method: "POST",
      body: formData,
      signal: abortSignal,
    })
    // 200: return the item details
    if (response.ok) {
      const body: ItemCreated = await response.json()
      return { type: "successfulResponse", id: body.id, value_shown: body.value_shown }
    }
    // Not a 200
    let errorBody: unknown
    try {
      errorBody = await response.json()
    } catch {
      return { type: "failedResponse", errorMessage: FALLBACK_MESSAGE }
    }
    if (
      typeof errorBody === "object" &&
      errorBody !== null &&
      "detail" in errorBody &&
      typeof errorBody.detail === "string"
    ) {
      return { type: "failedResponse", errorMessage: errorBody.detail }
    }
    return { type: "failedResponse", errorMessage: FALLBACK_MESSAGE }
  } catch {
    // No response: the 2-minute timer aborted it, or the network failed.
    if (abortSignal.aborted) {
      return { type: "timeout" }
    }
    return { type: "failedResponse", errorMessage: FALLBACK_MESSAGE }
  }
}
