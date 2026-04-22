import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./app/**/*.{ts,tsx}",
    "./components/**/*.{ts,tsx}",
    "./lib/**/*.{ts,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        ink: "#161b24",
        cloud: "#f5efe8",
        panel: "#fffaf4",
        ember: "#d97706",
        moss: "#2f6f57",
        ruby: "#a63d40",
        haze: "#7b8794",
      },
      fontFamily: {
        sans: ["IBM Plex Sans", "Avenir Next", "Segoe UI", "sans-serif"],
      },
      boxShadow: {
        panel: "0 20px 60px rgba(22, 27, 36, 0.12)",
      },
    },
  },
  plugins: [],
};

export default config;
