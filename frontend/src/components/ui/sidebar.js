import * as React from "react"
import { Slot } from "@radix-ui/react-slot"
import { cva } from "class-variance-authority"
import * as CollapsiblePrimitive from "@radix-ui/react-collapsible"
import { PanelLeft } from "lucide-react"
import { cn } from "../../lib/utils"
import { Button } from "./button"
import { Separator } from "./separator"
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "./tooltip"
import { Sheet, SheetContent } from "./sheet"

const SIDEBAR_COOKIE_NAME = "sidebar:state"
const SIDEBAR_COOKIE_MAX_AGE = 60 * 60 * 24 * 7
const SIDEBAR_WIDTH = "225px"
const SIDEBAR_WIDTH_ICON = "3rem"
const SIDEBAR_WIDTH_MOBILE = "18rem"
const SIDEBAR_KEYBOARD_SHORTCUT = "b"

const SidebarContext = React.createContext({
  state: "expanded",
  open: true,
  setOpen: (open) => {},
  openMobile: false,
  setOpenMobile: (open) => {},
  isMobile: false,
  toggleSidebar: () => {},
})

function useSidebar() {
  const context = React.useContext(SidebarContext)
  if (!context) {
    throw new Error("useSidebar must be used within a SidebarProvider.")
  }
  return context
}

const SidebarProvider = React.forwardRef(
  (
    {
      children,
      defaultOpen = true,
      open: openProp,
      onOpenChange: setOpenProp,
      ...props
    },
    ref
  ) => {
    const [openMobile, setOpenMobile] = React.useState(false)
    const [internalOpen, setInternalOpen] = React.useState(() => {
      // Initialize from cookie if available
      if (typeof document !== "undefined") {
        const cookie = document.cookie
          .split("; ")
          .find((row) => row.startsWith(`${SIDEBAR_COOKIE_NAME}=`))
        const cookieValue = cookie?.split("=")[1]
        if (cookieValue === "true" || cookieValue === "false") {
          return cookieValue === "true"
        }
      }
      return defaultOpen
    })

    // Use controlled value if provided, otherwise use internal state
    const open = openProp !== undefined ? openProp : internalOpen

    const setOpen = React.useCallback(
      (value) => {
        const openState = typeof value === "function" ? value(open) : value
        if (setOpenProp) {
          setOpenProp(openState)
        } else {
          setInternalOpen(openState)
        }

        // This sets the cookie to keep the sidebar state.
        if (typeof document !== "undefined") {
          document.cookie = `${SIDEBAR_COOKIE_NAME}=${openState}; path=/; max-age=${SIDEBAR_COOKIE_MAX_AGE}`
        }
      },
      [setOpenProp, open]
    )

    // Handle mobile
    const [isMobile, setIsMobile] = React.useState(() => {
      if (typeof window === "undefined") return false
      return window.innerWidth < 768
    })

    React.useEffect(() => {
      const handleResize = () => {
        const mobile = window.innerWidth < 768
        setIsMobile(mobile)
        if (!mobile) {
          setOpenMobile(false)
        }
      }
      window.addEventListener("resize", handleResize)
      return () => window.removeEventListener("resize", handleResize)
    }, [])

    // Keyboard shortcut
    React.useEffect(() => {
      const handleKeyDown = (event) => {
        if (
          event.key === SIDEBAR_KEYBOARD_SHORTCUT &&
          (event.metaKey || event.ctrlKey)
        ) {
          event.preventDefault()
          setOpen((open) => !open)
        }
      }
      window.addEventListener("keydown", handleKeyDown)
      return () => window.removeEventListener("keydown", handleKeyDown)
    }, [setOpen])

    const toggleSidebar = React.useCallback(() => {
      return setOpen((open) => !open)
    }, [setOpen])

    const state = open ? "expanded" : "collapsed"

    const contextValue = React.useMemo(
      () => ({
        state,
        open,
        setOpen,
        isMobile,
        openMobile,
        setOpenMobile,
        toggleSidebar,
      }),
      [state, open, setOpen, isMobile, openMobile, setOpenMobile, toggleSidebar]
    )

    return (
      <SidebarContext.Provider value={contextValue} {...props}>
        <TooltipProvider delayDuration={0}>
          <div className="flex h-full w-full">
            {children}
          </div>
        </TooltipProvider>
      </SidebarContext.Provider>
    )
  }
)
SidebarProvider.displayName = "SidebarProvider"

