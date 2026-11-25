import { render, screen } from '@testing-library/react'
import { expect, it } from 'vitest'
import App from './App.tsx'

it('shows the header and the capture screen', () => {
  render(<App />)

  expect(screen.getByRole('img', { name: 'Street Garms' })).toBeInTheDocument()
  expect(screen.getByRole('heading', { level: 1, name: 'Photograph the label' })).toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Read label' })).toBeInTheDocument()
})
