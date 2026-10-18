/** @type {import('tailwindcss').Config} */
// Editorial theme with a runtime dark mode. Every color is emitted as an
// `rgb(var(--x) / <alpha-value>)` channel triple: the LIGHT values (the
// current ink-on-paper editorial palette) live on `:root`, the DARK values
// are redefined on `html.dark` in src/index.css. Utility class names never
// change — toggling the `dark` class repaints the whole app, opacity
// modifiers included.
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  darkMode: "class",
  theme: {
    fontFamily: {
      sans: ['"Helvetica Neue"', "Helvetica", "Inter", "Arial", "system-ui", "sans-serif"],
      disp: ['"Helvetica Neue"', "Helvetica", "Inter", "Arial", "system-ui", "sans-serif"],
      mono: ['"SF Mono"', "ui-monospace", "Cascadia Code", "Consolas", "monospace"],
    },
    extend: {
      colors: {
        slate: {
          50: "rgb(var(--sl-50) / <alpha-value>)",
          100: "rgb(var(--sl-100) / <alpha-value>)",
          200: "rgb(var(--sl-200) / <alpha-value>)",
          300: "rgb(var(--sl-300) / <alpha-value>)",
          400: "rgb(var(--sl-400) / <alpha-value>)",
          500: "rgb(var(--sl-500) / <alpha-value>)",
          600: "rgb(var(--sl-600) / <alpha-value>)",
          700: "rgb(var(--sl-700) / <alpha-value>)",
          800: "rgb(var(--sl-800) / <alpha-value>)",
          900: "rgb(var(--sl-900) / <alpha-value>)",
          950: "rgb(var(--sl-950) / <alpha-value>)",
        },
        cyan: {
          200: "rgb(var(--cy-200) / <alpha-value>)",
          300: "rgb(var(--cy-300) / <alpha-value>)",
          400: "rgb(var(--cy-400) / <alpha-value>)",
          500: "rgb(var(--cy-500) / <alpha-value>)",
          600: "rgb(var(--cy-600) / <alpha-value>)",
          700: "rgb(var(--cy-700) / <alpha-value>)",
          800: "rgb(var(--cy-800) / <alpha-value>)",
        },
        emerald: {
          300: "rgb(var(--em-300) / <alpha-value>)",
          500: "rgb(var(--em-500) / <alpha-value>)",
        },
        amber: {
          200: "rgb(var(--am-200) / <alpha-value>)",
          300: "rgb(var(--am-300) / <alpha-value>)",
          400: "rgb(var(--am-400) / <alpha-value>)",
          500: "rgb(var(--am-500) / <alpha-value>)",
          700: "rgb(var(--am-700) / <alpha-value>)",
        },
        rose: {
          300: "rgb(var(--ro-300) / <alpha-value>)",
          400: "rgb(var(--ro-400) / <alpha-value>)",
          500: "rgb(var(--ro-500) / <alpha-value>)",
        },
        violet: {
          300: "rgb(var(--vi-300) / <alpha-value>)",
          500: "rgb(var(--vi-500) / <alpha-value>)",
        },
        orange: {
          300: "rgb(var(--or-300) / <alpha-value>)",
        },
        cosmos: {
          900: "rgb(var(--co-900) / <alpha-value>)",
          800: "rgb(var(--co-800) / <alpha-value>)",
          700: "rgb(var(--co-700) / <alpha-value>)",
          accent: "rgb(var(--co-accent) / <alpha-value>)",
          warm: "rgb(var(--co-warm) / <alpha-value>)",
        },
      },
    },
  },
  plugins: [],
};
