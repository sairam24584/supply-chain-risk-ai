/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,jsx}"],
  theme: {
    extend: {
      fontFamily: {
        sans: ["Inter", "ui-sans-serif", "system-ui", "sans-serif"],
        mono: ["JetBrains Mono", "ui-monospace", "Menlo", "monospace"],
      },
      colors: {
        brand: {
          50:  "#eef4ff",
          100: "#dbe7ff",
          200: "#bdd0ff",
          300: "#90b1ff",
          400: "#5a86ff",
          500: "#3563ff",
          600: "#1d44f0",
          700: "#1733c9",
          800: "#172e9d",
          900: "#172a7a",
          950: "#0f1b4d",
        },
        ink: {
          50:  "#f7f8fb",
          100: "#eef0f6",
          200: "#dde1ec",
          300: "#bcc3d4",
          400: "#8b94ab",
          500: "#5e6781",
          600: "#454d64",
          700: "#36394d",
          800: "#212436",
          900: "#13152a",
          950: "#0a0c1d",
        },
        severity: {
          high: "#dc2626",
          medium: "#f59e0b",
          low: "#16a34a",
        },
      },
      boxShadow: {
        card: "0 1px 3px rgba(15, 23, 42, 0.04), 0 1px 2px rgba(15, 23, 42, 0.03)",
        soft: "0 8px 24px -8px rgba(13, 27, 77, 0.15), 0 2px 6px -2px rgba(13, 27, 77, 0.08)",
        glow: "0 0 0 1px rgba(53, 99, 255, 0.12), 0 8px 24px -8px rgba(53, 99, 255, 0.25)",
      },
      backgroundImage: {
        "sidebar-gradient":
          "linear-gradient(180deg, #0a0c1d 0%, #13152a 60%, #172a7a 130%)",
        "hero-gradient":
          "linear-gradient(135deg, rgba(53,99,255,0.10) 0%, rgba(53,99,255,0.02) 60%)",
        "danger-gradient":
          "linear-gradient(135deg, rgba(220,38,38,0.10) 0%, rgba(220,38,38,0.02) 60%)",
      },
      keyframes: {
        "fade-in": {
          "0%": { opacity: 0, transform: "translateY(4px)" },
          "100%": { opacity: 1, transform: "translateY(0)" },
        },
        shimmer: {
          "0%": { backgroundPosition: "-200% 0" },
          "100%": { backgroundPosition: "200% 0" },
        },
      },
      animation: {
        "fade-in": "fade-in 0.25s ease-out",
        shimmer: "shimmer 1.8s linear infinite",
      },
    },
  },
  plugins: [],
};
