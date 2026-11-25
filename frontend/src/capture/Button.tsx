import type { ComponentProps } from "react"

// The one full-width action button. Its style lives here only (ADR-0008, D10),
// so callers pass behaviour and content, never a className.
type ButtonProps = Omit<ComponentProps<"button">, "className" | "type"> & {
    type: "button" | "submit"
}

export function Button(props: ButtonProps) {
    return (
        <button
            {...props}
            className={
                "w-full rounded-xl bg-brand-green py-4 text-lg font-bold uppercase tracking-wide " +
                "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-white"
            }
        />
    )
}
