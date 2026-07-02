# Proposal — ASADERO MC CHICKEN EXPRESS Bot Backend

## ¿Qué Estamos Construyendo?

Un backend productivo en FastAPI para operar un bot de pedidos de restaurante por Telegram para **ASADERO MC CHICKEN EXPRESS**. El sistema migrará el workflow actual de n8n a una arquitectura mantenible, modular, escalable y lista para producción.

El núcleo del sistema será **FastAPI + PostgreSQL + LangGraph**. Redis y ChromaDB serán servicios de apoyo, no fuentes principales de verdad.

## ¿Por Qué Lo Estamos Construyendo?

El workflow actual en n8n resuelve el flujo operativo inicial, pero concentra normalización, enrutamiento, lógica de negocio, consultas SQL, prompts de IA, manejo de carrito, checkout y respuestas Telegram en nodos difíciles de versionar, probar y evolucionar.

El objetivo es llevar ese comportamiento a un backend profesional donde cada regla de negocio tenga dueño claro, cobertura de pruebas y límites arquitectónicos sanos.

## Problema Actual del Workflow n8n

- Lógica conversacional dispersa entre nodos `Switch`, `Code`, `Postgres`, `Telegram` y `HTTP Request`.
- Catálogo y precios embebidos en código JavaScript del router.
- Flujo difícil de probar de forma automatizada.
- Reglas críticas como disponibilidad, domicilio, datos del cliente y confirmación de pedido mezcladas con infraestructura.
- Acoplamiento directo entre Telegram, SQL, Gemini y respuestas de usuario.
- Riesgo de inconsistencias entre precios del workflow y precios reales del negocio.
- Dificultad para implementar idempotencia, locks y reintentos confiables.
- Falta de separación entre dominio, aplicación, infraestructura y API.

## Objetivo del Backend FastAPI

Crear un backend que reciba actualizaciones de Telegram, normalice mensajes, gestione sesiones conversacionales, procese intención, administre carrito, checkout, clientes, domicilios, pedidos y facturas, usando LangGraph como máquina de estados conversacional.

El backend debe permitir usar Gemini inicialmente y cambiar a OpenAI u otro proveedor sin romper el dominio.

## Criterios de Éxito

- El bot replica el flujo funcional del workflow n8n actual.
- Los pedidos, clientes, sesiones finales, mensajes, productos, alias, zonas de domicilio y facturas quedan persistidos en PostgreSQL.
- Los precios se guardan como enteros COP y se centralizan en seeders.
- Cada pedido guarda snapshot de precio en `order_items`.
- Redis se usa para cache, locks, idempotencia y estado temporal rápido.
- ChromaDB se usa para búsqueda semántica del menú, sinónimos, errores de escritura y FAQ.
- La lógica de negocio no vive en controladores FastAPI ni en repositorios.
- El router principal de n8n queda reemplazado por LangGraph y estrategias de intención.
- Hay tests para reglas críticas, seeders de precios, carrito, checkout, domicilio, disponibilidad, IA e idempotencia.
- El stack local corre sin Docker en Python 3.9.x, con PostgreSQL, Redis y ChromaDB instalados como servicios locales.

## Alcance Dentro del Proyecto

- Backend FastAPI con arquitectura hexagonal y Vertical Slice Architecture.
- Webhook de Telegram.
- Persistencia PostgreSQL con SQLAlchemy 2 async y Alembic.
- Catálogo, precios, alias y disponibilidad.
- Sesiones conversacionales por `chat_id`.
- Carrito por sesión.
- Checkout con captura de datos del cliente.
- Cálculo de domicilio por barrio.
- Creación de pedido/factura.
- Integración inicial con Gemini vía puerto LLM.
- LangChain para interpretación y recuperación de contexto.
- LangGraph para la máquina de estados.
- Redis para cache, locks e idempotencia.
- ChromaDB para recuperación semántica.
- Tests con Pytest.
- Seeders de catálogo, alias, métodos de pago y zonas de domicilio.

## Fuera de Alcance

- Frontend administrativo.
- App móvil.
- Pasarela de pagos real.
- Gestión de repartidores en tiempo real.
- Inventario avanzado.
- Multi-sede completa salvo que se modele como extensión futura.
- Promoción activa de bebidas alcohólicas.
- Uso de ChromaDB como almacenamiento de pedidos, clientes o pagos.

## Usuarios Objetivo

- Clientes que realizan pedidos por Telegram.
- Personal del restaurante que recibe pedidos confirmados.
- Operadores técnicos que mantienen catálogo, zonas y precios.
- Futuras integraciones de canales como WhatsApp, web chat o panel administrativo.

## Canales Actuales y Futuros

- Canal actual: Telegram.
- Canales futuros: WhatsApp Business, web chat, integración POS, panel administrativo y potencial canal telefónico asistido.

## Riesgos Principales

- Precios incorrectos si se conserva el catálogo embebido del workflow como fuente de verdad.
- Doble procesamiento de updates de Telegram sin idempotencia.
- Estados conversacionales inconsistentes si Redis y PostgreSQL divergen.
- Interpretaciones erróneas del LLM si no hay validación determinística posterior.
- Guardar datos críticos en ChromaDB o Redis.
- Mezclar lógica de negocio en endpoints o repositorios.
- Falta de tests para precios, domicilio y checkout.
- Productos restringidos o especiales ofrecidos fuera de regla.

## Decisiones Iniciales

- La especificación de precios de estos documentos es autoritativa; el workflow n8n solo guía el flujo conversacional.
- PostgreSQL será la fuente de verdad.
- Redis será apoyo para cache, locks, idempotencia y estado temporal.
- ChromaDB será apoyo semántico para menú, alias, errores y FAQ.
- LangGraph reemplazará el router principal de n8n.
- LangChain orquestará prompts, parsing y recuperación cuando aplique.
- Gemini será el primer proveedor LLM detrás de un puerto intercambiable.
- FastAPI expondrá solo adaptadores/API; los casos de uso vivirán en aplicación.
- El dominio no dependerá de FastAPI, SQLAlchemy, Redis, ChromaDB, Telegram ni Gemini.
