# Tasks — ASADERO MC CHICKEN EXPRESS Bot Backend

## FASE 1 — Bootstrap del Proyecto

1. Crear estructura base `app/`, `tests/`, `alembic/`. Archivos: `app/main.py`, `tests/`, `alembic.ini`.
2. Crear configuración de proyecto Python. Archivos: `pyproject.toml`, `.python-version`, `.env.example`.
3. Agregar dependencias base: FastAPI, Pydantic v2, SQLAlchemy async, Alembic, asyncpg, Redis, ChromaDB, LangChain, LangGraph, httpx, Pytest.
4. Crear entrypoint mínimo de FastAPI sin lógica funcional. Archivos: `app/main.py`.

## FASE 2 — Configuración Base

5. Crear settings tipados. Archivos: `app/config/settings.py`.
6. Crear logging estructurado. Archivos: `app/config/logging.py`.
7. Crear manejo base de errores compartidos. Archivos: `app/shared/domain/exceptions.py`.
8. Crear utilidades de dinero y normalización de texto. Archivos: `app/shared/utils/money.py`, `app/shared/utils/text_normalizer.py`.
9. Crear calendario de festivos Colombia detrás de puerto. Archivos: `app/shared/utils/colombia_holidays.py`.

## FASE 3 — Dominio

10. Crear entidades base y value objects. Archivos: `app/shared/domain/base_entity.py`, `app/shared/domain/value_object.py`.
11. Crear value object `Money` entero COP. Archivos: `app/shared/domain/money.py`.
12. Crear dominio de catálogo. Archivos: `app/modules/catalog/domain/product.py`, `product_alias.py`.
13. Crear dominio de conversaciones. Archivos: `app/modules/conversations/domain/session.py`, `conversation_state.py`.
14. Crear dominio de carrito. Archivos: `app/modules/cart/domain/cart.py`, `cart_item.py`.
15. Crear dominio de clientes. Archivos: `app/modules/customers/domain/customer.py`.
16. Crear dominio de domicilios. Archivos: `app/modules/delivery/domain/delivery_zone.py`.
17. Crear dominio de pedidos y facturación. Archivos: `app/modules/orders/domain/order.py`, `order_item.py`, `invoice.py`.
18. Crear specifications. Archivos: `availability_spec.py`, `checkout_spec.py`, `age_restriction_spec.py`, `quantity_spec.py`, `delivery_spec.py`.

## FASE 4 — PostgreSQL y Alembic

19. Configurar engine async y sesiones. Archivos: `app/shared/infrastructure/database/engine.py`, `session.py`.
20. Crear Unit of Work. Archivos: `app/shared/application/unit_of_work.py`, `app/shared/infrastructure/database/sqlalchemy_unit_of_work.py`.
21. Crear modelos SQLAlchemy. Archivos: `app/modules/*/infrastructure/models.py`.
22. Crear migración inicial. Archivos: `alembic/versions/*_initial_schema.py`.
23. Agregar constraints e índices. Archivos: migración Alembic inicial.

## FASE 5 — Catálogo y Precios

24. Crear repositorio de catálogo como puerto. Archivos: `app/modules/catalog/application/ports.py`.
25. Crear adaptador SQLAlchemy de catálogo. Archivos: `app/modules/catalog/infrastructure/sqlalchemy_product_repository.py`.
26. Crear seeder de productos con precios exactos de `spec.md`. Archivos: `app/modules/catalog/infrastructure/seeders/catalog_seeder.py`.
27. Crear seeder de aliases obligatorios. Archivos: `app/modules/catalog/infrastructure/seeders/alias_seeder.py`.
28. Crear queries de menú por categoría. Archivos: `app/modules/catalog/application/queries/`.
29. Crear tests de precios exactos. Archivos: `tests/catalog/test_catalog_seed_prices.py`.

## FASE 6 — Telegram Webhook

30. Crear DTOs de update Telegram. Archivos: `app/modules/telegram/api/schemas.py`.
31. Crear endpoint webhook. Archivos: `app/modules/telegram/api/routes.py`.
32. Crear adaptador de envío Telegram con httpx. Archivos: `app/shared/infrastructure/telegram/telegram_sender.py`.
33. Crear repositorio de mensajes Telegram. Archivos: `app/modules/telegram/application/ports.py`, `infrastructure/sqlalchemy_message_repository.py`.
34. Crear caso de uso `HandleTelegramUpdateUseCase`. Archivos: `app/modules/telegram/application/handle_update/`.