const Sidebar = React.forwardRef(
  (
    {
      side = "left",
      variant = "sidebar",
      collapsible = "offcanvas",
      className,
      children,
      ...props
    },
    ref
  ) => {
    // Check if we're inside an existing provider by reading context directly
    const contextValue = React.useContext(SidebarContext)
    const hasProvider = contextValue && contextValue.state !== undefined

    // If we have an existing provider, use it directly
    if (hasProvider) {
      const { isMobile, openMobile, setOpenMobile } = contextValue

      if (isMobile) {
        return (
          <Sheet open={openMobile} onOpenChange={setOpenMobile} {...props}>
            <SheetContent
              data-sidebar="sidebar"
              data-mobile="true"
              className="w-[--sidebar-width] p-0 [&>button]:hidden"
              style={
                {
                  "--sidebar-width": SIDEBAR_WIDTH_MOBILE,
                }
              }
            >
              <SidebarInner side={side} variant={variant} collapsible={collapsible}>
                {children}
              </SidebarInner>
            </SheetContent>
          </Sheet>
        )
      }

      return (
        <SidebarInner
          ref={ref}
          side={side}
          variant={variant}
          collapsible={collapsible}
          className={className}
          {...props}
        >
          {children}
        </SidebarInner>
      )
    }

    // No existing provider, create our own
    if (collapsible === "icon") {
      return (
        <SidebarProvider>
          <SidebarInner
            ref={ref}
            side={side}
            variant={variant}
            collapsible={collapsible}
            className={className}
            {...props}
          >
            {children}
          </SidebarInner>
        </SidebarProvider>
      )
    }

    return (
      <SidebarProvider>
        <SidebarInner
          ref={ref}
          side={side}
          variant={variant}
          collapsible={collapsible}
          className={className}
          {...props}
        >
          {children}
        </SidebarInner>
      </SidebarProvider>
    )
  }
)
Sidebar.displayName = "Sidebar"

const SidebarInner = React.forwardRef(
  (
    {
      side = "left",
      variant = "sidebar",
      collapsible = "offcanvas",
      className,
      children,
      ...props
    },
    ref
  ) => {
    const { state, open } = useSidebar()

    return (
      <aside
        ref={ref}
        data-sidebar="sidebar"
        data-state={state}
        data-collapsible={state === "collapsed" ? collapsible : ""}
        data-side={side}
        data-variant={variant}
        className={cn(
          "group/sidebar-wrapper flex h-full flex-col bg-transparent text-sidebar-foreground transition-all duration-300 ease-in-out",
          "data-[collapsible=icon]:w-[--sidebar-width-icon]",
          "data-[state=collapsed][data-collapsible=offcanvas]:w-0 data-[state=collapsed][data-collapsible=offcanvas]:min-w-0 data-[state=collapsed][data-collapsible=offcanvas]:overflow-hidden data-[state=collapsed][data-collapsible=offcanvas]:border-0",
          className
        )}
        style={
          state === "collapsed" && collapsible === "offcanvas"
            ? {
                width: "0",
                minWidth: "0",
                maxWidth: "0",
                "--sidebar-width": SIDEBAR_WIDTH,
                "--sidebar-width-icon": SIDEBAR_WIDTH_ICON,
              }
            : {
                width: SIDEBAR_WIDTH,
                minWidth: SIDEBAR_WIDTH,
                maxWidth: SIDEBAR_WIDTH,
                "--sidebar-width": SIDEBAR_WIDTH,
                "--sidebar-width-icon": SIDEBAR_WIDTH_ICON,
              }
        }
        {...props}
      >
        {children}
      </aside>
    )
  }
)
SidebarInner.displayName = "SidebarInner"

