import { useState, useCallback } from 'react'
import {
  BookOpen, BookMarked, DollarSign, Globe, Quote,
  QrCode, Mail, MapPin, CalendarDays, User, Users,
  Sun, Zap, RefreshCw, Loader2, ExternalLink, Copy,
  Check, BookText, Sparkles, Gamepad2, Smile, Search,
  Gamepad, Wine, Telescope, Brain, PawPrint,
  Cat, Laugh, Radio, Swords, Hash,
} from 'lucide-react'
import { motion } from 'framer-motion'
import { api } from '../utils/api'

// ─── Categories & Icon Map ─────────────────────────────────────────────────

interface ApiCard {
  id: string
  category: string
  title: string
  description: string
  icon: typeof BookOpen
  endpoint: string
  color: string   // tailwind color class for the accent
}

const API_CARDS: ApiCard[] = [
  // ── Reference ──
  { id: 'dictionary', category: 'Reference', title: 'Dictionary', description: 'Word definitions, phonetics & examples', icon: BookText, endpoint: '/api/free/dictionary?word=', color: 'from-cyan-400 to-blue-500' },
  { id: 'random-fact', category: 'Reference', title: 'Random Fact', description: 'Useless but true facts', icon: Sparkles, endpoint: '/api/free/random-fact', color: 'from-violet-400 to-purple-500' },
  { id: 'joke', category: 'Reference', title: 'Chuck Norris Jokes', description: 'Hand-curated Chuck Norris facts', icon: Smile, endpoint: '/api/free/joke', color: 'from-amber-400 to-orange-500' },

  // ── Books & Poetry ──
  { id: 'books', category: 'Books', title: 'Open Library', description: 'Search millions of books', icon: BookOpen, endpoint: '/api/free/books?q=', color: 'from-emerald-400 to-green-500' },
  { id: 'poem', category: 'Books', title: 'Random Poem', description: 'Poetry from PoetryDB', icon: Quote, endpoint: '/api/free/poem', color: 'from-pink-400 to-rose-500' },

  // ── Finance ──
  { id: 'currency', category: 'Finance', title: 'Currency Rates', description: 'Live exchange rates (150+ currencies)', icon: DollarSign, endpoint: '/api/free/currency?base=', color: 'from-green-400 to-teal-500' },
  { id: 'currency-convert', category: 'Finance', title: 'Currency Converter', description: 'Convert between any two currencies', icon: Globe, endpoint: '/api/free/currency/convert?amount=1&from=USD&to=EUR', color: 'from-teal-400 to-cyan-500' },

  // ── Productivity ──
  { id: 'ip', category: 'Tools', title: 'IP Geolocation', description: 'Your public IP & location', icon: MapPin, endpoint: '/api/free/ip', color: 'from-indigo-400 to-blue-500' },
  { id: 'qrcode', category: 'Tools', title: 'QR Code Generator', description: 'Generate QR codes from any text', icon: QrCode, endpoint: '/api/free/qrcode?data=', color: 'from-purple-400 to-pink-500' },
  { id: 'email-validate', category: 'Tools', title: 'Email Validator', description: 'Check if an email is valid', icon: Mail, endpoint: '/api/free/email/validate?email=', color: 'from-red-400 to-rose-500' },

  // ── Demographics ──
  { id: 'age', category: 'Demographics', title: 'Age Estimator', description: 'Guess age from a first name', icon: User, endpoint: '/api/free/age?name=', color: 'from-sky-400 to-cyan-500' },
  { id: 'gender', category: 'Demographics', title: 'Gender Estimator', description: 'Guess gender from a first name', icon: Users, endpoint: '/api/free/gender?name=', color: 'from-fuchsia-400 to-pink-500' },
  { id: 'nationality', category: 'Demographics', title: 'Nationality Estimator', description: 'Guess nationality from a name', icon: Globe, endpoint: '/api/free/nationality?name=', color: 'from-blue-400 to-indigo-500' },

  // ── Calendar ──
  { id: 'holidays', category: 'Calendar', title: 'Public Holidays', description: 'Holidays for 90+ countries', icon: CalendarDays, endpoint: '/api/free/holidays?country=', color: 'from-yellow-400 to-amber-500' },

  // ── Entertainment ──
  { id: 'bored', category: 'Entertainment', title: 'Bored API', description: 'Random activity suggestions', icon: Sun, endpoint: '/api/free/bored', color: 'from-orange-400 to-red-500' },
  { id: 'games', category: 'Entertainment', title: 'Free Games', description: 'Free-to-play game database', icon: Gamepad2, endpoint: '/api/free/games', color: 'from-lime-400 to-green-500' },
  { id: 'jokeapi', category: 'Entertainment', title: 'JokeAPI', description: 'Random jokes from all categories', icon: Laugh, endpoint: '/api/free/jokeapi', color: 'from-amber-400 to-yellow-500' },

  // ── Gaming ──
  { id: 'steam-deals', category: 'Gaming', title: 'Steam Deals', description: 'CheapShark game price tracker', icon: Gamepad, endpoint: '/api/free/steam-deals', color: 'from-blue-500 to-indigo-600' },
  { id: 'rick-morty', category: 'Gaming', title: 'Rick and Morty', description: 'Character database', icon: Radio, endpoint: '/api/free/rick-morty/random', color: 'from-green-500 to-teal-600' },
  { id: 'star-wars', category: 'Gaming', title: 'Star Wars API', description: 'SWAPI character data', icon: Swords, endpoint: '/api/free/star-wars/random', color: 'from-yellow-500 to-orange-600' },

  // ── Food & Drink ──
  { id: 'cocktail', category: 'Food & Drink', title: 'Cocktail DB', description: 'Cocktail recipes & ingredients', icon: Wine, endpoint: '/api/free/cocktail?name=', color: 'from-pink-500 to-rose-600' },
  { id: 'cocktail-random', category: 'Food & Drink', title: 'Random Cocktail', description: 'Surprise cocktail recipe', icon: Wine, endpoint: '/api/free/cocktail/random', color: 'from-purple-500 to-fuchsia-600' },

  // ── Science ──
  { id: 'nasa-apod', category: 'Science', title: 'NASA APOD', description: 'Astronomy Picture of the Day', icon: Telescope, endpoint: '/api/free/nasa/apod', color: 'from-indigo-500 to-violet-600' },
  { id: 'trivia', category: 'Science', title: 'Open Trivia DB', description: 'Random trivia questions', icon: Brain, endpoint: '/api/free/trivia', color: 'from-cyan-500 to-blue-600' },
  { id: 'number-fact', category: 'Science', title: 'Numbers API', description: 'Interesting number facts', icon: Hash, endpoint: '/api/free/number-fact?number=', color: 'from-emerald-500 to-teal-600' },

  // ── Animals ──
  { id: 'dog', category: 'Animals', title: 'Dog CEO', description: 'Random dog pictures', icon: PawPrint, endpoint: '/api/free/dog', color: 'from-amber-500 to-orange-600' },
  { id: 'cat', category: 'Animals', title: 'Cat API', description: 'Random cat pictures', icon: Cat, endpoint: '/api/free/cat', color: 'from-rose-500 to-pink-600' },
]

