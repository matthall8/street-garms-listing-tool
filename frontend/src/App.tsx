import logo from "./assets/logosg.avif"
import { Capture } from "./capture/Capture"

function App() {
  return (
    <>
      <header className="flex items-center justify-between border-b-4 border-brand-green bg-white px-4 py-3 text-black">
        <img src={logo} alt="Street Garms" className="h-6" />
        <p className="text-sm font-bold uppercase tracking-widest">Label reader</p>
      </header>
      <main className="mx-auto flex w-full max-w-md flex-col gap-5 px-6 pt-6 pb-8">
        <h1 className="font-display text-5xl font-semibold uppercase leading-[0.85]">Photograph the label</h1>
        <Capture />
      </main>
    </>
  )
}

export default App
