import { render, screen } from '@testing-library/react'
import { expect, it } from 'vitest'
import App from './App.tsx'

it('shows the h1 tag', () => {
  render(<App />)

  const h1 = screen.getByRole('heading', {name: 'Hello World' })

  expect(h1).toBeInTheDocument()
})
