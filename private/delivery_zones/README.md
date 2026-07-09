# AMB urban delivery zones

Generated rows: 329
Rows that require price review: 309

Files:

- `amb_urban_delivery_zones.csv`: review sheet with source and pricing metadata.
- `amb_urban_delivery_zones.sql`: idempotent PostgreSQL import for `bot.delivery_zones`.

Scope:

- Includes urban neighborhoods/sectors for Bucaramanga, Floridablanca, Girón and Piedecuesta.
- Excludes veredas and corregimientos. If a customer writes one of those locations, leave it
  absent from `bot.delivery_zones`; the existing OpenRouteService fallback calculates the
  delivery price from distance using the `.env` km pricing settings.

Apply only after reviewing the CSV:

```bash
psql "$DATABASE_URL" -f bot/private/delivery_zones/amb_urban_delivery_zones.sql
```

Quick DB check:

```sql
SELECT count(*) FROM bot.delivery_zones;
SELECT neighborhood, delivery_price_cop
FROM bot.delivery_zones
ORDER BY neighborhood
LIMIT 20;
```