const COPY_QUICK: Record<string, { label: string; query: string }[]> = {
  dictionary: [
    { label: 'serendipity', query: 'serendipity' },
    { label: 'ephemeral', query: 'ephemeral' },
    { label: 'ubiquitous', query: 'ubiquitous' },
  ],
  books: [
    { label: 'AI & Machine Learning', query: 'artificial intelligence' },
    { label: 'Classic Sci-Fi', query: 'Dune' },
    { label: 'Self-Improvement', query: 'Atomic Habits' },
  ],
  cocktail: [
    { label: 'Margarita', query: 'margarita' },
    { label: 'Mojito', query: 'mojito' },
    { label: 'Old Fashioned', query: 'old fashioned' },
  ],
  'number-fact': [
    { label: '42', query: '42' },
    { label: 'π (pi)', query: '314' },
    { label: 'Year you were born', query: '1990' },
  ],
}

// ─── Card Templates ─────────────────────────────────────────────────────────

// Each API card has a specific render function based on its response shape

function renderResult(cardId: string, data: Record<string, unknown>) {
  switch (cardId) {
    case 'dictionary':
      return renderDictionary(data)
    case 'random-fact':
      return renderFact(data)
    case 'joke':
      return renderJoke(data)
    case 'books':
      return renderBooks(data)
    case 'poem':
      return renderPoem(data)
    case 'currency':
      return renderCurrencyRates(data)
    case 'currency-convert':
      return renderCurrencyConvert(data)
    case 'ip':
      return renderIpInfo(data)
    case 'qrcode':
      return renderQrCode(data)
    case 'email-validate':
      return renderEmailValidation(data)
    case 'age':
      return renderDemographic(data, 'age')
    case 'gender':
      return renderDemographic(data, 'gender')
    case 'nationality':
      return renderNationality(data)
    case 'holidays':
      return renderHolidays(data)
    case 'bored':
      return renderBored(data)
    case 'games':
      return renderGames(data)
    case 'steam-deals':
      return renderSteamDeals(data)
    case 'cocktail':
    case 'cocktail-random':
      return renderCocktail(data)
    case 'nasa-apod':
      return renderNasaApod(data)
    case 'trivia':
      return renderTrivia(data)
    case 'dog':
    case 'cat':
      return renderAnimal(data)
    case 'jokeapi':
      return renderJokeApi(data)
    case 'rick-morty':
      return renderRickMorty(data)
    case 'star-wars':
      return renderStarWars(data)
    case 'number-fact':
      return renderNumberFact(data)
    default:
      return <pre className="text-xs text-dim-400 overflow-auto max-h-40">{JSON.stringify(data, null, 2)}</pre>
  }
}

