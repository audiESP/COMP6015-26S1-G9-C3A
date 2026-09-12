/** Shared Tailwind tokens for the native and web Care Companion UI. */
module.exports = {
  content: ['./App.tsx', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        care: {
          canvas: '#F2F4F1', surface: '#FFFFFF', ink: '#203832', muted: '#697C75',
          line: '#E3EAE6', primary: '#176B58', deep: '#183F34', soft: '#E8F3ED',
          lime: '#E2EFD8', onhero: '#F4F8EF', subtle: '#C3D8CA',
          warning: '#FFF3DC', amber: '#80551C', danger: '#A34539', blush: '#FFF0EB',
        },
      },
      borderRadius: { card: '22px', hero: '26px', control: '16px' },
    },
  },
};
