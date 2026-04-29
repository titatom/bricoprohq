/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    './pages/**/*.{js,ts,jsx,tsx}',
    './components/**/*.{js,ts,jsx,tsx}',
  ],
  theme: {
    extend: {
      colors: {
        // Bricopro navy — primary brand color
        brand: {
          50:  '#eef2f9',
          100: '#d5dff0',
          200: '#aabfe1',
          300: '#7a9acf',
          400: '#4f78bc',
          500: '#2d5aa8',
          600: '#1B3A6B',   // core navy (logo fill)
          700: '#152e56',
          800: '#0f2240',
          900: '#0a162a',
        },
        // Bricopro orange — accent / highlight
        accent: {
          50:  '#fff8ed',
          100: '#ffeece',
          200: '#ffd999',
          300: '#ffc063',
          400: '#ffa832',
          500: '#F5A020',   // core orange (logo border)
          600: '#e08a0a',
          700: '#b86e07',
          800: '#8f5405',
          900: '#5c3503',
        },
      },
    },
  },
  plugins: [],
}
