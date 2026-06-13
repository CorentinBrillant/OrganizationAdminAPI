import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import UiEmbed from './UiEmbed'

describe('UiEmbed', () => {
  it('rend un iframe avec l url attendue', () => {
    render(<UiEmbed file="source-ffck.html" title="Source FFCK" />)

    const iframe = screen.getByTitle('Source FFCK')
    expect(iframe).toHaveAttribute('src', '/ui/source-ffck.html?embedded=1')
  })

  it('envoie le bridgeMessage au chargement de l iframe', () => {
    const bridgeMessage = { type: 'ffck:activeCampaignContext', campaignId: 11 }
    render(<UiEmbed file="source-ffck.html" title="Source FFCK" bridgeMessage={bridgeMessage} />)

    const iframe = screen.getByTitle('Source FFCK')
    const postMessage = vi.fn()
    Object.defineProperty(iframe, 'contentWindow', {
      configurable: true,
      value: { postMessage },
    })

    fireEvent.load(iframe)

    expect(postMessage).toHaveBeenCalledWith(bridgeMessage, window.location.origin)
  })
})