const SidebarRail = React.forwardRef(({ ...props }, ref) => {
  return (
    <div
      ref={ref}
      data-sidebar="rail"
      {...props}
      className={cn(
        "absolute inset-y-0 z-50 hidden w-1 -translate-x-full transition-all group-data-[side=left]/sidebar-wrapper:left-0 group-data-[side=right]/sidebar-wrapper:right-0 group-data-[collapsible=icon]/sidebar-wrapper:translate-x-0 group-data-[collapsible=icon]/sidebar-wrapper:bg-sidebar-border",
        "group-data-[collapsible=icon]/sidebar-wrapper:hover:w-2",
        "group-data-[side=left]/sidebar-wrapper:group-hover/sidebar-wrapper:translate-x-0",
        "group-data-[side=right]/sidebar-wrapper:group-hover/sidebar-wrapper:translate-x-0"
      )}
    />
  )
})
SidebarRail.displayName = "SidebarRail"

const SidebarInset = React.forwardRef(({ className, ...props }, ref) => {
  return (
    <div
      ref={ref}
      className={cn(
        "relative flex w-full flex-1 flex-col bg-background",
        className
      )}
      {...props}
    />
  )
})
SidebarInset.displayName = "SidebarInset"

const SidebarInput = React.forwardRef(({ className, ...props }, ref) => {
  return (
    <input
      ref={ref}
      data-sidebar="input"
      className={cn(
        "flex h-8 w-full rounded-md border border-sidebar-border bg-sidebar-accent px-2 py-1 text-sm text-sidebar-accent-foreground ring-offset-sidebar file:border-0 file:bg-transparent file:text-sm file:font-medium file:text-sidebar-foreground placeholder:text-sidebar-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sidebar-ring focus-visible:ring-offset-2 focus-visible:ring-offset-sidebar disabled:cursor-not-allowed disabled:opacity-50",
        className
      )}
      {...props}
    />
  )
})
SidebarInput.displayName = "SidebarInput"

const SidebarHeader = React.forwardRef(({ className, ...props }, ref) => {
  return (
    <div
      ref={ref}
      data-sidebar="header"
      className={cn(
        "flex h-16 shrink-0 items-center gap-2 pl-4 pr-4",
        className
      )}
      {...props}
    />
  )
})
SidebarHeader.displayName = "SidebarHeader"

const SidebarFooter = React.forwardRef(({ className, ...props }, ref) => {
  return (
    <div
      ref={ref}
      data-sidebar="footer"
      className={cn(
        "flex h-16 shrink-0 items-center gap-2 pl-4 pr-4",
        className
      )}
      {...props}
    />
  )
})
SidebarFooter.displayName = "SidebarFooter"

const SidebarSeparator = React.forwardRef(
  ({ className, ...props }, ref) => {
    return (
      <Separator
        ref={ref}
        data-sidebar="separator"
        className={cn("bg-sidebar-border", className)}
        {...props}
      />
    )
  }
)
SidebarSeparator.displayName = "SidebarSeparator"

const SidebarContent = React.forwardRef(({ className, ...props }, ref) => {
  return (
    <div
      ref={ref}
      data-sidebar="content"
      className={cn(
        "flex min-h-0 flex-1 flex-col gap-2 overflow-auto pl-4 pr-4 group-data-[collapsible=icon]:overflow-hidden",
        className
      )}
      {...props}
    />
  )
})
SidebarContent.displayName = "SidebarContent"

const SidebarGroup = React.forwardRef(({ className, ...props }, ref) => {
  return (
    <div
      ref={ref}
      data-sidebar="group"
      className={cn("relative flex w-full min-w-0 flex-col p-2", className)}
      {...props}
    />
  )
})
SidebarGroup.displayName = "SidebarGroup"

const SidebarGroupLabel = React.forwardRef(({ className, asChild = false, ...props }, ref) => {
  const Comp = asChild ? Slot : "div"
  return (
    <Comp
      ref={ref}
      data-sidebar="group-label"
      className={cn(
        "duration-200 flex h-8 shrink-0 items-center rounded-md px-2 text-xs font-medium text-sidebar-foreground/70 outline-none ring-sidebar-ring transition-[margin,opa] ease-linear focus-visible:ring-2 [&>svg]:size-4 [&>svg]:shrink-0",
        "group-data-[collapsible=icon]:-mt-8 group-data-[collapsible=icon]:opacity-0",
        className
      )}
      {...props}
    />
  )
})
SidebarGroupLabel.displayName = "SidebarGroupLabel"