function renderDictionary(data: Record<string, unknown>) {
  const defs = data.definitions as Array<{ part_of_speech: string; definition: string; example: string }> | undefined
  if (!defs?.length) return <p className="text-dim-400 text-sm">No definitions found</p>
  return (
    <div className="space-y-2">
      <p className="text-lg font-bold text-ghost">{(data.word as string)?.toUpperCase()}</p>
      {(data.phonetic as string) && <p className="text-xs text-dim-400">/{data.phonetic as string}/</p>}
      {defs.map((d, i) => (
        <div key={i} className="border-l-2 border-cyan-500/30 pl-3">
          <span className="text-[10px] uppercase tracking-wider text-cyan-400 font-semibold">{d.part_of_speech}</span>
          <p className="text-sm text-ghost mt-0.5">{d.definition}</p>
          {d.example && <p className="text-xs text-dim-500 italic mt-0.5">"{d.example}"</p>}
        </div>
      ))}
    </div>
  )
}

function renderFact(data: Record<string, unknown>) {
  return <p className="text-sm text-ghost leading-relaxed">{(data.fact as string) || 'No fact found'}</p>
}

function renderJoke(data: Record<string, unknown>) {
  return <p className="text-sm text-ghost leading-relaxed">{(data.joke as string) || 'No joke found'}</p>
}

function renderBooks(data: Record<string, unknown>) {
  const books = data.books as Array<{ title: string; author: string; year: number; cover_url: string | null }> | undefined
  if (!books?.length) return <p className="text-dim-400 text-sm">No books found</p>
  return (
    <div className="space-y-2 max-h-48 overflow-y-auto">
      {books.map((b, i) => (
        <div key={i} className="flex gap-3 items-start">
          {b.cover_url ? (
            <img src={b.cover_url} alt={b.title} className="w-10 h-14 rounded object-cover bg-white/5 flex-shrink-0" />
          ) : (
            <div className="w-10 h-14 rounded bg-white/5 flex items-center justify-center flex-shrink-0">
              <BookMarked className="w-4 h-4 text-dim-400" />
            </div>
          )}
          <div className="min-w-0">
            <p className="text-sm text-ghost truncate">{b.title}</p>
            <p className="text-xs text-dim-400">{b.author || 'Unknown author'}</p>
            {b.year && <p className="text-[10px] text-dim-500">{b.year}</p>}
          </div>
        </div>
      ))}
    </div>
  )
}

function renderPoem(data: Record<string, unknown>) {
  const lines = data.lines as string[] | undefined
  if (!lines?.length) return <p className="text-dim-400 text-sm">No poem found</p>
  return (
    <div>
      <p className="text-sm font-bold text-ghost">{(data.title as string)?.toUpperCase()}</p>
      <p className="text-[10px] text-dim-500 mb-2">by {data.author as string}</p>
      <div className="text-xs text-ghost/80 leading-relaxed italic max-h-40 overflow-y-auto">
        {lines.slice(0, 20).map((line, i) => (
          <p key={i}>{line}</p>
        ))}
      </div>
    </div>
  )
}

function renderCurrencyRates(data: Record<string, unknown>) {
  const rates = data.rates as Record<string, number> | undefined
  if (!rates) return <p className="text-dim-400 text-sm">No rates available</p>
  const majors = ['EUR', 'GBP', 'JPY', 'CHF', 'CAD', 'AUD', 'INR', 'CNY', 'BRL', 'KRW']
  return (
    <div>
      <p className="text-xs text-dim-400">Base: <span className="text-ghost font-bold">{data.base as string}</span> ({data.date as string})</p>
      <div className="mt-2 grid grid-cols-2 gap-1 text-xs">
        {majors.map((code) => {
          const rate = rates[code]
          if (!rate) return null
          return (
            <div key={code} className="flex justify-between px-2 py-1 rounded bg-white/5">
              <span className="text-dim-400">{code}</span>
              <span className="text-ghost">{rate.toFixed(4)}</span>
            </div>
          )
        })}
      </div>
    </div>
  )
}

function renderCurrencyConvert(data: Record<string, unknown>) {
  return (
    <div className="text-center">
      <p className="text-2xl font-bold text-ghost">{data.converted as number}</p>
      <p className="text-xs text-dim-400">
        {data.amount as number} {data.from as string} = {data.to as string}
      </p>
      <p className="text-[10px] text-dim-500 mt-1">Rate: {(data.rate as number)?.toFixed(6)}</p>
      <p className="text-[10px] text-dim-500">{data.date as string}</p>
    </div>
  )
}

