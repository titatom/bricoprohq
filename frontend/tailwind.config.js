/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    './pages/**/*.{js,ts,jsx,tsx}',
    './components/**/*.{js,ts,jsx,tsx}',
  ],
  theme: {
    extend: {
      colors: {
        // Bricopro blue — primary brand color
        brand: {
          50:  '#eef6fb',
          100: '#d6e8f4',
          200: '#adcfe4',
          300: '#7eafd1',
          400: '#4f8bb8',
          500: '#2d6998',
          600: '#18486f',   // core blue
          700: '#133a59',
          800: '#0e2b43',
          900: '#091d2d',
        },
        // Bricopro orange — accent / highlight
        accent: {
          50:  '#fff8ed',
          100: '#ffeece',
          200: '#ffd999',
          300: '#ffc063',
          400: '#f9a13a',
          500: '#f7931e',   // core orange
          600: '#d97808',
          700: '#b86e07',
          800: '#8f5405',
          900: '#5c3503',
        },
      },
    },
  },
  plugins: [],
}
