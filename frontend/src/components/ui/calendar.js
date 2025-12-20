import * as React from "react"
import { ChevronLeft, ChevronRight } from "lucide-react"
import { cn } from "../../lib/utils"
import { buttonVariants } from "./button"

function Calendar({
  mode = "single",
  selected,
  onSelect,
  defaultMonth,
  className,
  minDate,
  maxDate,
  ...props
}) {
  const [currentMonth, setCurrentMonth] = React.useState(() => {
    return defaultMonth || selected || new Date()
  })

  // Sync currentMonth when defaultMonth or selected changes
  React.useEffect(() => {
    if (defaultMonth) {
      setCurrentMonth(defaultMonth)
    } else if (selected) {
      setCurrentMonth(selected)
    }
  }, [defaultMonth, selected])

  const month = currentMonth.getMonth()
  const year = currentMonth.getFullYear()

  // Get first day of month and number of days
  const firstDay = new Date(year, month, 1)
  const lastDay = new Date(year, month + 1, 0)
  const daysInMonth = lastDay.getDate()
  const startingDayOfWeek = firstDay.getDay()

  // Get days of previous month to fill the first week
  const prevMonth = new Date(year, month - 1, 0)
  const daysInPrevMonth = prevMonth.getDate()

  const days = []
  
  // Add previous month's trailing days
  for (let i = startingDayOfWeek - 1; i >= 0; i--) {
    days.push({
      date: new Date(year, month - 1, daysInPrevMonth - i),
      isCurrentMonth: false,
    })
  }

  // Add current month's days
  for (let i = 1; i <= daysInMonth; i++) {
    days.push({
      date: new Date(year, month, i),
      isCurrentMonth: true,
    })
  }

  // Add next month's leading days to fill the last week
  const remainingDays = 42 - days.length // 6 weeks * 7 days
  for (let i = 1; i <= remainingDays; i++) {
    days.push({
      date: new Date(year, month + 1, i),
      isCurrentMonth: false,
    })
  }

  const weekDays = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]
  const monthNames = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December"
  ]

  const isSelected = (date) => {
    if (!selected) return false
    return (
      date.getDate() === selected.getDate() &&
      date.getMonth() === selected.getMonth() &&
      date.getFullYear() === selected.getFullYear()
    )
  }

  const isToday = (date) => {
    const today = new Date()
    return (
      date.getDate() === today.getDate() &&
      date.getMonth() === today.getMonth() &&
      date.getFullYear() === today.getFullYear()
    )
  }

  const isFutureDate = (date) => {
    // Only check future dates if maxDate is set (for filter by date)
    if (maxDate) {
      const max = new Date(maxDate)
      max.setHours(23, 59, 59, 999)
      const compareDate = new Date(date)
      compareDate.setHours(0, 0, 0, 0)
      return compareDate > max
    }
    return false
  }

  const isPastDate = (date) => {
    // Only check past dates if minDate is set (for due date)
    if (minDate) {
      const min = new Date(minDate)
      min.setHours(0, 0, 0, 0)
      const compareDate = new Date(date)
      compareDate.setHours(0, 0, 0, 0)
      return compareDate < min
    }
    return false
  }

  const isDisabledDate = (date) => {
    return isFutureDate(date) || isPastDate(date)
  }

  const handleDateClick = (date) => {
    if (onSelect && !isDisabledDate(date)) {
      onSelect(date)
    }
  }

  const goToPreviousMonth = () => {
    if (canGoToPreviousMonth) {
      setCurrentMonth(new Date(year, month - 1, 1))
    }
  }

  // Check if we should disable next month button (when maxDate is set)
  const nextMonthFirstDay = new Date(year, month + 1, 1)
  nextMonthFirstDay.setHours(0, 0, 0, 0)
  const canGoToNextMonth = maxDate ? nextMonthFirstDay <= new Date(maxDate) : true
  
  // Check if we should disable previous month button (when minDate is set)
  const prevMonthLastDay = new Date(year, month, 0)
  prevMonthLastDay.setHours(23, 59, 59, 999)
  const canGoToPreviousMonth = minDate ? prevMonthLastDay >= new Date(minDate) : true

  const goToNextMonth = () => {
    if (canGoToNextMonth) {
      setCurrentMonth(new Date(year, month + 1, 1))
    }
  }

  return (
    <div className={cn("p-2", className)} {...props}>
      <div className="flex items-center justify-between mb-2">
        <button
          type="button"
          onClick={goToPreviousMonth}
          disabled={!canGoToPreviousMonth}
          className={cn(
            "h-6 w-6 p-0 bg-transparent border-0 hover:bg-accent rounded-md flex items-center justify-center",
            canGoToPreviousMonth ? "cursor-pointer" : "cursor-not-allowed opacity-30"
          )}
        >
          <ChevronLeft className="h-3.5 w-3.5 text-foreground" />
        </button>
        <div className="text-xs font-medium">
          {monthNames[month]} {year}
        </div>
        <button
          type="button"
          onClick={goToNextMonth}
          disabled={!canGoToNextMonth}
          className={cn(
            "h-6 w-6 p-0 bg-transparent border-0 hover:bg-accent rounded-md flex items-center justify-center",
            canGoToNextMonth ? "cursor-pointer" : "cursor-not-allowed opacity-30"
          )}
        >
          <ChevronRight className="h-3.5 w-3.5 text-foreground" />
        </button>
      </div>
      <div className="grid grid-cols-7 gap-0.5 mb-1.5">
        {weekDays.map((day) => (
          <div
            key={day}
            className="text-muted-foreground rounded-md w-7 font-normal text-xs text-center"
          >
            {day}
          </div>
        ))}
      </div>
      <div className="grid grid-cols-7 gap-0.5">
        {days.map((day, idx) => {
          const isSelectedDay = isSelected(day.date)
          const isTodayDay = isToday(day.date)
          const isDisabled = isDisabledDate(day.date)
          return (
            <button
              key={idx}
              type="button"
              onClick={() => handleDateClick(day.date)}
              disabled={isDisabled}
              className={cn(
                buttonVariants({ variant: "ghost" }),
                "h-7 w-7 p-0 font-normal text-xs",
                !day.isCurrentMonth && "text-muted-foreground opacity-50",
                isDisabled && "opacity-30 cursor-not-allowed",
                isSelectedDay &&
                  "bg-primary text-primary-foreground hover:bg-primary hover:text-primary-foreground focus:bg-primary focus:text-primary-foreground",
                !isSelectedDay && !isDisabled && isTodayDay && "bg-accent text-accent-foreground",
                !isSelectedDay && !isDisabled && !isTodayDay && "hover:bg-accent hover:text-accent-foreground"
              )}
            >
              {day.date.getDate()}
            </button>
          )
        })}
      </div>
    </div>
  )
}

Calendar.displayName = "Calendar"

export { Calendar }







