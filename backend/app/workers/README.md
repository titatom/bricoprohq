# Workers

This folder hosts the in-process background jobs used by Bricopro HQ.

The next scheduled job to land here (PR6) is an APScheduler-based dashboard
refresh loop that honors `CACHE_TTL_MINUTES` per integration. Future work
can extend it to handle:

- stale-cache sweeps (`DashboardCache.expires_at < now`)
- asynchronous AI content generation
- automatic post publishing (Meta / GBP) once the publishing service lands
- KPI ingestion from upstream insights APIs

We deliberately stayed in-process rather than introducing Redis + RQ /
Celery: the typical Bricopro HQ install is a single container running on
Unraid, and an in-process scheduler keeps deployment to one moving part.
