'use client'

import { Menu, PanelRightClose, PanelRightOpen } from 'lucide-react'
import { useUIStore } from '@/stores/ui-store'

export function Header() {
  const {
    sidebarOpen,
    toggleSidebar,
    artifactPanelOpen,
    toggleArtifactPanel,
    currentArtifact,
  } = useUIStore()

  return (
    <header className="flex items-center justify-between px-4 py-3 bg-bg-primary border-b border-white/10">
      <div className="flex items-center gap-3">
        <button
          onClick={toggleSidebar}
          className="p-2 hover:bg-bg-secondary rounded-lg transition-colors lg:hidden"
          aria-label="Toggle sidebar"
        >
          <Menu className="w-5 h-5 text-f1-gray" />
        </button>

        <div className="flex items-center gap-2">
          <div className="w-1 h-6 bg-f1-red rounded-full" />
          <h1 className="text-lg font-bold text-white">
            F1 Race Intelligence
          </h1>
          <span className="hidden sm:inline-block px-2 py-0.5 text-xs bg-bg-secondary text-f1-gray rounded-full">
            Beta
          </span>
        </div>
      </div>

      <div className="flex items-center gap-2">
        {currentArtifact && (
          <button
            onClick={toggleArtifactPanel}
            className="p-2 hover:bg-bg-secondary rounded-lg transition-colors"
            aria-label={artifactPanelOpen ? 'Hide panel' : 'Show panel'}
          >
            {artifactPanelOpen ? (
              <PanelRightClose className="w-5 h-5 text-f1-gray" />
            ) : (
              <PanelRightOpen className="w-5 h-5 text-f1-gray" />
            )}
          </button>
        )}
      </div>
    </header>
  )
}
