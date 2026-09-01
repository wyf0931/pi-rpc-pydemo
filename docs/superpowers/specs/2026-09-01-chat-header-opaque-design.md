# Chat Header Opaque Background Design

The fixed Chat detail title bar will use the page content background token
(`var(--bg)`) instead of transparency. Its existing fixed positioning and
`z-index` remain unchanged, so message content is covered while scrolling and
the light/dark theme tokens continue to resolve consistently.