function renderIpInfo(data: Record<string, unknown>) {
  return (
    <div className="space-y-1 text-xs">
      <div className="flex justify-between"><span className="text-dim-400">IP</span><span className="text-ghost font-mono">{data.ip as string}</span></div>
      <div className="flex justify-between"><span className="text-dim-400">City</span><span className="text-ghost">{data.city as string}</span></div>
      <div className="flex justify-between"><span className="text-dim-400">Region</span><span className="text-ghost">{data.region as string}</span></div>
      <div className="flex justify-between"><span className="text-dim-400">Country</span><span className="text-ghost">{data.country as string}</span></div>
      <div className="flex justify-between"><span className="text-dim-400">ISP</span><span className="text-ghost">{data.isp as string}</span></div>
      {(data.lat != null && data.lon != null) && (
        <div className="flex justify-between"><span className="text-dim-400">Coords</span><span className="text-ghost font-mono">{Number(data.lat).toFixed(4)}, {Number(data.lon).toFixed(4)}</span></div>
      )}
    </div>
  )
}

function renderQrCode(data: Record<string, unknown>) {
  return (
    <div className="flex flex-col items-center">
      <img
        src={data.image_url as string}
        alt="QR Code"
        className="w-32 h-32 rounded-lg bg-white p-2"
      />
      <p className="text-[10px] text-dim-500 mt-2 truncate max-w-full">{data.data as string}</p>
    </div>
  )
}

function renderEmailValidation(data: Record<string, unknown>) {
  const valid = data.valid as boolean
  return (
    <div className="text-center">
      <div className={`text-3xl mb-2 ${valid ? 'text-emerald-400' : 'text-red-400'}`}>
        {valid ? '✓' : '✗'}
      </div>
      <p className="text-sm text-ghost">{data.email as string}</p>
      <p className={`text-xs mt-1 ${valid ? 'text-emerald-400' : 'text-red-400'}`}>
        {valid ? 'Valid email' : 'Invalid email'}
      </p>
      {(data.disposable as boolean) && <p className="text-[10px] text-amber-400 mt-1">⚠ Disposable email detected</p>}
    </div>
  )
}

function renderDemographic(data: Record<string, unknown>, type: 'age' | 'gender') {
  if (type === 'age') {
    return (
      <div className="text-center">
        <p className="text-3xl font-bold text-ghost">{data.age != null ? `${data.age}` : '?'}</p>
        <p className="text-xs text-dim-400">years old (estimated)</p>
        <p className="text-[10px] text-dim-500 mt-1">Based on {data.count as number} records</p>
      </div>
    )
  }
  return (
    <div className="text-center">
      <p className={`text-3xl font-bold capitalize ${data.gender === 'male' ? 'text-blue-400' : data.gender === 'female' ? 'text-pink-400' : 'text-dim-400'}`}>
        {data.gender as string || '?'}
      </p>
      <p className="text-xs text-dim-400">Probability: {((data.probability as number) * 100).toFixed(0)}%</p>
      <p className="text-[10px] text-dim-500 mt-1">Based on {data.count as number} records</p>
    </div>
  )
}

function renderNationality(data: Record<string, unknown>) {
  const countries = data.countries as Array<{ country_id: string; probability: number }> | undefined
  if (!countries?.length) return <p className="text-dim-400 text-sm">No data</p>
  return (
    <div className="space-y-1">
      {countries.map((c, i) => (
        <div key={i} className="flex justify-between items-center">
          <span className="text-sm text-ghost">{c.country_id}</span>
          <div className="flex items-center gap-2">
            <div className="w-20 h-1.5 rounded-full bg-white/10 overflow-hidden">
              <div className="h-full rounded-full bg-gradient-to-r from-cyan-400 to-blue-500" style={{ width: `${c.probability}%` }} />
            </div>
            <span className="text-xs text-dim-400 w-10 text-right">{c.probability}%</span>
          </div>
        </div>
      ))}
    </div>
  )
}

function renderHolidays(data: Record<string, unknown>) {
  const holidays = data.holidays as Array<{ date: string; name: string; local_name: string }> | undefined
  if (!holidays?.length) return <p className="text-dim-400 text-sm">No holidays found</p>
  const upcoming = holidays.slice(0, 5)
  return (
    <div className="space-y-1.5 max-h-48 overflow-y-auto">
      {upcoming.map((h, i) => (
        <div key={i} className="flex gap-2 items-center">
          <span className="text-[10px] font-mono text-dim-400 w-20">{h.date}</span>
          <span className="text-xs text-ghost">{h.name}</span>
        </div>
      ))}
    </div>
  )
}

