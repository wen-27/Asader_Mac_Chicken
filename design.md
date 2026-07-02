# Design — ASADERO MC CHICKEN EXPRESS Bot Backend

## Decisiones de Arquitectura

- Usar arquitectura hexagonal con Vertical Slice Architecture.
- Organizar reglas por módulos de negocio: Telegram, conversaciones, catálogo, carrito, clientes, domicilio, pedidos e IA.
- Mantener dominio puro sin dependencias de FastAPI, SQLAlchemy, Redis, ChromaDB, Telegram ni Gemini.
- Usar casos de uso en capa de aplicación.
- Usar repositorios como puertos; SQLAlchemy async implementa adaptadores.
- Usar Unit of Work para transacciones.
- Usar Strategy Pattern para resolver intenciones.
- Usar LangGraph como máquina de estados conversacional.
- Usar Factory Pattern para mensajes del bot.
- Usar Specification Pattern para disponibilidad, checkout, domicilio, cantidades y restricciones.
- Usar DTOs Pydantic v2 para entrada/salida de aplicación y API.

## Stack Técnico

- Python 3.9.x
- FastAPI
- Pydantic v2
- SQLAlchemy 2 async
- Alembic
- PostgreSQL
- LangChain
- LangGraph
- Redis
- ChromaDB
- httpx
- Servicios locales sin Docker para desarrollo en esta maquina
- Pytest
- Gemini como proveedor LLM inicial

## Estructura de Carpetas

```text
app/
  main.py
  config/
    settings.py
    logging.py
  shared/
    domain/
      base_entity.py
      value_object.py
      exceptions.py
    application/
      unit_of_work.py
      result.py
    infrastructure/
      database/
      redis/
      chroma/
      telegram/
      llm/
    utils/
      text_normalizer.py
      money.py
      colombia_holidays.py
  modules/
    telegram/
      domain/
      application/
      infrastructure/
      api/
    conversations/
      domain/
      application/
      infrastructure/
      graph/
    catalog/
      domain/
      application/
      infrastructure/
      api/
    cart/
      domain/
      application/
      infrastructure/
    customers/
      domain/
      application/
      infrastructure/
    delivery/
      domain/
      application/
      infrastructure/
    orders/
      domain/
      application/
      infrastructure/
      api/
    ai/
      domain/
      application/
      infrastructure/
      graph/
  tests/
```

Cada módulo puede organizar vertical slices con:

- `command`
- `handler`
- `query`
- `schemas` o `dtos`
- `validator`
- `repository port`
- `repository adapter`

## Diagrama Textual del Flujo

```text
Telegram Update
  -> FastAPI webhook
  -> Verify idempotency and lock by update_id/message_id/chat_id
  -> Normalize message
  -> Persist inbound telegram message
  -> Load or create conversation session
  -> Build ConversationContext
  -> LangGraph conversation graph
       -> Resolve intent strategy
       -> Execute use case
       -> Persist state changes with Unit of Work
       -> Build bot response
  -> Send Telegram response through adapter
  -> Persist outbound message metadata
  -> Release lock
```

## Reemplazo del Router n8n con LangGraph

El nodo `Router principal` de n8n se reemplaza por un grafo LangGraph con nodos pequeños:

- `load_context`
- `normalize_input`
- `resolve_intent`
- `route_by_intent`
- `show_menu`
- `select_product`
- `ask_quantity`
- `add_to_cart`
- `show_cart`
- `empty_cart`
- `remove_last_item`
- `start_checkout`
- `collect_customer_data`
- `resolve_delivery`
- `review_checkout`
- `confirm_order`
- `cancel`
- `natural_order`
- `fallback`

El `Switch` de n8n se reemplaza por edges condicionales de LangGraph basados en intención, estado y validaciones de dominio.

## Separación de FastAPI y Lógica de Negocio

FastAPI solo debe:

- Recibir requests.
- Validar DTOs de API.
- Resolver dependencias con `Depends`.
- Llamar casos de uso.
- Devolver respuestas HTTP.

FastAPI no debe:

- Calcular precios.
- Resolver disponibilidad.
- Mutar carrito directamente.
- Confirmar pedidos.
- Construir prompts complejos.
- Ejecutar SQL de negocio.

## Uso de PostgreSQL

PostgreSQL es la fuente de verdad para:

- Mensajes Telegram.
- Sesiones conversacionales persistentes.
- Productos.
- Alias.
- Zonas de domicilio.
- Clientes.
- Carritos o snapshots de carrito activo, según decisión de implementación.
- Pedidos.
- Items de pedido.
- Facturas.
- Estados y auditoría.

## Uso de Redis

Redis se usa para:

- Cache de catálogo.
- Cache de zonas de domicilio.
- Cache de sesión conversacional por `chat_id`.
- Locks por `chat_id` para evitar procesamiento concurrente.
- Idempotencia por `update_id` y `message_id`.
- Estado temporal rápido si aplica.

Redis no guarda la verdad final de pedidos, clientes, pagos ni sesiones finales.

## Uso de ChromaDB

ChromaDB se usa para:

- Búsqueda semántica del menú.
- Sinónimos de productos.
- Productos escritos con errores.
- Preguntas frecuentes.
- Contexto de recuperación para lenguaje natural.

ChromaDB no guarda pedidos, clientes, pagos ni sesiones finales.

## Uso de LangChain

LangChain se usa para:

- Plantillas de prompt.
- Parsing estructurado de respuestas del LLM.
- Recuperación de contexto desde ChromaDB.
- Cadena de interpretación de pedidos naturales.
- Encapsular proveedor Gemini detrás de un puerto.

## Uso de LangGraph

LangGraph se usa como máquina de estados:

- Estado de grafo: `chat_id`, texto normalizado, sesión, intención, producto seleccionado, cantidad, carrito, datos de cliente, errores, respuesta.
- Nodos determinísticos para reglas críticas.
- Nodo de lenguaje natural solo cuando intención o texto lo requiere.
- Edges condicionales para estados conversacionales.
- Persistencia de estado final vía casos de uso y Unit of Work.

## Modelos de Datos

Modelos principales:

- Telegram message.
- Conversation session.
- Product.
- Product alias.
- Delivery zone.
- Customer.
- Cart item.
- Order.
- Order item.
- Invoice.
- Payment method.
- Outbox message opcional para respuestas.

## Tablas

Tablas probables:

- `telegram_messages`
- `telegram_sessions`
- `products`
- `product_aliases`
- `delivery_zones`
- `customers`
- `cart_items`
- `orders`
- `order_items`
- `invoices`
- `payment_methods`
- `processed_updates`
- `outbox_messages`

Tablas observadas o inferidas del workflow n8n:

- `telegram_messages`
- `telegram_sessions`
- `cart_items`
- `delivery_zones`
- `orders`

## Entidades de Dominio

- `Product`
- `ProductAlias`
- `Money`
- `Cart`
- `CartItem`
- `ConversationSession`
- `Customer`
- `DeliveryZone`
- `Order`
- `OrderItem`
- `Invoice`
- `PaymentMethod`
- `TelegramMessage`

## Adaptadores

- `TelegramWebhookAdapter`
- `TelegramBotHttpAdapter`
- `SqlAlchemyProductRepository`
- `SqlAlchemySessionRepository`
- `SqlAlchemyCartRepository`
- `SqlAlchemyCustomerRepository`
- `SqlAlchemyDeliveryRepository`
- `SqlAlchemyOrderRepository`
- `RedisCacheAdapter`
- `RedisLockAdapter`
- `RedisIdempotencyAdapter`
- `ChromaMenuSearchAdapter`
- `GeminiLLMAdapter`

## Puertos

