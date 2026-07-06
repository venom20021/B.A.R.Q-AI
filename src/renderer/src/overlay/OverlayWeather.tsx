type WeatherData = {
  city: string
  temperature_c: number
  description: string
  icon: string
  humidity: number
  loaded: boolean
} | null | undefined

interface OverlayWeatherProps {
  weather: WeatherData
}

const ICON_BASE = 'https://openweathermap.org/img/wn'

export function OverlayWeather({ weather }: OverlayWeatherProps): JSX.Element {
  if (!weather || !weather.loaded) {
    return (
      <div className="widget-panel weather-widget">
        <div className="widget-label">Weather</div>
        <div className="widget-loading">
          <div className="widget-loading-dot" />
          <div className="widget-loading-dot" />
          <div className="widget-loading-dot" />
        </div>
      </div>
    )
  }

  return (
    <div className="widget-panel weather-widget">
      <div className="widget-label">{weather.city}</div>
      <div className="weather-row">
        <img
          className="weather-icon"
          src={`${ICON_BASE}/${weather.icon}@2x.png`}
          alt={weather.description}
          draggable={false}
        />
        <div>
          <div className="weather-temp">{Math.round(weather.temperature_c)}°</div>
          <div className="weather-desc">{weather.description}</div>
        </div>
      </div>
    </div>
  )
}
