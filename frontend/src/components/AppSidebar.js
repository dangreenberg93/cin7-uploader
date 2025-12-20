import React, { useState, useEffect } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { LogOut, ChevronsUpDown, Shield, FileText, Cog, ShoppingCart } from 'lucide-react';
import { useClient } from '../contexts/ClientContext';
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarGroupContent,
  SidebarGroupLabel,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
} from './ui/sidebar';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from './ui/dropdown-menu';

export function AppSidebar({ user, onLogout }) {
  const navigate = useNavigate();
  const location = useLocation();
  const [avatarError, setAvatarError] = useState(false);
  const { selectedClient, selectedClientId, setSelectedClientId, clients } = useClient();

  // Reset avatar error state when user changes
  useEffect(() => {
    setAvatarError(false);
  }, [user?.avatar_url]);
  
  // Try to preload avatar image
  useEffect(() => {
    if (user?.avatar_url && !avatarError) {
      const img = new Image();
      img.onerror = () => {
        console.warn('[AppSidebar] Avatar preload failed:', user.avatar_url);
        setAvatarError(true);
      };
      img.src = user.avatar_url;
    }
  }, [user?.avatar_url, avatarError]);

  return (
    <Sidebar>
      <SidebarHeader className="flex flex-col gap-3 py-3 pl-6 pr-2">
        {/* Logo */}
        <div className="flex items-center justify-center">
          <div className="flex-shrink-0" style={{ width: '225px', minWidth: '225px' }}>
            <img 
              src="/logo.png" 
              alt="Logo" 
              className="h-auto w-auto"
              style={{ objectFit: 'contain', maxHeight: '26px', width: 'auto' }}
              onError={(e) => {
                e.target.style.display = 'none';
              }}
            />
          </div>
        </div>
        {/* Client/Profile Selector */}
        <SidebarMenu>
          <SidebarMenuItem>
            {clients.length === 1 ? (
              // Single client: show simple button without dropdown, chevron, or hover
              <SidebarMenuButton
                className="pointer-events-none cursor-default hover:bg-transparent hover:text-sidebar-foreground"
              >
                <span className="truncate font-semibold text-lg flex-1 text-left">
                  {selectedClient ? selectedClient.name : clients[0]?.name || 'Select client'}
                </span>
              </SidebarMenuButton>
            ) : (
              // Multiple clients: show dropdown with chevron
              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <SidebarMenuButton
                    className="data-[state=open]:bg-sidebar-accent data-[state=open]:text-sidebar-accent-foreground"
                  >
                    <span className="truncate font-semibold text-lg flex-1 text-left">
                      {selectedClient ? selectedClient.name : 'Select client'}
                    </span>
                    <ChevronsUpDown className="ml-auto h-3.5 w-3.5" />
                  </SidebarMenuButton>
                </DropdownMenuTrigger>
                <DropdownMenuContent
                  className="min-w-56 rounded-lg p-1"
                  side="bottom"
                  align="start"
                  sideOffset={4}
                >
                  {clients.length === 0 ? (
                    <div className="px-2 py-1.5 text-xs text-muted-foreground">
                      No clients available
                    </div>
                  ) : (
                    clients.map((client) => (
                      <DropdownMenuItem
                        key={client.id}
                        onClick={() => setSelectedClientId(client.id)}
                        className={selectedClientId === client.id ? 'bg-accent' : ''}
                      >
                        <div className="flex items-center gap-2 w-full">
                          <div className="flex h-5 w-5 items-center justify-center rounded bg-muted text-muted-foreground text-xs font-medium flex-shrink-0">
                            {client.name.charAt(0).toUpperCase()}
                          </div>
                          <span className="flex-1 truncate text-sm">{client.name}</span>
                          {selectedClientId === client.id && (
                            <div className="h-1.5 w-1.5 rounded-full bg-primary" />
                          )}
                        </div>
                      </DropdownMenuItem>
                    ))
                  )}
                </DropdownMenuContent>
              </DropdownMenu>
            )}
          </SidebarMenuItem>
        </SidebarMenu>
      </SidebarHeader>
      <SidebarContent>
        <SidebarGroup className="pt-1">
          <SidebarGroupContent>
            <SidebarMenu>
              <SidebarMenuItem>
                <SidebarMenuButton asChild isActive={location.pathname === '/'}>
                  <a href="#" onClick={(e) => { e.preventDefault(); navigate('/'); }}>
                    <ShoppingCart />
                    <span>Sales Orders</span>
                  </a>
                </SidebarMenuButton>
              </SidebarMenuItem>
            </SidebarMenu>
          </SidebarGroupContent>
        </SidebarGroup>
        <SidebarGroup>
          <SidebarGroupLabel>Settings</SidebarGroupLabel>
          <SidebarGroupContent>
            <SidebarMenu>
              <SidebarMenuItem>
                <SidebarMenuButton asChild isActive={location.pathname === '/mappings'}>
                  <a href="#" onClick={(e) => { e.preventDefault(); navigate('/mappings'); }}>
                    <FileText />
                    <span>CSV Mappings</span>
                  </a>
                </SidebarMenuButton>
              </SidebarMenuItem>
              <SidebarMenuItem>
                <SidebarMenuButton asChild isActive={location.pathname === '/settings/cin7'}>
                  <a href="#" onClick={(e) => { e.preventDefault(); navigate('/settings/cin7'); }}>
                    <Cog />
                    <span>Cin7 Config</span>
                  </a>
                </SidebarMenuButton>
              </SidebarMenuItem>
            </SidebarMenu>
          </SidebarGroupContent>
        </SidebarGroup>
        {/* Only show Admin link to admins */}
        {(user?.role === 'admin' || user?.email === 'dan@paleblue.nyc') && (
          <SidebarGroup>
            <SidebarGroupContent>
              <SidebarMenu>
                <SidebarMenuItem>
                  <SidebarMenuButton asChild isActive={location.pathname === '/admin'}>
                    <a href="#" onClick={(e) => { e.preventDefault(); navigate('/admin'); }}>
                      <Shield />
                      <span>Admin</span>
                    </a>
                  </SidebarMenuButton>
                </SidebarMenuItem>
              </SidebarMenu>
            </SidebarGroupContent>
          </SidebarGroup>
        )}
      </SidebarContent>
      <SidebarFooter className="pb-8 pl-6 pr-2">
        {user && (
          <SidebarMenu>
            <SidebarMenuItem>
              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <SidebarMenuButton
                    className="data-[state=open]:bg-sidebar-accent data-[state=open]:text-sidebar-accent-foreground"
                  >
                    {user.avatar_url && !avatarError ? (
                      <img 
                        src={user.avatar_url} 
                        alt={user.name || user.email}
                        className="h-6 w-6 rounded-full object-cover flex-shrink-0"
                        style={{ 
                          width: '24px', 
                          height: '24px', 
                          minWidth: '24px',
                          minHeight: '24px',
                          borderRadius: '50%',
                          objectFit: 'cover',
                          display: 'block'
                        }}
                        referrerPolicy="no-referrer"
                        loading="lazy"
                        onError={(e) => {
                          console.warn('[AppSidebar] Avatar image failed to load, using fallback:', user.avatar_url);
                          setAvatarError(true);
                        }}
                      />
                    ) : (
                      <div className="flex h-6 w-6 items-center justify-center rounded-full bg-primary text-primary-foreground text-xs font-medium flex-shrink-0" style={{ minWidth: '24px', minHeight: '24px' }}>
                        {user.email ? user.email.charAt(0).toUpperCase() : 'U'}
                      </div>
                    )}
                    <span className="truncate font-semibold text-xs flex-1 text-left">
                      {user.name || user.email?.split('@')[0] || 'User'}
                    </span>
                    <ChevronsUpDown className="ml-auto h-3.5 w-3.5" />
                  </SidebarMenuButton>
                </DropdownMenuTrigger>
                <DropdownMenuContent
                  className="min-w-56 rounded-lg p-1"
                  side="bottom"
                  align="end"
                  sideOffset={4}
                >
                  <DropdownMenuLabel className="px-2 py-2 font-normal">
                    <div className="flex items-center gap-2 text-left text-sm">
                      {user.avatar_url && !avatarError ? (
                        <img 
                          src={user.avatar_url} 
                          alt={user.name || user.email}
                          className="h-8 w-8 rounded-full object-cover flex-shrink-0"
                          style={{ 
                            width: '32px', 
                            height: '32px',
                            minWidth: '32px',
                            minHeight: '32px',
                            borderRadius: '50%',
                            objectFit: 'cover',
                            display: 'block'
                          }}
                          referrerPolicy="no-referrer"
                          loading="lazy"
                          onError={(e) => {
                            console.warn('[AppSidebar] Avatar image failed to load in dropdown, using fallback:', user.avatar_url);
                            setAvatarError(true);
                          }}
                        />
                      ) : (
                        <div className="flex h-8 w-8 items-center justify-center rounded-full bg-primary text-primary-foreground text-xs font-medium flex-shrink-0" style={{ minWidth: '32px', minHeight: '32px' }}>
                          {user.email ? user.email.charAt(0).toUpperCase() : 'U'}
                        </div>
                      )}
                      <div className="grid flex-1 text-left text-sm leading-tight">
                        <span className="truncate font-semibold">
                          {user.name || user.email?.split('@')[0] || 'User'}
                        </span>
                        <span className="truncate text-xs text-muted-foreground">
                          {user.email}
                        </span>
                      </div>
                    </div>
                  </DropdownMenuLabel>
                  <DropdownMenuSeparator />
                  {onLogout && (
                    <DropdownMenuItem onClick={onLogout}>
                      <LogOut className="mr-2 h-4 w-4" />
                      <span>Log out</span>
                    </DropdownMenuItem>
                  )}
                </DropdownMenuContent>
              </DropdownMenu>
            </SidebarMenuItem>
          </SidebarMenu>
        )}
      </SidebarFooter>
    </Sidebar>
  );
}