function renderBored(data: Record<string, unknown>) {
  return (
    <div className="text-center">
      <p className="text-sm text-ghost leading-relaxed">{(data.activity as string) || 'No activity found'}</p>
      <div className="flex gap-2 justify-center mt-2 text-[10px] text-dim-400">
        <span className="px-2 py-0.5 rounded-full bg-white/5 capitalize">{(data.type as string)}</span>
        <span className="px-2 py-0.5 rounded-full bg-white/5">{data.participants as number} 👤</span>
        <span className="px-2 py-0.5 rounded-full bg-white/5">${(data.price as number) > 0 ? (data.price as number).toFixed(2) : 'Free'}</span>
      </div>
    </div>
  )
}

function renderGames(data: Record<string, unknown>) {
  const games = data.games as Array<{ title: string; genre: string; platform: string; thumbnail: string; short_description: string; url: string }> | undefined
  if (!games?.length) return <p className="text-dim-400 text-sm">No games found</p>
  return (
    <div className="space-y-2 max-h-48 overflow-y-auto">
      {games.slice(0, 4).map((g, i) => (
        <div key={i} className="flex gap-2 items-start">
          {g.thumbnail && <img src={g.thumbnail} alt={g.title} className="w-12 h-12 rounded object-cover flex-shrink-0" />}
          <div className="min-w-0">
            <p className="text-xs text-ghost font-semibold truncate">{g.title}</p>
            <p className="text-[10px] text-dim-400">{g.genre} · {g.platform}</p>
          </div>
        </div>
      ))}
    </div>
  )
}

function renderSteamDeals(data: Record<string, unknown>) {
  const deals = data.deals as Array<{ title: string; sale_price: number; normal_price: number; savings: number; thumb: string; store_id: string }> | undefined
  if (!deals?.length) return <p className="text-dim-400 text-sm">No deals found</p>
  return (
    <div className="space-y-1.5 max-h-48 overflow-y-auto">
      {deals.slice(0, 4).map((d, i) => (
        <div key={i} className="flex gap-2 items-start">
          {d.thumb && <img src={d.thumb} alt={d.title} className="w-10 h-10 rounded object-cover flex-shrink-0" />}
          <div className="min-w-0 flex-1">
            <p className="text-xs text-ghost font-semibold truncate">{d.title}</p>
            <div className="flex gap-1.5 items-center mt-0.5">
              <span className="text-xs font-bold text-emerald-400">${d.sale_price.toFixed(2)}</span>
              <span className="text-[10px] text-dim-500 line-through">${d.normal_price.toFixed(2)}</span>
              <span className="text-[9px] px-1 py-0.5 rounded bg-emerald-500/20 text-emerald-400">-{d.savings.toFixed(0)}%</span>
            </div>
          </div>
        </div>
      ))}
    </div>
  )
}

function renderCocktail(data: Record<string, unknown>) {
  const cocktails = data.cocktails as Array<{ name: string; category: string; glass: string; instructions: string; ingredients: string[]; thumbnail: string; alcoholic: string }> | undefined
  const single = (!cocktails && data.name) ? data as unknown as { name: string; category: string; glass: string; instructions: string; ingredients: string[]; thumbnail: string; alcoholic: string } : undefined
  const items = cocktails || (single ? [single] : [])
  if (!items || (items as Array<Record<string, unknown>>).length === 0) return <p className="text-dim-400 text-sm">No cocktail found</p>
  const c = items[0] as { name?: string; category?: string; glass?: string; instructions?: string; ingredients?: string[]; thumbnail?: string; alcoholic?: string }
  return (
    <div>
      <div className="flex gap-2 items-start mb-2">
        {c.thumbnail && <img src={c.thumbnail} alt={c.name} className="w-12 h-12 rounded-lg object-cover flex-shrink-0" />}
        <div>
          <p className="text-sm font-bold text-ghost">{c.name}</p>
          <p className="text-[10px] text-dim-400">{c.category} · {c.alcoholic}</p>
          <p className="text-[10px] text-dim-500">Glass: {c.glass}</p>
        </div>
      </div>
      {c.ingredients && c.ingredients.length > 0 && (
        <div className="flex flex-wrap gap-1 mb-2">
          {c.ingredients.slice(0, 6).map((ing, i) => (
            <span key={i} className="text-[9px] px-1.5 py-0.5 rounded-full bg-white/5 text-dim-400">{ing}</span>
          ))}
        </div>
      )}
      {c.instructions && <p className="text-[10px] text-dim-500 leading-relaxed line-clamp-3">{c.instructions}</p>}
    </div>
  )
}

function renderNasaApod(data: Record<string, unknown>) {
  return (
    <div>
      <p className="text-sm font-bold text-ghost">{data.title as string}</p>
      <p className="text-[10px] text-dim-500 mb-1">{data.date as string}{data.copyright ? ` © ${data.copyright as string}` : ''}</p>
      {(data.image_url as string) && (
        <img src={data.image_url as string} alt={data.title as string} className="w-full h-24 rounded-lg object-cover mb-1 bg-white/5" />
      )}
      <p className="text-[10px] text-dim-400 leading-relaxed line-clamp-3">{data.explanation as string}</p>
    </div>
  )
}

