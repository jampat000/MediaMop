/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      fontFamily: {
        outfit: ['"Outfit"', "system-ui", "-apple-system", "sans-serif"],
      },
      colors: {
        mb: {
          bg: "var(--mb-bg)",
          "bg-main": "var(--mb-bg-main)",
          text: "var(--mb-text)",
          text2: "var(--mb-text2)",
          accent: "var(--mb-accent)",
          "accent-bright": "var(--mb-accent-bright)",
        },
      },
    },
  },
  plugins: [],
};