const SidebarGroupAction = React.forwardRef(
  ({ className, asChild = false, ...props }, ref) => {
    const Comp = asChild ? Slot : "button"
    return (
      <Comp
        ref={ref}
        data-sidebar="group-action"
        className={cn(
          "absolute right-3 top-3.5 flex aspect-square w-5 items-center justify-center rounded-md p-0 text-sidebar-foreground outline-none ring-sidebar-ring transition-transform hover:bg-sidebar-accent hover:text-sidebar-accent-foreground focus-visible:ring-2 [&>svg]:size-4 [&>svg]:shrink-0",
          "group-data-[collapsible=icon]:hidden",
          className
        )}
        {...props}
      />
    )
  }
)
SidebarGroupAction.displayName = "SidebarGroupAction"

const SidebarGroupContent = React.forwardRef(({ className, ...props }, ref) => {
  return (
    <div
      ref={ref}
      data-sidebar="group-content"
      className={cn("w-full text-sm", className)}
      {...props}
    />
  )
})
SidebarGroupContent.displayName = "SidebarGroupContent"

const SidebarMenu = React.forwardRef(({ className, ...props }, ref) => {
  return (
    <ul
      ref={ref}
      data-sidebar="menu"
      className={cn("flex w-full min-w-0 flex-col gap-1", className)}
      {...props}
    />
  )
})
SidebarMenu.displayName = "SidebarMenu"

const SidebarMenuItem = React.forwardRef(({ className, ...props }, ref) => {
  return (
    <li
      ref={ref}
      data-sidebar="menu-item"
      className={cn("group/menu-item relative", className)}
      {...props}
    />
  )
})
SidebarMenuItem.displayName = "SidebarMenuItem"

const sidebarMenuButtonVariants = cva(
  "peer/menu-button flex w-full items-center gap-2 overflow-hidden rounded-md p-2 text-left text-sm outline-none ring-sidebar-ring transition-[width,height,padding] hover:bg-sidebar-accent hover:text-sidebar-accent-foreground focus-visible:ring-2 active:bg-sidebar-accent active:text-sidebar-accent-foreground disabled:pointer-events-none disabled:opacity-50 group-has-[[data-sidebar=menu-action]]/menu-item:pr-8 aria-disabled:pointer-events-none aria-disabled:opacity-50 data-[active=true]:bg-sidebar-accent data-[active=true]:font-medium data-[active=true]:text-sidebar-accent-foreground data-[state=open]:hover:bg-sidebar-accent data-[state=open]:hover:text-sidebar-accent-foreground group-data-[collapsible=icon]:!size-8 group-data-[collapsible=icon]:!p-2 [&>span:last-child]:truncate [&>svg]:size-4 [&>svg]:shrink-0",
  {
    variants: {
      variant: {
        default: "hover:bg-sidebar-accent hover:text-sidebar-accent-foreground",
        outline:
          "bg-sidebar border border-sidebar-border hover:bg-sidebar-accent hover:text-sidebar-accent-foreground",
      },
      size: {
        default: "h-8 text-sm",
        sm: "h-7 text-xs",
        lg: "h-12 text-sm group-data-[collapsible=icon]:!size-12",
      },
    },
    defaultVariants: {
      variant: "default",
      size: "default",
    },
  }
)

const SidebarMenuButton = React.forwardRef(
  (
    {
      asChild = false,
      isActive = false,
      variant = "default",
      size = "default",
      tooltip,
      className,
      ...props
    },
    ref
  ) => {
    const Comp = asChild ? Slot : "button"
    const { isMobile, state } = useSidebar()
    const button = (
      <Comp
        ref={ref}
        data-sidebar="menu-button"
        data-size={size}
        data-active={isActive}
        className={cn(sidebarMenuButtonVariants({ variant, size }), className)}
        {...props}
      />
    )

    if (!tooltip) {
      return button
    }

    if (asChild) {
      return (
        <Tooltip>
          <TooltipTrigger asChild>{button}</TooltipTrigger>
          <TooltipContent
            side="right"
            align="center"
            hidden={state !== "collapsed" || isMobile}
            className="ml-2"
          >
            {tooltip}
          </TooltipContent>
        </Tooltip>
      )
    }

    return (
      <Tooltip>
        <TooltipTrigger asChild>{button}</TooltipTrigger>
        <TooltipContent
          side="right"
          align="center"
          hidden={state !== "collapsed" || isMobile}
          className="ml-2"
        >
          {tooltip}
        </TooltipContent>
      </Tooltip>
    )
  }
)
SidebarMenuButton.displayName = "SidebarMenuButton"

