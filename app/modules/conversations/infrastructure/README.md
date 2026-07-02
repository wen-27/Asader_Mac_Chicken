# Conversation Persistence

`telegram_sessions.cart_json` intentionally stores the active cart as JSONB for the first
PostgreSQL persistence phase. This keeps the migration small while the conversational
state machine is still being shaped.

Recommended later migration: move active cart lines into a dedicated `cart_items` table
once cart queries, partial updates, analytics, or cross-session recovery become important.
Orders already persist immutable item snapshots in `order_items`, so historical order data
does not depend on `cart_json`.

