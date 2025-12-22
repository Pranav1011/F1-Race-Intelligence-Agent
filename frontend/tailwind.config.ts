import type { Config } from "tailwindcss";

const config: Config = {
  darkMode: "class",
  content: [
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        // Core palette - Modern dark theme with better contrast
        background: {
          primary: "#0A0A0F",      // Deep navy-black
          secondary: "#12121A",    // Slightly lighter
          tertiary: "#1A1A24",     // Card backgrounds
          elevated: "#22222E",     // Elevated surfaces
        },

        // Surface colors for cards and panels
        surface: {
          DEFAULT: "#16161E",
          hover: "#1E1E28",
          active: "#262630",
          border: "rgba(255, 255, 255, 0.08)",
        },

        // F1 accent colors - Vibrant but refined
        f1: {
          red: "#E31937",          // Slightly warmer red
          redLight: "#FF2D4D",     // Brighter variant
          redDark: "#B81530",      // Darker variant
          white: "#FFFFFF",
          gray: "#8B8B97",
          grayLight: "#A8A8B3",
        },

        // Modern accent colors
        accent: {
          blue: "#3B82F6",
          purple: "#8B5CF6",
          cyan: "#06B6D4",
          orange: "#F97316",
          emerald: "#10B981",
        },

        // Team colors
        teams: {
          redbull: "#3671C6",
          ferrari: "#F91536",
          mercedes: "#6CD3BF",
          mclaren: "#F58020",
          astonmartin: "#229971",
          alpine: "#0093CC",
          williams: "#64C4FF",
          rb: "#6692FF",
          kick: "#52E252",
          haas: "#B6BABD",
        },

        // Data visualization - More refined colors
        data: {
          positive: "#22C55E",     // Green success
          negative: "#EF4444",     // Red error
          neutral: "#71717A",      // Neutral gray
          warning: "#FBBF24",      // Warning yellow
          info: "#3B82F6",         // Info blue
        },

        // Text colors
        text: {
          primary: "#F9FAFB",
          secondary: "#A1A1AA",
          muted: "#71717A",
          accent: "#E31937",
        },

        // Tire compounds
        tires: {
          soft: "#FF3333",
          medium: "#FFD700",
          hard: "#EEEEEE",
          intermediate: "#43B02A",
          wet: "#0067AD",
        },
      },

      fontFamily: {
        sans: ["var(--font-inter)", "system-ui", "sans-serif"],
        mono: ["var(--font-mono)", "Consolas", "monospace"],
      },

      animation: {
        "fade-in": "fadeIn 0.3s ease-in-out",
        "slide-in": "slideIn 0.4s ease-out",
        "pulse-subtle": "pulseSubtle 2s infinite",
      },

      keyframes: {
        fadeIn: {
          "0%": { opacity: "0" },
          "100%": { opacity: "1" },
        },
        slideIn: {
          "0%": { transform: "translateX(20px)", opacity: "0" },
          "100%": { transform: "translateX(0)", opacity: "1" },
        },
        pulseSubtle: {
          "0%, 100%": { opacity: "1" },
          "50%": { opacity: "0.7" },
        },
      },
    },
  },
  plugins: [],
};

export default config;
