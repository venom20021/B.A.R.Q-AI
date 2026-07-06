type StocksData = {
  ticker: string
  company: string
  current_price: number
  change_percent: number
  loaded: boolean
} | null | undefined

interface OverlayStocksProps {
  stocks: StocksData
}

export function OverlayStocks({ stocks }: OverlayStocksProps): JSX.Element {
  if (!stocks || !stocks.loaded) {
    return (
      <div className="widget-panel stocks-widget">
        <div className="widget-label">Stocks</div>
        <div className="widget-loading">
          <div className="widget-loading-dot" />
          <div className="widget-loading-dot" />
          <div className="widget-loading-dot" />
        </div>
      </div>
    )
  }

  const isPositive = stocks.change_percent >= 0

  return (
    <div className="widget-panel stocks-widget">
      <div className="widget-label">{stocks.company?.slice(0, 14) || stocks.ticker}</div>
      <div className="stocks-ticker">{stocks.ticker}</div>
      <div className="stocks-price-row">
        <span className="stocks-price">
          ${stocks.current_price?.toFixed(2)}
        </span>
        <span className={`stocks-change ${isPositive ? 'positive' : 'negative'}`}>
          {isPositive ? '+' : ''}{(stocks.change_percent * 100).toFixed(2)}%
        </span>
      </div>
    </div>
  )
}
