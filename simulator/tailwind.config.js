/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        chapter: "#0f172a",
        correct: "#16a34a",
        incorrect: "#dc2626",
        partial: "#d97706",
      },
    },
  },
  plugins: [],
};