## FASE 7 — Sesiones Conversacionales

35. Crear repositorio de sesiones. Archivos: `app/modules/conversations/application/ports.py`.
36. Crear adaptador SQLAlchemy de sesiones. Archivos: `app/modules/conversations/infrastructure/sqlalchemy_session_repository.py`.
37. Crear `GetOrCreateSessionUseCase`. Archivos: `app/modules/conversations/application/get_or_create_session/`.
38. Crear gestión de estados mínimos. Archivos: `app/modules/conversations/domain/conversation_state.py`.

## FASE 8 — LangGraph

39. Definir estado del grafo conversacional. Archivos: `app/modules/conversations/graph/state.py`.
40. Crear nodos del grafo. Archivos: `app/modules/conversations/graph/nodes.py`.
41. Crear edges condicionales por intención y estado. Archivos: `app/modules/conversations/graph/graph.py`.
42. Mapear router n8n a nodos LangGraph. Archivos: `app/modules/conversations/graph/router.py`.
43. Crear tests de rutas principales del grafo. Archivos: `tests/conversations/test_conversation_graph.py`.

## FASE 9 — Carrito

44. Crear repositorio de carrito. Archivos: `app/modules/cart/application/ports.py`.
45. Crear adaptador SQLAlchemy de carrito. Archivos: `app/modules/cart/infrastructure/sqlalchemy_cart_repository.py`.
46. Crear caso de uso agregar producto. Archivos: `app/modules/cart/application/add_product/`.
47. Crear caso de uso mostrar carrito. Archivos: `app/modules/cart/application/show_cart/`.
48. Crear caso de uso vaciar carrito. Archivos: `app/modules/cart/application/empty_cart/`.
49. Crear caso de uso eliminar último producto. Archivos: `app/modules/cart/application/remove_last_item/`.
50. Crear tests de carrito. Archivos: `tests/cart/`.

## FASE 10 — Checkout

51. Crear caso de uso iniciar checkout. Archivos: `app/modules/orders/application/start_checkout/`.
52. Crear parser de datos del cliente desde texto libre. Archivos: `app/modules/customers/application/parse_customer_data/`.
53. Crear validador de datos faltantes. Archivos: `app/modules/customers/application/validators.py`.
54. Crear caso de uso revisar checkout. Archivos: `app/modules/orders/application/review_checkout/`.
55. Crear tests de checkout. Archivos: `tests/orders/test_checkout.py`.

## FASE 11 — Clientes

56. Crear repositorio de clientes. Archivos: `app/modules/customers/application/ports.py`.
57. Crear adaptador SQLAlchemy de clientes. Archivos: `app/modules/customers/infrastructure/sqlalchemy_customer_repository.py`.
58. Crear casos de uso guardar nombre, teléfono, dirección, barrio, observaciones y pago. Archivos: `app/modules/customers/application/update_customer_data/`.
59. Crear tests de validación de teléfono y datos libres. Archivos: `tests/customers/`.

## FASE 12 — Domicilios

60. Crear repositorio de zonas de domicilio. Archivos: `app/modules/delivery/application/ports.py`.
61. Crear adaptador SQLAlchemy de zonas. Archivos: `app/modules/delivery/infrastructure/sqlalchemy_delivery_zone_repository.py`.
62. Crear seeder de zonas con precios exactos. Archivos: `app/modules/delivery/infrastructure/seeders/delivery_zone_seeder.py`.
63. Crear caso de uso resolver domicilio por barrio. Archivos: `app/modules/delivery/application/resolve_delivery/`.
64. Crear tests de zonas y barrios. Archivos: `tests/delivery/`.

## FASE 13 — Pedidos y Facturación

65. Crear repositorio de pedidos. Archivos: `app/modules/orders/application/ports.py`.
66. Crear adaptador SQLAlchemy de pedidos. Archivos: `app/modules/orders/infrastructure/sqlalchemy_order_repository.py`.
67. Crear generación de número de pedido. Archivos: `app/modules/orders/application/order_number.py`.
68. Crear caso de uso confirmar pedido. Archivos: `app/modules/orders/application/confirm_order/`.
69. Crear generación de factura/resumen. Archivos: `app/modules/orders/application/generate_invoice/`.
70. Crear tests de snapshot de precios. Archivos: `tests/orders/test_order_price_snapshots.py`.

