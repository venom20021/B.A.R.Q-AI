import type { Config } from 'tailwindcss'

export default {
  content: ['./src/renderer/src/**/*.{js,jsx,ts,tsx}', './src/renderer/index.html'],
  theme: {
    extend: {
      colors: {
        // BARQ design system palette
        cyan: {
          950: '#001a1a',
          900: '#003333',
          800: '#004d4d',
          700: '#006666',
          600: '#008080',
          500: '#00b3b3',
          400: '#00e6e6',
          300: '#00f0ff',
          200: '#33f5ff',
          100: '#80faff',
          50: '#ccfdff',
        },
        void: {
          DEFAULT: '#0A0A0F',
          900: '#0A0A0F',
          800: '#0E0E15',
          700: '#12121A',
          600: '#1A1A2E',
          500: '#222240',
        },
        holographic: {
          DEFAULT: '#A855F7',
          400: '#A855F7',
          500: '#9333EA',
          600: '#7C3AED',
        },
        plasma: {
          DEFAULT: '#FF6B35',
          400: '#FF6B35',
          500: '#FF5722',
        },
        neural: {
          DEFAULT: '#00FF88',
          400: '#00FF88',
          500: '#00CC6A',
        },
        ghost: {
          DEFAULT: '#E8E8F0',
          400: '#C8C8D0',
          500: '#A8A8B5',
        },
        dim: {
          DEFAULT: '#5A5A7A',
          400: '#4A4A6A',
          500: '#3A3A5A',
        },
      },
      fontFamily: {
        orbitron: ['Orbitron', 'sans-serif'],
        rajdhani: ['Rajdhani', 'sans-serif'],
        exo: ['Exo 2', 'sans-serif'],
        'share-tech': ['Share Tech Mono', 'monospace'],
        'jetbrains': ['JetBrains Mono', 'monospace'],
      },
      fontSize: {
        'hud': ['10px', '14px'],
        'hud-lg': ['12px', '16px'],
      },
      boxShadow: {
        'glow-cyan': '0 0 20px rgba(0, 240, 255, 0.3)',
        'glow-cyan-sm': '0 0 10px rgba(0, 240, 255, 0.2)',
        'glow-purple': '0 0 20px rgba(168, 85, 247, 0.3)',
        'glow-green': '0 0 20px rgba(0, 255, 136, 0.3)',
        'glow-plasma': '0 0 20px rgba(255, 107, 53, 0.3)',
        'glass': '0 8px 32px rgba(0, 0, 0, 0.3)',
      },
      animation: {
        'glitch': 'glitch 0.3s ease-in-out',
        'glitch-2': 'glitch2 0.4s ease-in-out',
        'pulse-cyan': 'pulseCyan 2s ease-in-out infinite',
        'scanline': 'scanline 8s linear infinite',
        'shimmer': 'shimmer 2s linear infinite',
        'float': 'float 6s ease-in-out infinite',
        'holographic': 'holographic 4s linear infinite',
        'typewriter': 'typewriter 0.05s steps(1) forwards',
        'slide-up': 'slideUp 0.3s ease-out forwards',
        'slide-right': 'slideRight 0.2s ease-out',
        'fade-in': 'fadeIn 0.3s ease-out forwards',
        'pulse-ring': 'pulseRing 1.5s cubic-bezier(0.215, 0.61, 0.355, 1) infinite',
        'waveform': 'waveform 0.5s ease-in-out infinite alternate',
        'glow-pulse': 'glowPulse 2s ease-in-out infinite',
        'boot-pulse': 'bootPulse 1s ease-in-out infinite',
      },
      keyframes: {
        glitch: {
          '0%, 100%': { transform: 'translate(0)' },
          '20%': { transform: 'translate(-2px, 2px)' },
          '40%': { transform: 'translate(2px, -2px)' },
          '60%': { transform: 'translate(-1px, -1px)' },
          '80%': { transform: 'translate(1px, 1px)' },
        },
        glitch2: {
          '0%, 100%': { transform: 'translate(0) skew(0deg)', opacity: '1' },
          '10%': { transform: 'translate(-3px, 0) skew(2deg)', opacity: '0.8' },
          '20%': { transform: 'translate(3px, 0) skew(-2deg)', opacity: '0.6' },
          '30%': { transform: 'translate(-1px, 0) skew(1deg)', opacity: '0.9' },
          '40%': { transform: 'translate(1px, 0) skew(-1deg)', opacity: '1' },
        },
        pulseCyan: {
          '0%, 100%': { boxShadow: '0 0 10px rgba(0, 240, 255, 0.2)' },
          '50%': { boxShadow: '0 0 25px rgba(0, 240, 255, 0.5)' },
        },
        scanline: {
          '0%': { transform: 'translateY(-100%)' },
          '100%': { transform: 'translateY(100vh)' },
        },
        shimmer: {
          '0%': { backgroundPosition: '-200% 0' },
          '100%': { backgroundPosition: '200% 0' },
        },
        float: {
          '0%, 100%': { transform: 'translateY(0)' },
          '50%': { transform: 'translateY(-10px)' },
        },
        holographic: {
          '0%': { backgroundPosition: '0% 50%' },
          '50%': { backgroundPosition: '100% 50%' },
          '100%': { backgroundPosition: '0% 50%' },
        },
        slideUp: {
          '0%': { transform: 'translateY(20px)', opacity: '0' },
          '100%': { transform: 'translateY(0)', opacity: '1' },
        },
        slideRight: {
          '0%': { transform: 'translateX(-20px)', opacity: '0' },
          '100%': { transform: 'translateX(0)', opacity: '1' },
        },
        fadeIn: {
          '0%': { opacity: '0' },
          '100%': { opacity: '1' },
        },
        pulseRing: {
          '0%': { transform: 'scale(0.95)', opacity: '0.7' },
          '50%': { transform: 'scale(1.1)', opacity: '0.3' },
          '100%': { transform: 'scale(0.95)', opacity: '0.7' },
        },
        waveform: {
          '0%': { height: '20%' },
          '100%': { height: '100%' },
        },
        glowPulse: {
          '0%, 100%': { opacity: '0.6' },
          '50%': { opacity: '1' },
        },
        bootPulse: {
          '0%, 100%': { opacity: '0.5' },
          '50%': { opacity: '1' },
        },
      },
    }
  },
  plugins: []
} satisfies Config
