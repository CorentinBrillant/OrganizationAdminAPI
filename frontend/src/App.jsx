import { useEffect, useMemo, useState } from 'react'
import { useSelector } from 'react-redux'
import { loginWithPassword, checkSession, logoutSession } from './api/auth'
import { clearStoredToken, getStoredToken, setStoredToken, syncTokenCookie } from './auth/token'
import Sidebar from './components/Sidebar'
import './index.css'
import DashboardFusionPage from './pages/DashboardFusionPage'
import LoginPage from './pages/LoginPage'
import MemberDedupPage from './pages/MemberDedupPage'
import MonitoringCampagnesPage from './pages/MonitoringCampagnesPage'
import SourceBadgesPage from './pages/SourceBadgesPage'
import SourceFfckPage from './pages/SourceFfckPage'
import SourceHelloAssoPage from './pages/SourceHelloAssoPage'

const pages = {
  dashboard: DashboardFusionPage,
  helloasso: SourceHelloAssoPage,
  ffck: SourceFfckPage,
  badges: SourceBadgesPage,
  dedup: MemberDedupPage,
  monitoring: MonitoringCampagnesPage,
}

function App() {
  const [activePage, setActivePage] = useState('dashboard')
  const [authReady, setAuthReady] = useState(false)
  const [authenticated, setAuthenticated] = useState(false)
  const [authUser, setAuthUser] = useState(null)
  const activeCampaign = useSelector((state) => state.campaigns.activeCampaign)
  const ActivePage = useMemo(() => pages[activePage] || DashboardFusionPage, [activePage])
  const activePageRenderKey = `${activePage}:${String(activeCampaign || '')}`

  useEffect(() => {
    const bootstrapAuth = async () => {
      const token = getStoredToken()
      if (!token) {
        setAuthenticated(false)
        setAuthReady(true)
        return
      }

      syncTokenCookie(token)
      try {
        const session = await checkSession()
        if (session?.authenticated) {
          setAuthenticated(true)
          setAuthUser(
            session?.user && typeof session.user === 'object'
              ? { name: String(session.user.username || '').trim(), role: 'Utilisateur' }
              : null,
          )
        } else {
          clearStoredToken()
          setAuthenticated(false)
          setAuthUser(null)
        }
      } catch (_error) {
        clearStoredToken()
        setAuthenticated(false)
        setAuthUser(null)
      } finally {
        setAuthReady(true)
      }
    }

    bootstrapAuth()
  }, [])

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

  const handleLogin = async ({ username, password }) => {
    const result = await loginWithPassword({ username, password })
    if (!result.token) {
      throw new Error('Token manquant dans la réponse.')
    }

    setStoredToken(result.token)
    setAuthenticated(true)
    setAuthUser(
      result?.user && typeof result.user === 'object'
        ? { name: String(result.user.username || '').trim(), role: 'Utilisateur' }
        : null,
    )
  }

  const handleLogout = async () => {
    try {
      await logoutSession()
    } catch (_error) {
      // If the token is already expired/invalid, local cleanup is still enough.
    } finally {
      clearStoredToken()
      setAuthenticated(false)
      setAuthUser(null)
      setActivePage('dashboard')
    }
  }

  if (!authReady) {
    return (
      <div className="app-shell">
        <main className="app-main">Vérification de la session...</main>
      </div>
    )
  }

  if (!authenticated) {
    return <LoginPage onLogin={handleLogin} />
  }

  return (
    <div className="app-shell">
      <Sidebar activePage={activePage} onPageChange={setActivePage} user={authUser} onLogout={handleLogout} />
      <main className="app-main">
        <ActivePage key={activePageRenderKey} />
      </main>
    </div>
  )
}

export default App
