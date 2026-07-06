import { useEffect, useState } from 'react'

interface ClockData {
  time: string
  date: string
  dayOfWeek: string
}

const DAYS = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday']
const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

function getClockData(): ClockData {
  const now = new Date()
  const hh = String(now.getHours()).padStart(2, '0')
  const mm = String(now.getMinutes()).padStart(2, '0')
  const ss = String(now.getSeconds()).padStart(2, '0')
  return {
    time: `${hh}:${mm}:${ss}`,
    date: `${DAYS[now.getDay()]}, ${MONTHS[now.getMonth()]} ${now.getDate()}`,
    dayOfWeek: DAYS[now.getDay()],
  }
}

export function OverlayClock(): JSX.Element {
  const [clock, setClock] = useState(getClockData)

  useEffect(() => {
    const interval = setInterval(() => setClock(getClockData()), 1000)
    return () => clearInterval(interval)
  }, [])

  return (
    <div className="widget-panel clock-widget">
      <div className="widget-label">Clock</div>
      <div className="clock-time">{clock.time}</div>
      <div className="clock-date">{clock.date}</div>
    </div>
  )
}
