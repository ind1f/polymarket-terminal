export function GiftIcon({ title }: { title: string }) {
  return (
    <svg
      className="gift"
      width="12"
      height="12"
      viewBox="0 0 16 16"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.4"
      strokeLinecap="round"
      strokeLinejoin="round"
      role="img"
      aria-label={title}
    >
      <title>{title}</title>
      <rect x="2" y="6" width="12" height="3" rx="0.5" />
      <path d="M3 9v5h10V9M8 6v8M8 6C7 3.5 4.5 3 4.5 4.6 4.5 6 8 6 8 6zM8 6c1-2.5 3.5-3 3.5-1.4C11.5 6 8 6 8 6z" />
    </svg>
  );
}
