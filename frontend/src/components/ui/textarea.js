import * as React from "react"
import { cn } from "../../lib/utils"

const Textarea = React.forwardRef(({ className, ...props }, ref) => {
  return (
    <textarea
      className={cn(
        "flex min-h-[80px] w-full rounded-md border border-input bg-transparent px-3 py-2 text-xs ring-offset-background placeholder:text-gray-400 focus-visible:outline-none focus-visible:ring-0 disabled:cursor-not-allowed disabled:opacity-50 hover:bg-muted/50 transition-colors",
        className
      )}
      ref={ref}
      {...props}
    />
  )
})
Textarea.displayName = "Textarea"

export { Textarea }



