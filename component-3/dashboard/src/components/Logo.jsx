// The InteliSE mark: a requirement-to-test-hook trace (four linked nodes, the last one green = verified).
export function LogoMark({ size = 40 }) {
  return (
    <svg className="logo-mark" viewBox="0 0 64 64" width={size} height={size} role="img" aria-label="InteliSE">
      <defs>
        <linearGradient id="inteliseMarkBg" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#4c7dff" />
          <stop offset="1" stopColor="#2f46d1" />
        </linearGradient>
      </defs>
      <rect width="64" height="64" rx="16" fill="url(#inteliseMarkBg)" />
      <path d="M15 46 L27 25 L39 39 L50 18" fill="none" stroke="#ffffff" strokeOpacity="0.9" strokeWidth="4" strokeLinecap="round" strokeLinejoin="round" />
      <circle cx="15" cy="46" r="5.5" fill="#ffffff" />
      <circle cx="27" cy="25" r="5.5" fill="#ffffff" />
      <circle cx="39" cy="39" r="5.5" fill="#ffffff" />
      <circle cx="50" cy="18" r="6.5" fill="#22c55e" stroke="#ffffff" strokeWidth="3" />
    </svg>
  );
}
