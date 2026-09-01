# Web Fetch Activity Compact Design

Web fetch activity will present one compact timeline row: a read count, inline
page-title links, and the existing chevron. URL-shaped `Title:` values are
discarded in favor of a fetched heading or hostname. Each link label is safely
truncated to 20 characters, while the full title remains available as the link
tooltip. The existing drawer still exposes all fetched pages.
