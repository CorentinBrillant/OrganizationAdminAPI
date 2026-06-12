import { useCallback, useEffect, useRef } from 'react'

export default function UiEmbed({ file, title, bridgeMessage = null }) {
  const iframeRef = useRef(null)

  const postBridgeMessage = useCallback(() => {
    if (!bridgeMessage) return
    const iframe = iframeRef.current
    if (!iframe?.contentWindow) return
    iframe.contentWindow.postMessage(bridgeMessage, window.location.origin)
  }, [bridgeMessage])

  useEffect(() => {
    postBridgeMessage()
  }, [postBridgeMessage])

  return (
    <iframe
      ref={iframeRef}
      className="ui-embed"
      src={`/ui/${file}?embedded=1`}
      title={title}
      loading="eager"
      referrerPolicy="no-referrer"
      onLoad={postBridgeMessage}
    />
  )
}