## FASE 14 — LangChain

71. Crear puerto LLM. Archivos: `app/modules/ai/application/ports.py`.
72. Crear prompt template de interpretación de pedidos. Archivos: `app/modules/ai/application/prompts/natural_order_prompt.py`.
73. Crear parser estructurado de respuesta LLM. Archivos: `app/modules/ai/application/parsers.py`.
74. Crear caso de uso interpretar pedido natural. Archivos: `app/modules/ai/application/interpret_natural_order/`.
75. Crear tests con respuestas Gemini simuladas. Archivos: `tests/ai/test_natural_order_parser.py`.

## FASE 15 — ChromaDB

76. Crear adaptador ChromaDB. Archivos: `app/shared/infrastructure/chroma/client.py`.
77. Crear puerto de búsqueda semántica. Archivos: `app/modules/ai/application/semantic_search_port.py`.
78. Crear indexador de menú desde PostgreSQL. Archivos: `app/modules/catalog/infrastructure/chroma_menu_indexer.py`.
79. Crear búsqueda semántica de productos y FAQ. Archivos: `app/modules/ai/infrastructure/chroma_menu_search.py`.
80. Crear tests de fallback semántico con fakes. Archivos: `tests/ai/test_semantic_menu_search.py`.

## FASE 16 — Redis

81. Crear cliente Redis. Archivos: `app/shared/infrastructure/redis/client.py`.
82. Crear cache de catálogo. Archivos: `app/modules/catalog/infrastructure/redis_catalog_cache.py`.
83. Crear cache de zonas. Archivos: `app/modules/delivery/infrastructure/redis_delivery_cache.py`.
84. Crear locks por `chat_id`. Archivos: `app/shared/infrastructure/redis/locks.py`.
85. Crear idempotencia por `update_id` y `message_id`. Archivos: `app/shared/infrastructure/redis/idempotency.py`.
86. Crear tests de idempotencia con fake Redis. Archivos: `tests/telegram/test_idempotency.py`.

## FASE 17 — Tests

87. Configurar Pytest async. Archivos: `pytest.ini` o `pyproject.toml`, `tests/conftest.py`.
88. Crear fixtures de base de datos. Archivos: `tests/fixtures/`.
89. Crear tests unitarios de dominio. Archivos: `tests/domain/`.
90. Crear tests de aplicación por módulo. Archivos: `tests/*/`.
91. Crear tests de integración de repositorios. Archivos: `tests/integration/`.
92. Crear tests del webhook Telegram. Archivos: `tests/telegram/test_webhook.py`.

## FASE 18 — Runtime Local sin Docker

93. Fijar compatibilidad de runtime en Python 3.9.x. Archivos: `pyproject.toml`, `.python-version`.
94. Crear script de arranque local para PostgreSQL, Redis, ChromaDB y API. Archivos: `scripts/local_dev.py`.
95. Crear comandos locales de migración, seed, health y tunel. Archivos: `Makefile`.
96. Crear comandos de migración y seed. Archivos: `Makefile` o scripts en `scripts/`.
97. Documentar variables de entorno. Archivos: `.env.example`, `README.md`.

## FASE 19 — Validación Final

98. Validar que no existe lógica de negocio en controladores FastAPI. Archivos: revisión `app/modules/*/api/`.
99. Validar que repositorios no tienen lógica de negocio compleja. Archivos: revisión `app/modules/*/infrastructure/`.
100. Validar que Redis y ChromaDB no guardan datos críticos finales. Archivos: revisión adaptadores.
101. Ejecutar tests completos. Comando esperado: `pytest`.
102. Levantar stack completo. Comando esperado: `python -m scripts.local_dev`.
103. Probar flujo manual: menú, producto, cantidad, carrito, checkout, domicilio, confirmación.
104. Probar flujo lenguaje natural con Gemini.
105. Probar reintento de Telegram y confirmar idempotencia.
106. Revisar que precios seed coinciden exactamente con `spec.md`.