const SidebarMenuAction = React.forwardRef(
  (
    {
      asChild = false,
      showOnHover = false,
      className,
      ...props
    },
    ref
  ) => {
    const Comp = asChild ? Slot : "button"

    return (
      <Comp
        ref={ref}
        data-sidebar="menu-action"
        className={cn(
          "absolute right-1 top-1.5 flex aspect-square w-5 items-center justify-center rounded-md p-0 text-sidebar-foreground outline-none ring-sidebar-ring transition-transform hover:bg-sidebar-accent hover:text-sidebar-accent-foreground focus-visible:ring-2 peer-hover/menu-button:text-sidebar-accent-foreground [&>svg]:size-4 [&>svg]:shrink-0",
          "peer-data-[size=sm]/menu-button:top-1",
          "peer-data-[size=default]/menu-button:top-1.5",
          "peer-data-[size=lg]/menu-button:top-2.5",
          "group-data-[collapsible=icon]:hidden",
          "peer-data-[state=open]/menu-button:text-sidebar-accent-foreground",
          showOnHover &&
            "group-focus-within/menu-item:opacity-100 group-hover/menu-item:opacity-100 data-[state=open]:opacity-100 peer-data-[active=true]/menu-button:text-sidebar-accent-foreground opacity-0 transition-opacity",
          className
        )}
        {...props}
      />
    )
  }
)
SidebarMenuAction.displayName = "SidebarMenuAction"

const SidebarMenuBadge = React.forwardRef(({ className, ...props }, ref) => {
  return (
    <span
      ref={ref}
      data-sidebar="menu-badge"
      className={cn(
        "ml-auto flex size-5 shrink-0 items-center justify-center rounded-md text-xs font-medium tabular-nums text-sidebar-foreground group-data-[collapsible=icon]:hidden",
        className
      )}
      {...props}
    />
  )
})
SidebarMenuBadge.displayName = "SidebarMenuBadge"

const SidebarMenuSkeleton = React.forwardRef(
  ({ className, showIcon = false, ...props }, ref) => {
    // Random width between 50 to 100%.
    const width = React.useMemo(
      () => `${Math.floor(Math.random() * 50) + 50}%`,
      []
    )

    return (
      <li
        ref={ref}
        data-sidebar="menu-skeleton"
        className={cn("rounded-md h-8 flex gap-2 items-center px-2", className)}
        {...props}
      >
        {showIcon && (
          <div className="flex h-4 w-4 shrink-0 animate-pulse rounded-md bg-sidebar-primary/10" />
        )}
        <div
          className="h-4 animate-pulse rounded-md bg-sidebar-primary/10"
          style={{ width }}
        />
      </li>
    )
  }
)
SidebarMenuSkeleton.displayName = "SidebarMenuSkeleton"

const SidebarMenuSub = React.forwardRef(({ className, ...props }, ref) => {
  return (
    <ul
      ref={ref}
      data-sidebar="menu-sub"
      className={cn(
        "mx-3.5 flex min-w-0 translate-x-px flex-col gap-1 border-l border-sidebar-border px-2.5 py-0.5",
        "group-data-[collapsible=icon]:hidden",
        className
      )}
      {...props}
    />
  )
})
SidebarMenuSub.displayName = "SidebarMenuSub"

const SidebarMenuSubItem = React.forwardRef(({ ...props }, ref) => {
  return <li ref={ref} {...props} />
})
SidebarMenuSubItem.displayName = "SidebarMenuSubItem"

