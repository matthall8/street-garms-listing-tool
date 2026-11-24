import { useState, useReducer, type SubmitEvent } from "react"
import { captureReducer,initialCapture } from "./state"
import { UPLOAD_TIMEOUT_MS, uploadPhoto } from "./upload"

const NO_PHOTO_MESSAGE = "Add a photo of the label showing the ART number."

export function Capture() {
    const [model, dispatch] = useReducer(captureReducer, initialCapture)
    const [missingPhoto, setMissingPhoto] = useState(false)
    const handleSubmit = async (event: SubmitEvent<HTMLFormElement>) => {
        event.preventDefault()
        const formData = new FormData(event.currentTarget)
        const image = formData.get("productImage")
        if (!(image instanceof File) || image.size === 0) {
            setMissingPhoto(true)
            return 
        }
        setMissingPhoto(false)
        dispatch({type: "submitted"})
        const controller = new AbortController()
        const timeoutId =  setTimeout(() => {
            controller.abort()
        }, UPLOAD_TIMEOUT_MS);
        const action = await uploadPhoto(image, controller.signal)
        clearTimeout(timeoutId)
        dispatch(action)
    }
    const uploadAgain = <button type="button" onClick={() => dispatch({type:"reset"})}>Upload again</button>
    switch(model.state.status) {
        case 'idle':
            return (
                <div>
                    <form onSubmit={handleSubmit}>
                        <label>Input image:
                        <input name="productImage" type="file" accept="image/*" />
                        </label>
                        <button type="submit">Submit</button>
                    </form>
                    {missingPhoto && <p>{NO_PHOTO_MESSAGE}</p>}
                </div>
            );
        case 'uploading':
            return <p>Uploading</p>
        case 'read':
            return(
                <div>
                    <p>Read: {model.state.value_shown}</p>
                    {uploadAgain}
                </div>
            )
        case 'empty':
            return(
                <div>
                    <p>Empty</p>
                    {uploadAgain}
                </div>
            )
        case 'timedOut':
            return(
                <div>
                    <p>Timed Out</p>
                    {uploadAgain}
                </div>
            )
        case 'failed':
                        return(
                <div>
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