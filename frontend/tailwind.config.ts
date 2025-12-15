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
        // Core palette
        background: {
          primary: "#0F0F0F",
          secondary: "#1A1A1A",
          tertiary: "#252525",
        },

        // F1 accent colors
        f1: {
          red: "#E10600",
          white: "#FFFFFF",
          gray: "#949498",
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

        // Data visualization
        data: {
          positive: "#00FF87",
          negative: "#FF4444",
          neutral: "#888888",
          warning: "#FFB800",
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
