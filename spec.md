# Spec — ASADERO MC CHICKEN EXPRESS Bot Backend

## Feature List

- Recibir updates de Telegram por webhook.
- Normalizar mensajes entrantes.
- Persistir mensajes recibidos.
- Aplicar idempotencia por `update_id` y `message_id`.
- Buscar o crear sesión por `chat_id`.
- Resolver intención por reglas, estado actual y lenguaje natural.
- Mostrar menú completo y por categorías.
- Seleccionar productos.
- Pedir cantidades.
- Agregar productos al carrito.
- Mostrar carrito.
- Vaciar carrito.
- Eliminar último producto.
- Iniciar checkout.
- Capturar datos del cliente en un mensaje libre o paso a paso.
- Validar datos faltantes.
- Calcular domicilio por barrio.
- Generar pedido/factura.
- Guardar pedido en PostgreSQL.
- Responder por Telegram.
- Interpretar pedidos escritos naturalmente con Gemini inicialmente.
- Usar ChromaDB para búsqueda semántica de menú, sinónimos, errores y FAQ.
- Usar Redis para cache, locks, idempotencia y sesiones rápidas.

## User Stories

- Como cliente, quiero escribir "menú" para ver las opciones disponibles.
- Como cliente, quiero pedir por categoría: asado, broaster, bebidas, adicionales o especiales.
- Como cliente, quiero escribir naturalmente "quiero medio broaster con gaseosa" y que el bot lo entienda.
- Como cliente, quiero revisar mi carrito antes de confirmar.
- Como cliente, quiero vaciar el carrito o eliminar el último producto.
- Como cliente, quiero finalizar mi pedido y enviar mis datos en un solo mensaje.
- Como cliente, quiero recibir un resumen con subtotal, domicilio y total.
- Como restaurante, quiero que los pedidos queden guardados con precios históricos.
- Como restaurante, quiero evitar pedidos duplicados por reintentos de Telegram.
- Como operador, quiero que el catálogo y las zonas se puedan sembrar y probar.

## Acceptance Criteria

- Dado un update válido de Telegram, el sistema normaliza y persiste el mensaje antes de procesarlo.
- Dado un `chat_id` nuevo, el sistema crea una sesión conversacional.
- Dado un `update_id` ya procesado, el sistema no duplica carrito, pedido ni respuesta crítica.
- Dado que el usuario pide menú, el bot responde con categorías y productos disponibles.
- Dado que el usuario selecciona producto, el bot pide cantidad.
- Dada una cantidad válida, el producto se agrega al carrito con subtotal entero COP.
- Dado carrito vacío, checkout responde que primero debe agregar productos.
- Dado checkout con datos incompletos, el bot lista datos faltantes.
- Dado barrio reconocido, se calcula domicilio según zona.
- Dado barrio no reconocido, el bot pide corregir barrio.
- Dado pedido confirmado, se persiste `order`, `order_items` con snapshots de precio y factura.
- Dado producto especial en día no permitido, el bot informa restricción.
- Dado bebida alcohólica, el producto queda marcado `requires_age_verification = true`.
- Dado pedido interpretado por LLM, el sistema valida códigos, cantidades y disponibilidad antes de tocar el carrito.

## Edge Cases

- Telegram reintenta el mismo update.
- Usuario envía cantidad cero, negativa, decimal o texto ambiguo.
- Usuario pide producto inexistente.
- Usuario escribe alias con errores: broster, broasted, media, lasaña.
- Usuario pide especiales entre semana no festivo.
- Usuario pide alcohol o el negocio decide ocultar alcohol.
- Usuario cambia de intención a mitad del checkout.
- Usuario cancela pedido con carrito activo.
- Usuario envía datos del cliente en líneas desordenadas.
- Teléfono con espacios, guiones o indicativo.
- Barrio no existe en zonas de domicilio.
- Redis no disponible temporalmente.
- ChromaDB no encuentra resultados.
- Gemini responde JSON inválido.
- Gemini devuelve producto inexistente o cantidad inválida.
- Precio cambia después de crear pedidos antiguos.

## Estados Conversacionales

- `MAIN_MENU`
- `PRODUCT_CATEGORY`
- `SELECT_ASADO`
- `SELECT_BROASTER`
- `SELECT_BEBIDA`
- `SELECT_ADICIONAL`
- `SELECT_ESPECIAL`
- `ASK_QUANTITY`
- `POST_ADD`
- `CHECKOUT_CONFIRM`
- `ASK_CUSTOMER_DATA`
- `CHECKOUT_REVIEW`
- `NATURAL_ORDER`

Estados observados en el workflow n8n que deben mapearse o conservarse como subestados:

- `pedir_nombre`
- `pedir_telefono`
- `pedir_direccion`
- `pedir_barrio`
- `pedir_observaciones`
- `pedir_pago`
- `mostrar_confirmacion`