const SidebarMenuSubButton = React.forwardRef(
  (
    {
      asChild = false,
      size = "sm",
      isActive = false,
      className,
      ...props
    },
    ref
  ) => {
    const Comp = asChild ? Slot : "a"
    return (
      <Comp
        ref={ref}
        data-sidebar="menu-sub-button"
        data-size={size}
        data-active={isActive}
        className={cn(
          "flex h-7 min-w-0 -translate-x-px items-center gap-2 overflow-hidden rounded-md px-2 text-sidebar-foreground outline-none ring-sidebar-ring hover:bg-sidebar-accent hover:text-sidebar-accent-foreground focus-visible:ring-2 active:bg-sidebar-accent active:text-sidebar-accent-foreground disabled:pointer-events-none disabled:opacity-50 aria-disabled:pointer-events-none aria-disabled:opacity-50 peer-data-[size=sm]/menu-button:text-xs [&>span:last-child]:truncate [&>svg]:size-4 [&>svg]:shrink-0 [&>svg]:text-sidebar-foreground/50",
          "data-[active=true]:bg-sidebar-accent data-[active=true]:text-sidebar-accent-foreground",
          "group-data-[collapsible=icon]:hidden",
          className
        )}
        {...props}
      />
    )
  }
)
SidebarMenuSubButton.displayName = "SidebarMenuSubButton"

const SidebarMenuSubItemButton = React.forwardRef(
  (
    {
      asChild = false,
      size = "sm",
      isActive = false,
      className,
      ...props
    },
    ref
  ) => {
    return (
      <SidebarMenuSubItem>
        <SidebarMenuSubButton
          ref={ref}
          asChild={asChild}
          size={size}
          isActive={isActive}
          className={className}
          {...props}
        />
      </SidebarMenuSubItem>
    )
  }
)
SidebarMenuSubItemButton.displayName = "SidebarMenuSubItemButton"

const SidebarTrigger = React.forwardRef(
  ({ className, onClick, ...props }, ref) => {
    const { toggleSidebar } = useSidebar()

    return (
      <Button
        ref={ref}
        data-sidebar="trigger"
        variant="ghost"
        size="icon"
        className={cn("h-6 w-6", className)}
        onClick={(event) => {
          onClick?.(event)
          toggleSidebar()
        }}
        {...props}
      >
        <PanelLeft className="h-4 w-4" />
        <span className="sr-only">Toggle Sidebar</span>
      </Button>
    )
  }
)
SidebarTrigger.displayName = "SidebarTrigger"

const SidebarCollapsible = React.forwardRef(
  ({ defaultOpen, open: openProp, onOpenChange, className, ...props }, ref) => {
    return (
      <CollapsiblePrimitive.Root
        ref={ref}
        defaultOpen={defaultOpen}
        open={openProp}
        onOpenChange={onOpenChange}
        {...props}
        className={cn("group/collapsible", className)}
      />
    )
  }
)
SidebarCollapsible.displayName = "SidebarCollapsible"

const SidebarCollapsibleTrigger = React.forwardRef(
  ({ asChild = false, className, ...props }, ref) => {
    const Comp = asChild ? Slot : SidebarMenuButton

    return (
      <CollapsiblePrimitive.Trigger
        ref={ref}
        asChild
        {...props}
        className={cn("group/link", className)}
      >
        <Comp data-sidebar="collapsible-trigger" />
      </CollapsiblePrimitive.Trigger>
    )
  }
)
SidebarCollapsibleTrigger.displayName = "SidebarCollapsibleTrigger"

const SidebarCollapsibleContent = React.forwardRef(
  ({ className, ...props }, ref) => {
    return (
      <CollapsiblePrimitive.Content
        ref={ref}
        {...props}
        className={cn(
          "data-[state=closed]:animate-collapsible-up data-[state=open]:animate-collapsible-down",
          "group-data-[collapsible=icon]:!hidden",
          className
        )}
      />
    )
  }
)
SidebarCollapsibleContent.displayName = "SidebarCollapsibleContent"

export {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarGroupAction,
  SidebarGroupContent,
  SidebarGroupLabel,
  SidebarHeader,
  SidebarInput,
  SidebarInset,
  SidebarMenu,
  SidebarMenuAction,
  SidebarMenuBadge,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarMenuSkeleton,
  SidebarMenuSub,
  SidebarMenuSubButton,
  SidebarMenuSubItem,
  SidebarMenuSubItemButton,
  SidebarProvider,
  SidebarRail,
  SidebarCollapsible,
  SidebarCollapsibleContent,
  SidebarCollapsibleTrigger,
  SidebarSeparator,
  SidebarTrigger,
  useSidebar,
}

