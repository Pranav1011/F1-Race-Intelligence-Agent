import { create } from 'zustand'
import { Visualization } from '@/types'

interface UIStore {
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

export const useUIStore = create<UIStore>((set) => ({
  sidebarOpen: true,
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
    set({
      currentArtifact: viz,
      artifactPanelOpen: viz !== null,
    })
  },

  clearArtifact: () => {
    set({
      currentArtifact: null,
      artifactPanelOpen: false,
    })
  },
}))
