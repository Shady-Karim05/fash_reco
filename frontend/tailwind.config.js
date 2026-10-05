/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        brand: {
          50: '#fdf8f6',
          100: '#f2e8e5',
          200: '#eaddd7',
          300: '#e0cec7',
          400: '#d2bab0',
          500: '#bfa094',
          600: '#a18072',
          700: '#846356',
          800: '#63473c',
          900: '#432e26',
          950: '#261914',
        },
        sand: {
          50: '#faf8f5',
          100: '#f5f0e8',
          200: '#eae2d5',
          300: '#ddd2c0',
          400: '#c5b59e',
          500: '#a8947b',
          600: '#8c775f',
          700: '#705c48',
          800: '#584839',
          900: '#2b231c',
        },
        accent: {
          50: '#fdf8f3',
          100: '#faeee2',
          200: '#f4dcbf',
          300: '#ecc496',
          400: '#e2a669',
          500: '#d98b44',
          600: '#cb7132',
          700: '#a85529',
          800: '#864426',
          900: '#6d3922',
        },
        fashion: {
          dark: '#121214',
          surface: '#18181b',
          muted: '#71717a',
          accent: '#e2b170',
          gold: '#d4af37',
        }
      },
      fontFamily: {
        sans: ['Plus Jakarta Sans', 'Inter', 'sans-serif'],
        serif: ['Playfair Display', 'serif'],
      },
      boxShadow: {
        'subtle': '0 4px 20px -2px rgba(0, 0, 0, 0.05)',
        'premium': '0 10px 30px -4px rgba(0, 0, 0, 0.08), 0 4px 6px -2px rgba(0, 0, 0, 0.04)',
        'glow': '0 0 25px rgba(226, 177, 112, 0.25)',
      }
    },
  },
  plugins: [],
}