- `ProductRepository`
- `SessionRepository`
- `MessageRepository`
- `CartRepository`
- `CustomerRepository`
- `DeliveryZoneRepository`
- `OrderRepository`
- `InvoiceRepository`
- `UnitOfWork`
- `TelegramSender`
- `CachePort`
- `LockPort`
- `IdempotencyPort`
- `SemanticMenuSearchPort`
- `LLMIntentParserPort`
- `HolidayCalendarPort`

## Servicios de Aplicación

- `HandleTelegramUpdateUseCase`
- `NormalizeTelegramMessageUseCase`
- `GetOrCreateSessionUseCase`
- `ResolveIntentUseCase`
- `ShowMenuUseCase`
- `SelectProductUseCase`
- `AddProductToCartUseCase`
- `ShowCartUseCase`
- `EmptyCartUseCase`
- `RemoveLastCartItemUseCase`
- `StartCheckoutUseCase`
- `ProcessCustomerDataUseCase`
- `ResolveDeliveryUseCase`
- `CreateOrderUseCase`
- `GenerateInvoiceUseCase`
- `InterpretNaturalOrderUseCase`

## Estrategia de Testing

- Unit tests para value objects y specifications.
- Unit tests para resolución de intención.
- Unit tests para reglas de disponibilidad de especiales.
- Unit tests para productos restringidos.
- Unit tests para dinero sin floats.
- Tests de seeders de precios exactos.
- Tests de aliases obligatorios.
- Tests de carrito.
- Tests de checkout.
- Tests de domicilio.
- Tests de parsing de datos del cliente.
- Tests de LLM con respuestas simuladas.
- Tests de LangGraph con rutas principales.
- Integration tests para repositorios SQLAlchemy.
- Integration tests para webhook Telegram con dependencias fake.
- Tests de idempotencia y locks.

## Estrategia de Migraciones

- Alembic será la única herramienta de cambios de esquema.
- Cada módulo dueño propone sus tablas, pero las migraciones se integran en una secuencia lineal.
- Usar UUIDs o IDs enteros según convención elegida en bootstrap.
- Agregar constraints para códigos únicos, precios no negativos, cantidades positivas y estados válidos.
- Agregar índices por `chat_id`, `update_id`, `message_id`, `product_code`, `order_number` y `neighborhood`.

## Estrategia de Seeders

- Seeders versionados para catálogo, alias, zonas de domicilio y métodos de pago.
- Los seeders deben ser idempotentes.
- Los precios seed deben coincidir exactamente con `spec.md`.
- Los aliases mínimos obligatorios son:
  - broaster
  - broasted
  - broster
  - pollo broaster
  - medio pollo
  - media
  - gaseosa litro y medio
  - coca litro y medio
  - lasana
  - lasagna
  - maduro
  - papa
  - papa francesa
- Al sembrar ChromaDB, el origen será PostgreSQL, no archivos duplicados de catálogo.

## Mapeo del Workflow n8n

- `Telegram Trigger` -> webhook FastAPI.
- `Normalizar mensaje` -> normalizer + DTO de entrada.
- `Guardar mensaje recibido` -> `MessageRepository`.
- `Buscar o crear sesión` -> `GetOrCreateSessionUseCase`.
- `Router principal` -> LangGraph + Intent Strategies.
- `Switch` -> conditional edges de LangGraph.
- Nodos `Execute a SQL query*` -> repositorios + Unit of Work.
- Nodos `Send a text message*` -> `BotMessageFactory` + `TelegramSender`.
- `Extraer datos factura` -> parser de datos del cliente.
- `Preparar prompt Gemini` -> LangChain prompt template.
- `Gemini interpretar pedido` -> `GeminiLLMAdapter`.
- `Parsear respuesta Gemini` -> structured parser + validaciones de dominio.
- `Agregar productos IA al carrito` -> `AddProductToCartUseCase`.
- `Generar factura final` -> `CreateOrderUseCase` + `GenerateInvoiceUseCase`.