## Intenciones Soportadas

- `mostrar_menu`
- `ver_menu`
- `menu_broaster`
- `menu_asado`
- `menu_bebidas`
- `menu_adicionales`
- `menu_especiales`
- `pedir_cantidad`
- `agregar_producto`
- `mostrar_carrito`
- `vaciar_carrito`
- `eliminar_producto`
- `resumen_checkout`
- `pedir_datos_cliente`
- `procesar_datos_cliente`
- `confirmar_pedido`
- `cancelar`
- `producto_restringido`
- `producto_inexistente`
- `horarios`
- `lenguaje_natural`
- `generar_factura`
- `guardar_nombre`
- `guardar_telefono`
- `guardar_direccion`
- `guardar_barrio`
- `guardar_observaciones`
- `pedir_pago`

## Reglas del Negocio

- El bot debe operar bajo el nombre **ASADERO MC CHICKEN EXPRESS**.
- PostgreSQL es la fuente de verdad.
- Redis no puede ser fuente principal de verdad.
- ChromaDB no puede guardar pedidos, clientes, pagos ni sesiones finales.
- La IA nunca confirma pedidos sin validación determinística.
- La confirmación del pedido requiere carrito no vacío, datos completos, domicilio resuelto y método de pago válido.
- Cancelar pedido limpia carrito temporal y sesión activa según corresponda.

## Reglas de Precios

- Los precios se guardan como enteros COP.
- No se usa `float` para dinero.
- Los precios se centralizan en seeders.
- `order_items` guarda snapshot de precio, nombre, código y subtotal al momento de crear el pedido.
- Cambios futuros de precios no alteran pedidos antiguos.
- Los tests deben validar que los precios seed coinciden exactamente con esta especificación.
- La especificación de precios aquí definida prevalece sobre cualquier precio embebido en el workflow n8n.

## Catálogo Base Autoritativo

### Pollo Asado

- `ASADO_ENTERO`: 1 Asado Entero — 44500
- `ASADO_34`: 3/4 Asado — 34000
- `ASADO_MEDIO`: 1/2 Asado — 22300
- `ASADO_CUARTO`: 1/4 Asado — 11800

### Pollo Broasted / Broaster

- `BROASTER_ENTERO`: Broasted Entero — 51000
- `BROASTER_34`: 3/4 Broasted — 38600
- `BROASTER_MEDIO`: 1/2 Broasted — 25500
- `BROASTER_CUARTO`: 1/4 Broasted — 13500

### Bebidas

- `GASEOSA`: Gaseosa — 3000
- `LATA_GASEOSA`: Lata Gaseosa — 3300
- `LITRO_MEDIO`: Litro y Medio — 8500
- `TRES_LITROS`: Tres Litros — 9000
- `PERSONAL_400`: Personal 400 ml — 3500
- `AGUA_BOTELLA`: Agua Botella — 2600
- `JUGO_LUBY`: Jugo Luby — 2400
- `GATORADE`: Gatorade — 3500
- `JUGO_HIT_LITRO_TETRA`: Jugo Hit Litro Tetra — 6000
- `COLA_POLA`: Cola y Pola — 3000

### Bebidas Alcohólicas

- `CLUB_COLOMBIA`: Club Colombia — 4400
- `PILSEN_BOTELLA`: Pilsen Botella — 4000
- `CERVEZA_LATA`: Cerveza Lata — 4400
- `CERVEZA_MILLER_LATA`: Cerveza Miller Lata — 4400

Estos productos deben tener `requires_age_verification = true`. El bot no debe promocionarlos activamente ni sugerirlos a menores. Solo se listan si el negocio lo permite y bajo cumplimiento legal.

### Especiales

- `LASAGNA_MIXTA`: Lasagna Mixta — 20000
- `MADURO_QUESO`: Maduro con Queso — 9500

`LASAGNA_MIXTA` y `MADURO_QUESO` solo están disponibles fines de semana o festivos en Colombia.

### Adicionales

- `PAPA_FRANCESA`: Papa Francesa — 8200
- `PAPA_SALADA`: Papa Salada — 5000
- `BOTELLA_VIDRIO`: Botella Vidrio — 200
- `ICOPOR`: Icopores — 900
- `ADICIONAL_SALSAS`: Adicional de Salsas — 900
- `SOPA_ADICIONAL`: Sopa Adicional — 3500
- `ICOPOR_SOPA`: Icopor Sopa — 350

### Otros

