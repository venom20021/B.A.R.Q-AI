// ─── Content Types for Dynamic Content Panel ───────────────────────────────
// These define the shape of structured data that the Python backend broadcasts
// via WebSocket as `rich_content` events.

export interface FlightResult {
  airline: string
  departure: string
  arrival: string
  duration: string
  stops: string
  price: string
  link?: string
}

export interface FlightContent {
  type: 'flights'
  origin: string
  destination: string
  date: string
  results: FlightResult[]
  summary?: string
}

export interface YouTubeVideo {
  title: string
  channel: string
  views: string
  duration: string
  url: string
  thumbnail?: string
}

export interface YouTubeContent {
  type: 'youtube'
  query: string
  results: YouTubeVideo[]
  summary?: string
}

export interface NewsArticle {
  title: string
  source: string
  url: string
  published?: string
  snippet?: string
}

export interface NewsContent {
  type: 'news'
  topic: string
  results: NewsArticle[]
  summary?: string
}

export interface ReminderItem {
  id: number
  title: string
  message: string
  due_at: string
  status: string
}

export interface ReminderContent {
  type: 'reminders'
  results: ReminderItem[]
  summary?: string
}

export interface GenericContent {
  type: 'generic'
  title: string
  items: Array<{
    label: string
    value: string
    detail?: string
  }>
  summary?: string
}

export type RichContent =
  | FlightContent
  | YouTubeContent
  | NewsContent
  | ReminderContent
  | GenericContent

export interface RichContentEvent {
  type: 'rich_content'
  content: RichContent
}
