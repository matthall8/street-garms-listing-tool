import { useState, useReducer, type ChangeEvent, type SubmitEvent } from "react"
import { CameraIcon, TagIcon } from "./icons"
import { captureReducer, initialCapture } from "./state"
import { UPLOAD_TIMEOUT_MS, uploadPhoto } from "./upload"

const NO_PHOTO_MESSAGE = "Add a photo of the label showing the ART number."

const buttonClass =
    "w-full rounded-xl bg-brand-green py-4 text-lg font-bold uppercase tracking-wide " +
    "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-white"

export function Capture() {
    const [model, dispatch] = useReducer(captureReducer, initialCapture)
    const [missingPhoto, setMissingPhoto] = useState(false)
    // The chosen photo's name, shown in the box; null until one is chosen.
    const [photoName, setPhotoName] = useState<string | null>(null)

    const handleChange = (event: ChangeEvent<HTMLInputElement>) => {
        const file = event.currentTarget.files?.[0]
        setPhotoName(file && file.size > 0 ? file.name : null)
        setMissingPhoto(false)
    }

    const handleSubmit = async (event: SubmitEvent<HTMLFormElement>) => {
        event.preventDefault()
        const input = event.currentTarget.elements.namedItem("productImage")
        const image = input instanceof HTMLInputElement ? input.files?.[0] : undefined
        if (!(image instanceof File) || image.size === 0) {
            setMissingPhoto(true)
            return
        }
        // Leaving idle: the form unmounts, so its next showing starts empty.
        setMissingPhoto(false)
        setPhotoName(null)
        dispatch({ type: "submitted" })
        const controller = new AbortController()
        const timeoutId = setTimeout(() => {
            controller.abort()
        }, UPLOAD_TIMEOUT_MS)
        const action = await uploadPhoto(image, controller.signal)
        clearTimeout(timeoutId)
        dispatch(action)
    }

    const uploadAgain = (
        <button type="button" className={buttonClass} onClick={() => dispatch({ type: "reset" })}>
            Upload again
        </button>
    )

    switch (model.state.status) {
        case "idle":
            return (
                <form onSubmit={handleSubmit} className="flex flex-col gap-5">
                    <p className="flex gap-3">
                        <TagIcon className="mt-0.5 size-5 shrink-0 text-brand-green" />
                        <span>
                            Find the small tag with <strong>“Art.”</strong> on it, where there is one.
                        </span>
                    </p>
                    {/* The whole box is the input's label, so a tap anywhere opens the picker. */}
                    <label className="flex min-h-96 cursor-pointer flex-col items-center justify-center gap-4 rounded-2xl border-2 border-dashed border-brand-green bg-neutral-900 p-6 text-center focus-within:outline-2 focus-within:outline-offset-2 focus-within:outline-white">
                        <span className="flex size-28 items-center justify-center rounded-full bg-brand-green">
                            <CameraIcon className="size-12" />
                        </span>
                        <span className="text-xl font-bold uppercase tracking-wide">
                            {photoName === null ? "Open camera" : "Photo ready"}
                        </span>
                        <span className="break-all text-sm text-neutral-400">
                            {photoName === null ? "Tap anywhere in this box" : `${photoName}, tap to change`}
                        </span>
                        <input
                            name="productImage"
                            type="file"
                            accept="image/*"
                            className="sr-only"
                            onChange={handleChange}
                        />
                    </label>
                    {missingPhoto && (
                        <p role="alert" className="text-red-400">
                            {NO_PHOTO_MESSAGE}
                        </p>
                    )}
                    <button type="submit" className={buttonClass}>
                        Read label
                    </button>
                </form>
            )
        case "uploading":
            return (
                <div role="status" className="flex min-h-96 flex-col items-center justify-center gap-4 rounded-2xl border-2 border-brand-green bg-neutral-900 p-6 text-center">
                    <span className="size-16 animate-spin rounded-full border-4 border-neutral-700 border-t-brand-green" />
                    <p className="text-xl font-bold uppercase tracking-wide">Reading the label</p>
                    <p className="text-sm text-neutral-400">This can take up to 2 minutes.</p>
                </div>
            )
        // Bare placeholders until mvp-confirm.
        case "read":
            return (
                <div className="flex flex-col gap-5">
                    <p>Read: {model.state.value_shown}</p>
                    {uploadAgain}
                </div>
            )
        case "empty":
            return (
                <div className="flex flex-col gap-5">
                    <p>Empty</p>
                    {uploadAgain}
                </div>
            )
        case "timedOut":
            return (
                <div className="flex flex-col gap-5">
                    <p>Timed Out</p>
                    {uploadAgain}
                </div>
            )
        case "failed":
            return (
                <div className="flex flex-col gap-5">
                    <p>Failed: {model.state.errorMessage}</p>
                    {uploadAgain}
                </div>
            )
        default: {
            const unhandled: never = model.state
            throw new Error(`Unhandled state: ${JSON.stringify(unhandled)}`)
        }
    }
}
