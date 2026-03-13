import { readFileSync, readdirSync, existsSync } from 'fs'
import { join } from 'path'

interface Track {
  name: string
  artist: string
  album: string
  art: string
  url: string
  reason: string
  isNew: boolean
}

interface PlaylistData {
  date: string
  vibe: string
  playlistUrl: string
  playlistName: string
  tracks: Track[]
}

function getAllPlaylists(): PlaylistData[] {
  const dataDir = join(process.cwd(), 'data')
  if (!existsSync(dataDir)) return []
  
  const files = readdirSync(dataDir)
    .filter(f => f.endsWith('.json') && !f.startsWith('descriptions-'))
  
  const playlists = files.map(f => {
    const content = readFileSync(join(dataDir, f), 'utf-8')
    return JSON.parse(content) as PlaylistData
  })
  
  // Sort by date descending (newest first)
  playlists.sort((a, b) => (b.date || '').localeCompare(a.date || ''))
  
  return playlists
}

function getDescriptions(playlistName: string): Record<string, string> {
  const dataDir = join(process.cwd(), 'data')
  
  const descMap: Record<string, string> = {
    '✨ Rusty × Stella': 'descriptions-stella.json',
    '☕ Daikanyama Sessions': 'descriptions-daikanyama.json',
  }
  
  const filename = descMap[playlistName]
  if (!filename) return {}
  
  const filepath = join(dataDir, filename)
  if (!existsSync(filepath)) return {}
  
  try {
    return JSON.parse(readFileSync(filepath, 'utf-8'))
  } catch {
    return {}
  }
}

function formatDate(dateStr: string): string {
  const d = new Date(dateStr + 'T12:00:00')
  return d.toLocaleDateString('en-US', {
    weekday: 'long',
    month: 'long',
    day: 'numeric',
    year: 'numeric'
  })
}

function findDescription(descriptions: Record<string, string>, trackName: string, artistName?: string): string {
  // Try exact match on full key "Track — Artist"
  if (artistName) {
    const fullKey = `${trackName} — ${artistName}`
    if (descriptions[fullKey]) return descriptions[fullKey]
    // Try with first artist only
    const firstArtist = artistName.split(',')[0].trim()
    const shortKey = `${trackName} — ${firstArtist}`
    if (descriptions[shortKey]) return descriptions[shortKey]
  }
  // Try track name only
  if (descriptions[trackName]) return descriptions[trackName]
  // Try matching by track name in key (keys are "Track — Artist")
  for (const [key, val] of Object.entries(descriptions)) {
    const keyTrack = key.split(' — ')[0]
    if (keyTrack === trackName) return val
    if (trackName.toLowerCase().includes(keyTrack.toLowerCase()) ||
        keyTrack.toLowerCase().includes(trackName.toLowerCase())) {
      return val
    }
  }
  return ''
}

export default function Home() {
  const playlists = getAllPlaylists()

  if (playlists.length === 0) {
    return (
      <div className="container">
        <div className="empty-state">
          <h2>🎵 First playlist dropping soon</h2>
          <p>Check back tomorrow morning for your daily discoveries.</p>
        </div>
      </div>
    )
  }

  return (
    <div className="container">
      <div className="hero">
        <h1>🏂 Moby&apos;s Playlists</h1>
        <p className="subtitle">AI-curated music — updated daily</p>
      </div>

      <div className="blog-feed">
        {playlists.map((playlist, idx) => {
          const descriptions = getDescriptions(playlist.playlistName)
          
          return (
            <article key={idx} className="blog-post">
              <header className="post-header">
                <h2 className="post-title">{playlist.playlistName}</h2>
                <time className="post-date">{formatDate(playlist.date)}</time>
                {playlist.vibe && (
                  <p className="post-vibe">{playlist.vibe}</p>
                )}
                {playlist.playlistUrl && (
                  <a href={playlist.playlistUrl} target="_blank" rel="noopener noreferrer" className="spotify-badge">
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor">
                      <path d="M12 0C5.4 0 0 5.4 0 12s5.4 12 12 12 12-5.4 12-12S18.66 0 12 0zm5.521 17.34c-.24.359-.66.48-1.021.24-2.82-1.74-6.36-2.101-10.561-1.141-.418.122-.779-.179-.899-.539-.12-.421.18-.78.54-.9 4.56-1.021 8.52-.6 11.64 1.32.42.18.479.659.301 1.02zm1.44-3.3c-.301.42-.841.6-1.262.3-3.239-1.98-8.159-2.58-11.939-1.38-.479.12-1.02-.12-1.14-.6-.12-.48.12-1.021.6-1.141C9.6 9.9 15 10.561 18.72 12.84c.361.181.54.78.241 1.2zm.12-3.36C15.24 8.4 8.82 8.16 5.16 9.301c-.6.179-1.2-.181-1.38-.721-.18-.601.18-1.2.72-1.381 4.26-1.26 11.28-1.02 15.721 1.621.539.3.719 1.02.419 1.56-.299.421-1.02.599-1.559.3z"/>
                    </svg>
                    Listen on Spotify
                  </a>
                )}
              </header>

              <div className="tracklist">
                {playlist.tracks.map((track, i) => {
                  const desc = track.reason || findDescription(descriptions, track.name, track.artist)
                  return (
                    <div key={i} className="track-entry">
                      <div className="track-number">{String(i + 1).padStart(2, '0')}</div>
                      <a
                        href={track.url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="track-card"
                      >
                        {track.art && (
                          <img
                            src={track.art}
                            alt={track.album}
                            className="track-art"
                            width={80}
                            height={80}
                          />
                        )}
                        <div className="track-details">
                          {track.isNew && <span className="track-new">New Discovery</span>}
                          <div className="track-name">{track.name}</div>
                          <div className="track-artist">{track.artist}</div>
                          {desc && <div className="track-desc">{desc}</div>}
                        </div>
                      </a>
                    </div>
                  )
                })}
              </div>
            </article>
          )
        })}
      </div>

      <footer className="site-footer">
        Curated by Moby 🏂 — AI-powered music discovery
      </footer>
    </div>
  )
}
