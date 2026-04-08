import { createSlice } from '@reduxjs/toolkit';
import { COLORS } from '../utils/constants';

const themePalettes = {
  default: {
    id: 'default',
    name: 'Default',
    primary: COLORS.primary,
    background: COLORS.background,
    surface: COLORS.white,
    border: COLORS.gray200,
    text: COLORS.textPrimary,
    surfaceMuted: COLORS.infoLight,
    textSecondary: COLORS.textSecondary,
    tabActive: COLORS.primary,
    tabInactive: COLORS.gray500,
    accent: COLORS.secondary,
  },
  pro: {
    id: 'pro',
    name: 'Pro Luxe',
    primary: '#B7791F',
    background: '#FFF8EF',
    surface: '#FFFDF9',
    surfaceMuted: '#FFF4DA',
    border: '#E7C38B',
    text: '#3A2712',
    textSecondary: '#73552A',
    tabActive: '#B7791F',
    tabInactive: '#A1A1AA',
    accent: '#F59E0B',
    accentSoft: '#FCD9A5',
    glow: '#FFF1D6',
  },
  premium: {
    id: 'premium',
    name: 'Premium Luxe',
    primary: '#0B1220',
    background: '#F6F3EE',
    surface: '#FFFFFF',
    surfaceMuted: '#F1F5F9',
    border: '#D6C7B2',
    text: '#1A1A1A',
    textSecondary: '#5B5563',
    tabActive: '#0B1220',
    tabInactive: '#7C7C86',
    accent: '#C8A45D',
    accentSoft: '#F4E7C8',
    glow: '#FAF0DB',
  },
};

const resolveThemeId = (preferredMode, userPlan) => {
  const plan = String(userPlan || 'free').toLowerCase();

  if (preferredMode === 'default') {
    return 'default';
  }

  if (plan === 'premium') {
    return 'premium';
  }

  if (plan === 'pro') {
    return 'pro';
  }

  return 'default';
};

const initialState = {
  preferredMode: 'default', // default | subscription
  activeThemeId: 'default',
  lastPlan: 'free',
};

const themeSlice = createSlice({
  name: 'theme',
  initialState,
  reducers: {
    setPreferredThemeMode: (state, action) => {
      const mode = action.payload;
      if (mode !== 'default' && mode !== 'subscription') {
        return;
      }
      state.preferredMode = mode;
      state.activeThemeId = resolveThemeId(mode, state.lastPlan);
    },

    syncThemeWithPlan: (state, action) => {
      const plan = String(action.payload?.plan || 'free').toLowerCase();
      state.lastPlan = plan;
      state.activeThemeId = resolveThemeId(state.preferredMode, plan);
    },
  },
});

export const { setPreferredThemeMode, syncThemeWithPlan } = themeSlice.actions;

export const selectThemeState = (state) => state.theme;
export const selectPreferredThemeMode = (state) => state.theme.preferredMode;
export const selectActiveThemeId = (state) => state.theme.activeThemeId;
export const selectThemePalette = (state) => {
  const activeThemeId = state.theme.activeThemeId || 'default';
  return themePalettes[activeThemeId] || themePalettes.default;
};
export const selectAvailableThemeOptions = () => [
  { id: 'default', label: 'Default Theme' },
  { id: 'subscription', label: 'Subscription Theme' },
];

export default themeSlice.reducer;
