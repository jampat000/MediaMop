/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      fontFamily: {
        outfit: ['"Outfit"', "system-ui", "-apple-system", "sans-serif"],
      },
      colors: {
        mm: {
          bg: "var(--mm-bg)",
          "bg-main": "var(--mm-bg-main)",
          text: "var(--mm-text)",
          text2: "var(--mm-text2)",
          accent: "var(--mm-accent)",
          "accent-bright": "var(--mm-accent-bright)",
        },
      },
    },
  },
  plugins: [],
};