- `DOMICILIO_BASE`: Domicilio — 1000
- `ALOHA_VASO`: Aloha Vaso — 4500
- `BOCATO_CONO`: Bocato Cono — 5700
- `ARTESANAL`: Artesanal — 3500
- `PLATILLO`: Platillo — 3500
- `PALETA_DRACULA`: Paleta Dracula — 5500
- `CHOCOCONO`: Chococono — 3500
- `ALOHA_LIMON`: Aloha Limon — 2000
- `PALETA_JET`: Paleta Jet — 5000
- `CASERO`: Casero — 2500
- `POLET`: Polet — 7000
- `MINI_POLET`: Mini Polet — 6000
- `PLATILLO_JUMBO`: Platillo Jumbo — 4000

## Zonas de Domicilio

- `DOMICILIO_LAGOS_2_SANTA_COLOMA`: Lagos 2 / Santa Coloma — 2000
- `DOMICILIO_BUCARICA_BELLAVISTA`: Bucarica / Bellavista — 4000
- `DOMICILIO_CANAVERAL_FLORIDA`: Canaveral / Florida — 6000
- `DOMICILIO_PROVENZA_DIAMANTE`: Provenza / Diamante — 7000
- `DOMICILIO_CACIQUE`: Cacique — 8000
- `DOMICILIO_SAN_ANDRESITO`: San Andresito — 10000
- `DOMICILIO_CIUDADELA`: Ciudadela — 11000
- `DOMICILIO_CABECERA`: Cabecera — 12000
- `HOSPITAL_INTERNACIONAL`: Hospital Internacional — 10000
- `DOMICILIO_ADICIONAL`: Domicilio adicional — 500

## Métodos de Pago

- Datáfono
- Nequi
- Transferencia Bancolombia
- Efectivo

El workflow n8n actual usa principalmente Efectivo, Transferencia y Nequi. El backend debe soportar también Datáfono según esta especificación.

## Reglas del Carrito

- El carrito pertenece a una sesión conversacional activa.
- No se agregan productos inexistentes.
- No se agregan cantidades menores o iguales a cero.
- Cada línea guarda código, nombre, cantidad, precio unitario y subtotal.
- Mostrar carrito debe incluir productos y total acumulado.
- Vaciar carrito elimina todas las líneas activas.
- Eliminar producto quita la última línea agregada.
- Los totales se calculan con enteros COP.

## Reglas de Checkout

- No se puede iniciar checkout con carrito vacío.
- El checkout puede capturar datos en un solo mensaje o paso a paso.
- Antes de confirmar se debe mostrar resumen.
- Confirmar pedido requiere datos completos, domicilio válido y método de pago válido.
- Cancelar debe detener el checkout y limpiar estado conversacional pendiente.

## Reglas de Datos del Cliente

- Campos mínimos: nombre completo, teléfono, dirección, barrio y método de pago.
- Observaciones son opcionales y pueden default a `Ninguna`.
- Teléfono debe normalizarse removiendo separadores no numéricos.
- Teléfono incompleto debe solicitarse de nuevo.
- La extracción desde texto libre debe aceptar etiquetas como nombre, teléfono, celular, dirección, barrio, observaciones, pago y método de pago.

## Reglas de Disponibilidad

- Productos especiales `LASAGNA_MIXTA` y `MADURO_QUESO` solo se venden sábados, domingos o festivos en Colombia.
- Productos no disponibles hoy pueden mostrarse con nota si el negocio lo permite, pero no deben agregarse al carrito.
- Productos alcohólicos están restringidos y no deben promocionarse activamente.

## Reglas de Domicilio

- El domicilio se resuelve por barrio o zona.
- Si no existe zona para el barrio, no se confirma el pedido.
- El valor de domicilio se suma al subtotal para obtener total.
- Las zonas se cachean en Redis, pero se originan en PostgreSQL.

## Reglas de Productos Restringidos

- Bebidas alcohólicas requieren `requires_age_verification = true`.
- El bot no debe sugerir alcohol como upsell.
- Si se listan, debe hacerse bajo configuración del negocio y cumplimiento legal.
- El dominio debe permitir ocultar categorías restringidas por canal, horario o política.

## Reglas de IA

- Gemini es el proveedor inicial.
- El dominio solo conoce un puerto LLM, no Gemini directamente.
- El LLM debe devolver JSON estricto cuando interprete pedidos.
- Si el JSON es inválido, se responde con fallback y no se modifica carrito.
- Si el LLM devuelve códigos inexistentes, se descartan.
- Si el LLM devuelve cantidades inválidas, se descartan.
- Si no menciona cantidad, se usa 1.
- La IA no decide precios, disponibilidad, domicilio ni confirmación final.

## Reglas de Telegram

- El webhook debe responder rápido y procesar idempotentemente.
- Se debe persistir `chat_id`, `message_id`, `update_id`, texto bruto y texto normalizado.
- Las respuestas deben ser claras, cortas y orientadas a la siguiente acción.
- Los botones o teclados pueden agregarse después, pero el flujo debe funcionar por texto.
