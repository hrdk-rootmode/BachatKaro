const toNumber = (value, fallback = 0) => {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
};

const parseDateTime = (value) => {
  if (!value) return null;
  const raw = String(value).trim();
  if (!raw) return null;

  const hasTimezone = /[zZ]$|[+-]\d{2}:?\d{2}$/.test(raw);
  const normalized = hasTimezone ? raw : `${raw}Z`;
  const dt = new Date(normalized);
  return Number.isNaN(dt.getTime()) ? null : dt;
};

export const getSearchQuotaSnapshot = ({ user, userStats, planInfo, fallbackLimit = 10 } = {}) => {
  const usage = user?.usage_stats || {};
  const stats = userStats || {};

  const searchesToday = toNumber(
    stats.searches_today ??
    user?.searches_today ??
    usage.searches_today ??
    usage.daily_searches,
    0
  );

  const totalSearches = toNumber(
    stats.total_searches ??
    user?.total_searches ??
    usage.total_searches,
    0
  );

  const bonusSearches = Math.max(
    toNumber(stats.bonus_searches, 0),
    toNumber(usage.bonus_searches, 0),
    toNumber(usage.daily_search_bonus, 0)
  );

  const rawPlanLimit = stats.searches_remaining === -1
    ? -1
    : toNumber(
        planInfo?.searches_per_day ??
        user?.daily_limit ??
        usage.daily_limit ??
        fallbackLimit,
        fallbackLimit
      );

  const unlimitedUntil = parseDateTime(usage.unlimited_search_until);
  const hasActiveUnlimitedWindow = unlimitedUntil ? unlimitedUntil.getTime() > Date.now() : false;

  const isUnlimited = rawPlanLimit === -1 || stats.searches_remaining === -1 || hasActiveUnlimitedWindow;
  const baseDailyLimit = isUnlimited ? -1 : rawPlanLimit;
  const effectiveDailyLimit = isUnlimited ? -1 : Math.max(0, baseDailyLimit + bonusSearches);
  const remainingSearches = isUnlimited ? -1 : Math.max(0, effectiveDailyLimit - searchesToday);
  const searchUsagePct = isUnlimited || effectiveDailyLimit <= 0
    ? 0
    : Math.min(100, Math.round((searchesToday / effectiveDailyLimit) * 100));

  return {
    searchesToday,
    totalSearches,
    bonusSearches,
    baseDailyLimit,
    effectiveDailyLimit,
    remainingSearches,
    searchUsagePct,
    isUnlimited,
  };
};