function renderTrivia(data: Record<string, unknown>) {
  const questions = data.questions as Array<{ category: string; difficulty: string; question: string; correct_answer: string; incorrect_answers: string[] }> | undefined
  if (!questions?.length) return <p className="text-dim-400 text-sm">No questions found</p>
  const q = questions[0]
  return (
    <div>
      <div className="flex gap-1 mb-1">
        <span className="text-[9px] px-1.5 py-0.5 rounded-full bg-white/5 text-cyan-400">{q.category}</span>
        <span className={`text-[9px] px-1.5 py-0.5 rounded-full capitalize ${q.difficulty === 'easy' ? 'text-emerald-400 bg-emerald-500/10' : q.difficulty === 'medium' ? 'text-amber-400 bg-amber-500/10' : 'text-red-400 bg-red-500/10'}`}>{q.difficulty}</span>
      </div>
      <p className="text-xs text-ghost mb-2">{q.question}</p>
      <div className="space-y-0.5">
        <p className="text-[10px] text-emerald-400">✓ {q.correct_answer}</p>
        {q.incorrect_answers.slice(0, 3).map((a, i) => (
          <p key={i} className="text-[10px] text-dim-500">✗ {a}</p>
        ))}
      </div>
    </div>
  )
}

function renderAnimal(data: Record<string, unknown>) {
  const url = data.image_url as string
  if (!url) return <p className="text-dim-400 text-sm">No image found</p>
  return (
    <div className="flex justify-center">
      <img src={url} alt="Random animal" className="w-full h-28 rounded-lg object-cover bg-white/5" />
    </div>
  )
}

function renderJokeApi(data: Record<string, unknown>) {
  const joke = data.joke as string
  const category = data.category as string
  if (!joke) return <p className="text-dim-400 text-sm">No joke found</p>
  return (
    <div>
      {category && <span className="text-[9px] px-1.5 py-0.5 rounded-full bg-white/5 text-cyan-400 mb-1 inline-block">{category}</span>}
      <p className="text-sm text-ghost leading-relaxed">{joke}</p>
    </div>
  )
}

function renderRickMorty(data: Record<string, unknown>) {
  return (
    <div className="flex gap-2 items-start">
      {(data.image as string) && <img src={data.image as string} alt={data.name as string} className="w-14 h-14 rounded-lg object-cover flex-shrink-0" />}
      <div className="min-w-0">
        <p className="text-sm font-bold text-ghost">{data.name as string}</p>
        <div className="flex gap-1.5 mt-0.5">
          <span className={`text-[9px] px-1.5 py-0.5 rounded-full ${data.status === 'Alive' ? 'text-emerald-400 bg-emerald-500/10' : data.status === 'Dead' ? 'text-red-400 bg-red-500/10' : 'text-dim-400 bg-white/5'}`}>{data.status as string}</span>
          <span className="text-[9px] px-1.5 py-0.5 rounded-full bg-white/5 text-dim-400">{data.species as string}</span>
          <span className="text-[9px] px-1.5 py-0.5 rounded-full bg-white/5 text-dim-400">{data.gender as string}</span>
        </div>
        <p className="text-[10px] text-dim-500 mt-0.5">{data.origin as string} → {data.location as string}</p>
      </div>
    </div>
  )
}

function renderStarWars(data: Record<string, unknown>) {
  return (
    <div className="text-center">
      <p className="text-lg font-bold text-ghost">{data.name as string}</p>
      <div className="grid grid-cols-2 gap-x-3 gap-y-0.5 mt-2 text-[10px]">
        <div className="flex justify-between"><span className="text-dim-400">Height</span><span className="text-ghost">{data.height as string}cm</span></div>
        <div className="flex justify-between"><span className="text-dim-400">Mass</span><span className="text-ghost">{data.mass as string}kg</span></div>
        <div className="flex justify-between"><span className="text-dim-400">Hair</span><span className="text-ghost capitalize">{data.hair_color as string}</span></div>
        <div className="flex justify-between"><span className="text-dim-400">Eyes</span><span className="text-ghost capitalize">{data.eye_color as string}</span></div>
        <div className="flex justify-between"><span className="text-dim-400">Born</span><span className="text-ghost">{data.birth_year as string}</span></div>
        <div className="flex justify-between"><span className="text-dim-400">Gender</span><span className="text-ghost capitalize">{data.gender as string}</span></div>
        <div className="flex justify-between"><span className="text-dim-400">Films</span><span className="text-ghost">{data.film_count as number}</span></div>
      </div>
    </div>
  )
}

function renderNumberFact(data: Record<string, unknown>) {
  return <p className="text-sm text-ghost leading-relaxed">{(data.fact as string) || 'No fact found'}</p>
}

