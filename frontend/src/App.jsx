import { useEffect, useMemo, useState } from 'react'
import { useSelector } from 'react-redux'
import Sidebar from './components/Sidebar'
import './index.css'
import DashboardFusionPage from './pages/DashboardFusionPage'
import MemberDedupPage from './pages/MemberDedupPage'
import MonitoringCampagnesPage from './pages/MonitoringCampagnesPage'
import SourceFfckPage from './pages/SourceFfckPage'
import SourceHelloAssoPage from './pages/SourceHelloAssoPage'

const pages = {
  dashboard: DashboardFusionPage,
  helloasso: SourceHelloAssoPage,
  ffck: SourceFfckPage,
  dedup: MemberDedupPage,
  monitoring: MonitoringCampagnesPage,
}

function App() {
  const [activePage, setActivePage] = useState('dashboard')
  const activeCampaign = useSelector((state) => state.campaigns.activeCampaign)
  const ActivePage = useMemo(() => pages[activePage] || DashboardFusionPage, [activePage])
  const activePageRenderKey = `${activePage}:${String(activeCampaign || '')}`

  useEffect(() => {
    const onMessage = (event) => {
      if (event.origin !== window.location.origin) return
      if (event.data?.type !== 'ffck:navigate') return
      const nextPage = event.data?.page
      if (typeof nextPage === 'string' && pages[nextPage]) {
        setActivePage(nextPage)
      }
    }

    window.addEventListener('message', onMessage)
    return () => window.removeEventListener('message', onMessage)
  }, [])

  return (
    <div className="app-shell">
      <Sidebar activePage={activePage} onPageChange={setActivePage} />
      <main className="app-main">
        <ActivePage key={activePageRenderKey} />
      </main>
    </div>
  )
}

export default App
