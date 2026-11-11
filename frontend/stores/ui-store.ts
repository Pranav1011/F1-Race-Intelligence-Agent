import { create } from 'zustand'
import { Visualization } from '@/types'

interface UIStore {
  // Only drives the mobile drawer; at lg and up the sidebar is always shown
  sidebarOpen: boolean
  artifactPanelOpen: boolean
  currentArtifact: Visualization | null

  toggleSidebar: () => void
  setSidebarOpen: (open: boolean) => void
  toggleArtifactPanel: () => void
  setArtifactPanelOpen: (open: boolean) => void
  setArtifact: (viz: Visualization | null) => void
  clearArtifact: () => void
}

/** True when a visualization has rows to plot; empty ones never open the panel. */
export function hasChartData(viz: Visualization | null | undefined): viz is Visualization {
  return Boolean(viz && Array.isArray(viz.data) && viz.data.length > 0)
}

export const useUIStore = create<UIStore>((set) => ({
  sidebarOpen: false,
  artifactPanelOpen: false,
  currentArtifact: null,

  toggleSidebar: () => {
    set((state) => ({ sidebarOpen: !state.sidebarOpen }))
  },

  setSidebarOpen: (open: boolean) => {
    set({ sidebarOpen: open })
  },

  toggleArtifactPanel: () => {
    set((state) => ({ artifactPanelOpen: !state.artifactPanelOpen }))
  },

  setArtifactPanelOpen: (open: boolean) => {
    set({ artifactPanelOpen: open })
  },

  setArtifact: (viz: Visualization | null) => {
    if (viz === null) {
      set({ currentArtifact: null, artifactPanelOpen: false })
    } else if (hasChartData(viz)) {
      set({ currentArtifact: viz, artifactPanelOpen: true })
    }
  },

  clearArtifact: () => {
    set({
      currentArtifact: null,
      artifactPanelOpen: false,
    })
  },
}))
