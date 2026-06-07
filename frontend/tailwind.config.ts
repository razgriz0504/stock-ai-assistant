import type { Config } from 'tailwindcss'

const config: Config = {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        // 主色板
        cream: {
          50: '#fdfcfa',
          100: '#faf9f5',
          200: '#f5f3ef',
          300: '#e8e4de',
          400: '#d4cfc7',
          500: '#a8a29e',
        },
        copper: {
          DEFAULT: '#c9774a',
          light: '#d4956e',
          dark: '#b5683e',
        },
        sidebar: {
          DEFAULT: '#1e2530',
          light: '#2a3340',
          lighter: '#354050',
        },
        success: '#2d6a4f',
        danger: '#b91c1c',
        warning: '#b45309',
      },
      fontFamily: {
        sans: ['DM Sans', '-apple-system', 'BlinkMacSystemFont', 'sans-serif'],
        heading: ['Space Grotesk', 'sans-serif'],
        mono: ['JetBrains Mono', 'monospace'],
      },
      fontSize: {
        'xs': ['11px', { lineHeight: '16px' }],
        'sm': ['13px', { lineHeight: '20px' }],
        'base': ['14px', { lineHeight: '22px' }],
        'lg': ['16px', { lineHeight: '24px' }],
        'xl': ['18px', { lineHeight: '28px' }],
        '2xl': ['24px', { lineHeight: '32px' }],
        '3xl': ['32px', { lineHeight: '40px' }],
      },
      borderRadius: {
        DEFAULT: '8px',
        'lg': '10px',
        'xl': '12px',
      },
      boxShadow: {
        'card': '0 1px 3px rgba(0,0,0,0.04), 0 1px 2px rgba(0,0,0,0.02)',
        'card-hover': '0 4px 12px rgba(0,0,0,0.06), 0 2px 4px rgba(0,0,0,0.03)',
      },
    },
  },
  plugins: [],
}

export default config