// ─── Component ──────────────────────────────────────────────────────────────

export function PublicApisPage(): JSX.Element {
  const [results, setResults] = useState<Record<string, Record<string, unknown>>>({})
  const [loading, setLoading] = useState<Record<string, boolean>>({})
  const [searchInputs, setSearchInputs] = useState<Record<string, string>>({})
  const [copiedId, setCopiedId] = useState<string | null>(null)
  // Currency converter specific inputs
  const [convertAmount, setConvertAmount] = useState('1')
  const [convertFrom, setConvertFrom] = useState('USD')
  const [convertTo, setConvertTo] = useState('EUR')

  const fetchApi = useCallback(async (card: ApiCard, query?: string) => {
    setLoading((prev) => ({ ...prev, [card.id]: true }))

    let endpoint = card.endpoint
    if (card.id === 'currency-convert') {
      // Build endpoint from converter-specific inputs
      const amt = parseFloat(convertAmount) || 1
      endpoint = `/api/free/currency/convert?amount=${amt}&from=${encodeURIComponent(convertFrom.toUpperCase())}&to=${encodeURIComponent(convertTo.toUpperCase())}`
    } else if (query) {
      endpoint += encodeURIComponent(query)
    }

    try {
      const data = await api<Record<string, unknown>>(endpoint)
      setResults((prev) => ({ ...prev, [card.id]: data || { status: 'error', message: 'No response' } }))
    } catch {
      setResults((prev) => ({ ...prev, [card.id]: { status: 'error', message: 'Request failed' } }))
    }
    setLoading((prev) => ({ ...prev, [card.id]: false }))
  }, [convertAmount, convertFrom, convertTo])

  const handleCopy = useCallback(async (text: string, id: string) => {
    try {
      await navigator.clipboard.writeText(text)
      setCopiedId(id)
      setTimeout(() => setCopiedId(null), 2000)
    } catch { /* ignore */ }
  }, [])

  return (
    <div className="p-6 max-w-7xl mx-auto space-y-6">
      <motion.div initial={{ opacity: 0, y: -10 }} animate={{ opacity: 1, y: 0 }}>
        <h1 className="text-xl font-orbitron font-bold text-ghost tracking-wider flex items-center gap-3">
          <Zap className="w-5 h-5 text-cyan-400" />
          PUBLIC APIS
        </h1>
        <p className="text-sm font-rajdhani text-dim-400 mt-1">
          Free, no-authentication-required APIs for everything from dictionaries to currency conversion
        </p>
      </motion.div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {API_CARDS.map((card, idx) => {
          const isLoading = loading[card.id]
          const data = results[card.id]
          const searchVal = searchInputs[card.id] || ''
          const quickSearches = COPY_QUICK[card.id]

          return (
            <motion.div
              key={card.id}
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: idx * 0.03 }}
              className="glass-card-hover relative group"
            >
              {/* Header */}
              <div className="flex items-start justify-between mb-3">
                <div className="flex items-center gap-2">
                  <div className={`w-8 h-8 rounded-lg bg-gradient-to-br ${card.color} flex items-center justify-center`}>
                    <card.icon className="w-4 h-4 text-white" />
                  </div>
                  <div>
                    <h3 className="text-sm font-rajdhani font-semibold text-ghost">{card.title}</h3>
                    <p className="text-[10px] font-exo text-dim-500">{card.category}</p>
                  </div>
                </div>
                <button
                  onClick={() => fetchApi(card, searchVal || undefined)}
                  disabled={isLoading}
                  className="p-1.5 rounded-md text-dim-400 hover:text-cyan-300 hover:bg-white/5 transition-all"
                  title="Fetch data"
                >
                  {isLoading ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <RefreshCw className="w-3.5 h-3.5" />}
                </button>
              </div>

              {/* Description */}
              <p className="text-xs font-exo text-dim-400 mb-3">{card.description}</p>

              {/* Search / Quick actions for cards that need input */}
              {quickSearches && (
                <div className="flex flex-wrap gap-1 mb-3">
                  {quickSearches.map((qs) => (
                    <button
                      key={qs.label}
                      onClick={() => {
                        setSearchInputs((prev) => ({ ...prev, [card.id]: qs.query }))
                        fetchApi(card, qs.query)
                      }}
                      className="text-[9px] px-2 py-0.5 rounded-full bg-white/5 text-dim-400 hover:text-cyan-300 hover:bg-white/10 transition-all"
                    >
                      {qs.label}
                    </button>
                  ))}
                </div>
              )}

              {/* Currency converter inputs */}
              {card.id === 'currency-convert' && (
                <div className="flex flex-col gap-1.5 mb-3">
                  <div className="flex gap-1.5">
                    <input
                      type="number"
                      value={convertAmount}
                      onChange={(e) => setConvertAmount(e.target.value)}
                      placeholder="Amount"
                      className="input-cyan text-xs w-16"
                      min="0"
                      step="any"
                    />
                    <input
                      type="text"
                      value={convertFrom}
                      onChange={(e) => setConvertFrom(e.target.value.toUpperCase())}
                      placeholder="USD"
                      className="input-cyan text-xs w-14 uppercase"
                      maxLength={3}
                    />
                    <span className="text-dim-500 self-center text-xs">→</span>
                    <input
                      type="text"
                      value={convertTo}
                      onChange={(e) => setConvertTo(e.target.value.toUpperCase())}
                      placeholder="EUR"
                      className="input-cyan text-xs w-14 uppercase"
                      maxLength={3}
                    />
                    <button
                      onClick={() => fetchApi(card)}
                      disabled={isLoading}
                      className="btn-cyan text-xs px-2"
                    >
                      <Search className="w-3 h-3" />
                    </button>
                  </div>
                  {convertAmount && convertFrom && convertTo && (
                    <div className="flex gap-1.5">
                      {[
                        { from: 'USD', to: 'EUR' },
                        { from: 'USD', to: 'INR' },
                        { from: 'EUR', to: 'GBP' },
                        { from: 'GBP', to: 'USD' },
                      ].map((pair) => (
                        <button
                          key={`${pair.from}-${pair.to}`}
                          onClick={() => {
                            setConvertAmount('1')
                            setConvertFrom(pair.from)
                            setConvertTo(pair.to)
                            setTimeout(() => fetchApi(card), 0)
                          }}
                          className="text-[9px] px-1.5 py-0.5 rounded-full bg-white/5 text-dim-400 hover:text-cyan-300 hover:bg-white/10 transition-all"
                        >
                          {pair.from}→{pair.to}
                        </button>
                      ))}
                    </div>
                  )}
                </div>
              )}

              {/* Text input for cards that need a query */}
              {['dictionary', 'books', 'qrcode', 'email-validate', 'age', 'gender', 'nationality', 'holidays', 'cocktail', 'number-fact', 'steam-deals'].includes(card.id) && (
                <div className="flex gap-1.5 mb-3">
                  <input
                    type="text"
                    value={searchVal}
                    onChange={(e) => setSearchInputs((prev) => ({ ...prev, [card.id]: e.target.value }))}
                    onKeyDown={(e) => e.key === 'Enter' && fetchApi(card, searchVal)}
                    placeholder={
                      card.id === 'email-validate' ? 'email@example.com' :
                      card.id === 'qrcode' ? 'Text or URL...' :
                      card.id === 'holidays' ? 'Country code (US)...' :
                      card.id === 'age' || card.id === 'gender' || card.id === 'nationality' ? 'First name...' :
                      'Search...'
                    }
                    className="input-cyan text-xs flex-1 min-w-0"
                  />
                  <button
                    onClick={() => fetchApi(card, searchVal)}
                    disabled={isLoading || !searchVal.trim()}
                    className="btn-cyan text-xs px-2.5"
                  >
                    <Search className="w-3 h-3" />
                  </button>
                </div>
              )}

              {/* Results area */}
              <div className="min-h-[60px]">
                {isLoading ? (
                  <div className="flex items-center justify-center h-12">
                    <Loader2 className="w-4 h-4 animate-spin text-cyan-400" />
                  </div>
                ) : data ? (
                  data.status === 'error' ? (
                    <p className="text-xs text-red-400">{(data.message as string) || 'Error'}</p>
                  ) : (
                    renderResult(card.id, data)
                  )
                ) : (
                  <p className="text-xs text-dim-500 italic">Click refresh to fetch data</p>
                )}
              </div>

              {/* Copy result button */}
              {data && data.status === 'ok' && (
                <button
                  onClick={() => handleCopy(JSON.stringify(data, null, 2), card.id)}
                  className="absolute top-2 right-8 p-1 rounded text-dim-500 hover:text-ghost opacity-0 group-hover:opacity-100 transition-all"
                  title="Copy JSON"
                >
                  {copiedId === card.id ? <Check className="w-3 h-3 text-emerald-400" /> : <Copy className="w-3 h-3" />}
                </button>
              )}
            </motion.div>
          )
        })}
      </div>

      {/* Footer attribution */}
      <motion.p
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ delay: 0.5 }}
        className="text-[10px] text-dim-500 text-center font-exo"
      >
        Powered by{' '}
        <a href="https://github.com/public-apis/public-apis" target="_blank" rel="noopener noreferrer" className="text-cyan-400 hover:underline inline-flex items-center gap-0.5">
          public-apis <ExternalLink className="w-2.5 h-2.5" />
        </a>
        {' · '}All APIs are free and require no authentication
      </motion.p>
    </div>
  )
}
