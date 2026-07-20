"""Centralized Telegram message copy for the conversation graph.

User-facing text should live here instead of inside nodes. That keeps the graph
focused on state transitions and makes UX/copy changes safer.
"""

from __future__ import annotations

from app.modules.catalog.domain.product import Product
from app.modules.conversations.graph.state import CartLineState, ConversationGraphState


class BotMessageFactory:
    BUSINESS_NAME = "ASADERO MC CHICKEN EXPRESS"
    NEQUI_ACCOUNT_NUMBER = "3182705144"
    NEQUI_ACCOUNT_HOLDER = "Fabio Leonardo Perez"
    # Category titles are intentionally friendly and emoji-based because these
    # are sent directly to WhatsApp/Telegram-style chat users.
    CATEGORY_TITLES = {
        "POLLO_ASADO": "🍗 Pollo asado",
        "POLLO_BROASTER": "🍗 Pollo broaster",
        "BEBIDAS": "🥤 Bebidas",
        "BEBIDAS_ALCOHOLICAS": "🍺 Bebidas alcoholicas",
        "ADICIONALES": "🍟 Adicionales",
        "ESPECIALES": "⭐ Platos especiales",
        "HELADOS": "🍦 Helados",
    }

    @classmethod
    def main_menu(cls) -> str:
        return "\n\n".join(
            [
                "🍗 ¡Bienvenid@ a Mac Chicken!",
                "Estamos listos para atenderte con mucho gusto. ¿En que podemos servirte hoy?",
                "📍 Cra 3 # 48-06, Lagos II, Floridablanca.",
                "🕒 Horario: lunes a domingo, 10:00 a. m. a 4:00 p. m.",
                "Te compartimos nuestro menu para que puedas escoger facil. Si deseas un domicilio, puedes enviarnos tu orden y estos datos en un solo mensaje:",
                "\n".join(
                    [
                        "Nombre:",
                        "Direccion y barrio:",
                        "Telefono:",
                        "Metodo de pago:",
                        "Nota o especificacion (opcional):",
                    ]
                ),
                "💳 Metodos de pago: Efectivo, Datafono, Nequi o Transferencia Bancolombia.",
                "Si tienes dudas o antojos, escribenos sin pena. En un momento te ayudamos con tu orden 🙌",
                "Tambien puedes seleccionar:",
                "\n".join(["🥤 Bebidas", "🍟 Adicionales"]),
            ]
        )

    @classmethod
    def customer_data_requirements_intro(cls) -> str:
        return "\n\n".join(
            [
                "📦 Para preparar tu orden necesitaremos estos datos:",
                "\n".join(
                    [
                        "Nombre completo",
                        "Telefono",
                        "Direccion",
                        "Barrio",
                        "Nota o especificacion (opcional)",
                        "Metodo de pago",
                    ]
                ),
                "💳 Metodos de pago: Efectivo, Datafono, Nequi o Transferencia Bancolombia.",
                "Cuando tengas lista tu orden, puedes enviarlos en un solo mensaje, en lineas separadas o como te quede mas facil.",
            ]
        )

    @classmethod
    def product_categories(cls) -> str:
        return "\n".join(
            [
                "📋 Elige una categoria:",
                "",
                "1. 🍗 Pollo asado",
                "2. 🍗 Pollo broaster",
                "3. 🥤 Bebidas",
                "4. 🍟 Adicionales",
                "5. ⭐ Platos especiales",
                "6. ✅ Finalizar orden",
                "0. ⬅️ Volver al inicio",
            ]
        )

    @classmethod
    def product_menu(cls, title: str, products: list[Product]) -> str:
        friendly_title = cls.CATEGORY_TITLES.get(title, title.replace("_", " ").title())
        if not products:
            return "\n".join(
                [
                    friendly_title,
                    "",
                    "Por ahora no hay productos disponibles en esta categoria.",
                    "",
                    "Puedes elegir otra categoria:",
                    "",
                    "1. 🍗 Pollo asado",
                    "2. 🍗 Pollo broaster",
                    "3. 🥤 Bebidas",
                    "4. 🍟 Adicionales",
                    "6. ✅ Finalizar orden",
                    "0. ⬅️ Volver al inicio",
                ]
            )
        lines = [friendly_title, ""]
        for index, product in enumerate(products, start=1):
            lines.append(f"{index}. {product.name.value} - ${product.price.amount}")
        lines.append("")
        lines.append("Selecciona el numero del producto que quieres añadir.")
        lines.append("0. ⬅️ Volver a categorias")
        return "\n".join(lines)

    @classmethod
    def ask_quantity(cls, product_name: str, price_cop: int) -> str:
        return "\n\n".join(
            [
                f"🛒 {product_name}",
                f"Precio unitario: ${price_cop}",
                "¿Cuantas unidades deseas añadir?",
                "0. ⬅️ Volver a categorias",
            ]
        )

    @classmethod
    def ask_chicken_part(cls, product_name: str) -> str:
        return "\n".join(
            [
                f"🍗 {product_name}",
                "",
                "¿Lo quieres en pierna o pechuga?",
                "",
                "1. Pierna",
                "2. Pechuga",
                "0. ⬅️ Volver a categorias",
            ]
        )

    @classmethod
    def ask_chicken_style(cls, product_name: str = "Pollo") -> str:
        return "\n".join(
            [
                f"🍗 {product_name}",
                "",
                "¿Lo quieres asado o broster?",
                "",
                "1. Asado",
                "2. Broster",
                "0. ⬅️ Volver a categorias",
            ]
        )

    @classmethod
    def ask_quarter_distribution(cls, product_name: str, remaining: int) -> str:
        return "\n".join(
            [
                f"🍗 {product_name}",
                "",
                f"Me faltan definir {remaining} cuarto(s).",
                "Dime como los quieres en pierna o pechuga.",
                "Ejemplos: 2 pechugas, 2 piernas, o solo pechuga.",
                "0. ⬅️ Volver a categorias",
            ]
        )

    @classmethod
    def ask_quarter_distribution_quantity(cls, part: str, remaining: int) -> str:
        return "\n".join(
            [
                f"Perfecto, {part.lower()}.",
                f"¿Cuantos cuarto(s) quieres en {part.lower()}? Me faltan {remaining}.",
                "0. ⬅️ Volver a categorias",
            ]
        )

    @classmethod
    def ask_chicken_composition(cls, product_name: str) -> str:
        return "\n".join(
            [
                f"🍗 {product_name}",
                "",
                "¿Como quieres la presa?",
                "",
                "1. 2 piernas y 1 pechuga",
                "2. 2 pechugas y 1 pierna",
                "0. ⬅️ Volver a categorias",
            ]
        )

    @classmethod
    def ask_product_variant(cls, product_name: str, options: tuple[str, ...]) -> str:
        lines = [f"🛒 {product_name}", "", "Elige una opcion:"]
        lines.extend(f"{index}. {option}" for index, option in enumerate(options, start=1))
        lines.append("0. ⬅️ Volver a categorias")
        return "\n".join(lines)

    @classmethod
    def ask_side_extra(cls) -> str:
        return "\n".join(
            [
                "La yuca para broaster seria un adicional.",
                "",
                "¿Cual quieres añadir?",
                "",
                "1. Yuca frita - $5000",
                "2. Papa o yuca salada - $5000",
                "0. ⬅️ Volver a categorias",
            ]
        )

    @classmethod
    def included_side_clarification(cls) -> str:
        return (
            "Te lo dejo con el acompañamiento incluido. "
            "Si quieres añadir una porcion adicional, escribeme por ejemplo: adicional de papa francesa."
        )

    @classmethod
    def product_unavailable(
        cls,
        product_name: str | None = None,
        alternatives: tuple[str, ...] = (),
        reason: str = "out_of_stock",
    ) -> str:
        label = product_name or "Ese producto"
        normalized_label = label.strip().lower()
        if reason == "restricted" and normalized_label in {"lasagna mixta", "maduro con queso"}:
            lines = [f"⚠️ Por ahora {label} solo esta disponible fines de semana o lunes festivos."]
        elif normalized_label in {"lasagna mixta", "maduro con queso"}:
            lines = [f"⚠️ En este momento no tenemos {label} disponible. Disculpa la molestia."]
        elif reason == "restricted":
            lines = [f"⚠️ {label} solo esta disponible fines de semana o lunes festivos."]
        else:
            lines = [f"⚠️ {label} no esta disponible en este momento."]
        if alternatives:
            lines.append("")
            lines.append("Puedo ofrecerte estas alternativas disponibles:")
            lines.extend(f"- {alternative}" for alternative in alternatives)
        else:
            lines.append("Puedes elegir otra opcion disponible del menu.")
            lines.append("Selecciona menu para ver las opciones.")
        return "\n".join(lines)

    @classmethod
    def stock_alternative_prompt(
        cls,
        unavailable_product_name: str,
        recommended_product_name: str,
        reason: str = "out_of_stock",
    ) -> str:
        normalized_name = unavailable_product_name.strip().lower()
        if reason == "restricted" and normalized_name in {"lasagna mixta", "maduro con queso"}:
            first_line = f"⚠️ Por ahora {unavailable_product_name} solo esta disponible fines de semana o lunes festivos."
        elif normalized_name in {"lasagna mixta", "maduro con queso"}:
            first_line = f"⚠️ En este momento no tenemos {unavailable_product_name} disponible. Disculpa la molestia."
        elif reason == "restricted":
            first_line = f"⚠️ {unavailable_product_name} solo esta disponible fines de semana o lunes festivos."
        else:
            first_line = f"⚠️ {unavailable_product_name} no esta disponible en este momento."
        return "\n\n".join(
            [
                first_line,
                f"Te puedo ofrecer {recommended_product_name}, que es la opcion mas cercana disponible.",
                "¿Quieres seguir con esta opcion o prefieres ver el menu?",
            ]
        )

    @classmethod
    def stock_alternative_invalid(cls, recommended_product_name: str | None = None) -> str:
        option = recommended_product_name or "la opcion recomendada"
        return "\n\n".join(
            [
                f"Selecciona Si para seguir con {option}.",
                "Tambien puedes seleccionar Ver menu para escoger otra opcion.",
            ]
        )

    @classmethod
    def product_not_found(cls) -> str:
        return "No encontre ese producto en este momento. Selecciona menu para ver las opciones disponibles."

    @classmethod
    def ambiguous_chicken_order(cls) -> str:
        return "\n".join(
            [
                "Claro, te ayudo con el pollo.",
                "",
                "Para evitar confusiones, dime cual quieres:",
                "",
                "1. 🍗 Pollo asado",
                "2. 🍗 Pollo broaster",
                "0. ⬅️ Volver al inicio",
            ]
        )

    @classmethod
    def invalid_quantity(cls) -> str:
        return "Por favor envia una cantidad valida. Ejemplo: 1, 2 o 3."

    @classmethod
    def added_to_cart(cls, line: CartLineState, total_cop: int) -> str:
        return "\n\n".join(
            [
                "✅ Añadido a tu orden.",
                f"{line.quantity} x {line.product_name} = ${line.subtotal_cop}",
                f"🧾 Total acumulado: ${total_cop}",
                "¿Que quieres hacer ahora?",
                "\n".join(
                    [
                        "1. Añadir más productos ➕",
                        "2. Ver orden 🧾",
                        "3. Finalizar orden ✅",
                        "4. Vaciar orden 🗑️",
                        "0. Volver a categorias ⬅️",
                    ]
                ),
            ]
        )

    @classmethod
    def natural_order_added(cls, lines: list[CartLineState], total_cop: int) -> str:
        added_lines = "\n".join(
            f"- {line.quantity} x {line.product_name}: ${line.subtotal_cop}" for line in lines
        )
        return "\n\n".join(
            [
                "✅ Añadido a tu orden.",
                added_lines,
                f"🧾 Total acumulado: ${total_cop}",
                "Para confirmar tu orden, enviame tus datos cuando puedas:",
                "\n".join(
                    [
                        "Nombre completo",
                        "Telefono",
                        "Direccion",
                        "Barrio",
                        "Metodo de pago",
                    ]
                ),
            ]
        )

    @classmethod
    def ambiguous_drink_clarification(cls, quantity: int | None = None) -> str:
        prefix = (
            f"Veo que tambien quieres {quantity} gaseosas."
            if quantity and quantity > 1
            else "Veo que tambien quieres una gaseosa."
        )
        return (
            f"{prefix} Para no añadirte una bebida equivocada, dime cual deseas:\n\n"
            "1. Coca-Cola personal 400 ml - $3500\n"
            "2. Coca-Cola 1.5 L - $8500\n"
            "3. Gaseosa 2.5 L - $8500\n"
            "4. Jugos Hit personal - $3000"
        )

    @classmethod
    def coca_cola_clarification(cls) -> str:
        return "\n".join(
            [
                "Claro. ¿Cual Coca-Cola quieres añadir?",
                "",
                "1. Coca-Cola personal 400 ml - $3500",
                "2. Coca-Cola 1.5 L - $8500",
                "",
                "Puedes responder con el numero o escribir: Coca-Cola personal / Coca-Cola 1.5.",
            ]
        )

    @classmethod
    def water_clarification(cls) -> str:
        return "\n".join(
            [
                "Claro. Tenemos agua botella por $2600.",
                "",
                "¿Cual quieres?",
                "",
                "1. Con gas",
                "2. Sin gas",
                "3. Saborizada",
                "",
                "Puedes responder con el numero o escribir el tipo de agua.",
            ]
        )

    @classmethod
    def natural_order_added_with_side_question(
        cls,
        lines: list[CartLineState],
        total_cop: int,
    ) -> str:
        added_lines = "\n".join(
            f"- {line.quantity} x {line.product_name}: ${line.subtotal_cop}" for line in lines
        )
        return "\n\n".join(
            [
                "✅ Añadido a tu orden.",
                added_lines,
                f"🧾 Total acumulado: ${total_cop}",
                cls.ask_side_extra(),
            ]
        )

    @classmethod
    def cart(cls, cart: list[CartLineState], total_cop: int) -> str:
        if not cart:
            return "🧾 Tu orden esta vacia. Escribe menu para ver opciones."
        lines = ["🧾 Tu orden:", ""]
        for line in cart:
            lines.append(f"- {line.quantity} x {line.product_name}: ${line.subtotal_cop}")
        lines.append("")
        lines.append(f"Total: ${total_cop}")
        lines.append("")
        lines.append("1. Añadir más productos ➕")
        lines.append("2. Ver orden 🧾")
        lines.append("3. Finalizar orden ✅")
        lines.append("4. Vaciar orden 🗑️")
        lines.append("0. Volver al inicio ⬅️")
        return "\n".join(lines)

    @classmethod
    def clear_cart(cls) -> str:
        return "🗑️ Listo, vacie tu orden. Puedes ordenar de nuevo cuando quieras."

    @classmethod
    def remove_last_item(cls, removed_name: str | None) -> str:
        if removed_name is None:
            return "🧾 Tu orden esta vacia. No hay productos para eliminar."
        return f"Listo, quite {removed_name} de tu orden."

    @classmethod
    def cart_replaced_items(
        cls,
        removed_names: list[str],
        added_lines: list[CartLineState],
        total_cop: int,
    ) -> str:
        removed_text = ", ".join(removed_names) if removed_names else "el producto indicado"
        added_text = "\n".join(
            f"- {line.quantity} x {line.product_name}: ${line.subtotal_cop}" for line in added_lines
        )
        return "\n\n".join(
            [
                f"Listo, quite {removed_text} de tu orden y añadí lo que prefieres.",
                added_text,
                f"🧾 Total acumulado: ${total_cop}",
                "¿Que quieres hacer ahora?",
                "\n".join(
                    [
                        "1. Añadir más productos ➕",
                        "2. Ver orden 🧾",
                        "3. Finalizar orden ✅",
                        "4. Vaciar orden 🗑️",
                        "0. Volver a categorias ⬅️",
                    ]
                ),
            ]
        )

    @classmethod
    def checkout_summary(cls, state: ConversationGraphState) -> str:
        if not state.cart:
            return "🧾 Tu orden esta vacia. Primero añade productos a tu orden."
        return "\n\n".join(
            [
                "🧾 Resumen de tu orden:",
                cls.cart(state.cart, state.subtotal_cop),
                "¿Confirmas tu orden? Selecciona SI para confirmar o NO para cancelar.",
            ]
        )

    @classmethod
    def ask_customer_data(cls, soup_available: bool = True) -> str:
        sections = [
            "📦 Para finalizar tu orden necesito los datos de envio:",
            "\n".join(
                [
                    "Nombre completo",
                    "Telefono",
                    "Direccion",
                    "Barrio",
                    "Nota o especificacion (opcional)",
                    "Metodo de pago",
                ]
            ),
            "💳 Metodos de pago: Efectivo, Datafono, Nequi o Transferencia Bancolombia.",
        ]
        if not soup_available:
            sections.append("Lo sentimos, en este momento no tenemos sopa disponible.")
        sections.extend(
            [
                "Puedes enviarlos en un solo mensaje, en lineas separadas o como te quede mas facil.",
                "0. ⬅️ Volver a tu orden",
            ]
        )
        return "\n\n".join(sections)

    @classmethod
    def ask_pickup_customer_data(cls, soup_available: bool = True) -> str:
        sections = [
            "📦 Para dejar tu orden lista para recoger necesito estos datos:",
            "\n".join(
                [
                    "Nombre completo",
                    "Telefono",
                    "Nota o especificacion (opcional)",
                ]
            ),
        ]
        if not soup_available:
            sections.append("Lo sentimos, en este momento no tenemos sopa disponible.")
        sections.extend(
            [
                "Puedes enviarlos en un solo mensaje, en lineas separadas o como te quede mas facil.",
                "0. ⬅️ Volver a tu orden",
            ]
        )
        return "\n\n".join(sections)

    @classmethod
    def missing_customer_data(cls, missing: list[str]) -> str:
        return "\n\n".join(
            [
                "Me falta esta informacion: " + ", ".join(missing),
                "Puedes enviarla en texto normal, en un solo mensaje o en varias lineas.",
            ]
        )

    @classmethod
    def order_created(cls, state: ConversationGraphState) -> str:
        if state.fulfillment_type == "PICKUP":
            return "\n\n".join(
                [
                    "✅ Datos recibidos. Revisa tu orden para recoger:",
                    cls.cart(state.cart, state.subtotal_cop),
                    "\n".join(
                        [
                            f"👤 Cliente: {state.customer.name}",
                            f"📞 Telefono: {state.customer.phone}",
                            f"📝 Nota: {state.customer.observations or 'Sin nota'}",
                            "📍 Entrega: Recoge en local",
                        ]
                    ),
                    "\n".join(
                        [
                            f"Subtotal: ${state.subtotal_cop}",
                            "Domicilio: $0",
                            f"Total: ${state.total_cop}",
                        ]
                    ),
                    "¿Confirmas tu orden? Selecciona SI para confirmar o NO para cancelar.",
                ]
            )
        return "\n\n".join(
            [
                "✅ Datos recibidos. Revisa tu orden:",
                cls.cart(state.cart, state.subtotal_cop),
                "\n".join(
                    [
                        f"👤 Cliente: {state.customer.name}",
                        f"📞 Telefono: {state.customer.phone}",
                        f"📍 Direccion: {state.customer.address}",
                        f"🏘️ Barrio: {state.customer.neighborhood}",
                        f"📝 Nota: {state.customer.observations or 'Sin nota'}",
                        f"💳 Pago: {state.customer.payment_method}",
                    ]
                ),
                "\n".join(
                    [
                        f"Subtotal: ${state.subtotal_cop}",
                        f"Domicilio: ${state.delivery_price_cop or 0}",
                        f"Total: ${state.total_cop}",
                    ]
                ),
                "¿Confirmas tu orden? Selecciona SI para confirmar o NO para cancelar.",
            ]
        )

    @classmethod
    def confirmed(cls, requires_payment_proof: bool = False) -> str:
        if not requires_payment_proof:
            return "✅ Orden confirmada. Gracias por tu orden."
        return "\n\n".join(
            [
                "✅ Orden confirmada. Gracias por tu orden.",
                cls.payment_account_answer(),
                "Para poder preparar tu orden, por favor envianos el comprobante de pago por este mismo chat.",
            ]
        )

    @classmethod
    def payment_account_answer(cls) -> str:
        return (
            f"La cuenta de Nequi es {cls.NEQUI_ACCOUNT_NUMBER} "
            f"a nombre de {cls.NEQUI_ACCOUNT_HOLDER}."
        )

    @classmethod
    def payment_methods_answer(cls) -> str:
        return "Si, recibimos Efectivo, Datafono, Nequi o Transferencia Bancolombia."

    @classmethod
    def gratitude_answer(cls) -> str:
        return "Con mucho gusto, gracias a ti por elegirnos."

    @classmethod
    def order_confirmation_failed(cls) -> str:
        return (
            "No pude registrar tu orden en este momento. No perdi tu orden ni tus datos. "
            "Por favor intenta confirmar de nuevo en unos segundos."
        )

    @classmethod
    def cancelled(cls) -> str:
        return (
            "Muchas gracias por elegirnos. Cancele la orden actual y vamos a estar pendientes "
            "por si quieres ordenar de nuevo. Aqui estoy para atenderte con mucho gusto."
        )

    @classmethod
    def natural_language_fallback(cls) -> str:
        return (
            "Puedes escribirme tu orden en texto normal. Por ejemplo: "
            "un pollo asado con una Coca-Cola 1.5, medio broaster o dos papas francesas.\n\n"
            "Si quieres ver el menu, escribe menu o quiero ver el menu. "
            "Tambien puedes preguntarme por horarios, bebidas, adicionales o domicilios."
        )

    @classmethod
    def unavailable_product_answer(cls) -> str:
        return (
            "Gracias por preguntar. Por ahora no cuento con informacion de ese producto "
            "en el catalogo del asadero. Puedo ayudarte con pollo asado, broaster, bebidas, "
            "adicionales, especiales y domicilios.\n\n"
            "Selecciona menu para ver las opciones o dime otro producto del asadero."
        )

    @classmethod
    def product_list_answer(cls, title: str, products: list[Product]) -> str:
        friendly_title = cls.CATEGORY_TITLES.get(title, title.replace("_", " ").title())
        if not products:
            return f"No tengo productos disponibles en {friendly_title} por ahora."
        lines = [friendly_title, ""]
        for product in products:
            lines.append(f"- {product.name.value}: ${product.price.amount}")
        lines.append("")
        lines.append("Si quieres ordenar alguno, puedes escribirlo o seleccionar menu.")
        return "\n".join(lines)

    @classmethod
    def product_price_answer(cls, product: Product) -> str:
        return f"{product.name.value} vale ${product.price.amount}."

    @classmethod
    def product_contents_answer(
        cls,
        product: Product | None,
        soup_available: bool = True,
        piece_question: bool = False,
    ) -> str:
        if product is None:
            return (
                "Claro. Dime de que producto quieres saber que trae: pollo asado, "
                "pollo broaster, adicionales o especiales."
            )
        if piece_question:
            pieces = cls._chicken_piece_count(product.code.value)
            if pieces:
                return (
                    f"Si claro. {product.name.value} trae {pieces} presas. "
                    "Tomamos el pollo entero como 8 presas: 2 pechugas, 2 alas, 2 perniles y 2 muslos. "
                    "Puede variar un poco segun el corte del asadero."
                )
        normalized_name = product.name.value.lower()
        if "broast" in normalized_name:
            soup_text = cls._included_soup_text(product.code.value, soup_available)
            return (
                f"Si claro. {product.name.value} vale ${product.price.amount} y viene con papa francesa, "
                f"tartara, miel y salsa de tomate. {soup_text}"
            )
        if "asado" in normalized_name:
            soup_text = cls._included_soup_text(product.code.value, soup_available)
            return (
                f"Si claro. {product.name.value} vale ${product.price.amount} y viene con papa, "
                f"yuca cocida y ají. {soup_text}"
            )
        return (
            f"{product.name.value} esta disponible en el menu. "
            "Si quieres, puedes ordenarlo escribiendo el nombre del producto."
        )

    @classmethod
    def _included_soup_text(cls, product_code: str, soup_available: bool) -> str:
        if not soup_available:
            return (
                "En este momento no contamos con sopas porque ya se agotaron, "
                "pero con gusto podemos seguir con tu orden sin sopa."
            )
        if product_code in {"ASADO_ENTERO", "BROASTER_ENTERO", "ASADO_34", "BROASTER_34"}:
            return "Mientras haya sopa disponible, esta presentacion incluye 2 sopas sin costo."
        if product_code in {"ASADO_MEDIO", "BROASTER_MEDIO", "ASADO_CUARTO", "BROASTER_CUARTO"}:
            return "Mientras haya sopa disponible, esta presentacion incluye 1 sopa sin costo."
        return "La sopa depende de la presentacion del pollo."

    @classmethod
    def _chicken_piece_count(cls, product_code: str) -> int | None:
        return {
            "ASADO_ENTERO": 8,
            "BROASTER_ENTERO": 8,
            "ASADO_34": 6,
            "BROASTER_34": 6,
            "ASADO_MEDIO": 4,
            "BROASTER_MEDIO": 4,
            "ASADO_CUARTO": 2,
            "BROASTER_CUARTO": 2,
        }.get(product_code)

    @classmethod
    def soup_unavailable_prompt(cls) -> str:
        return "\n\n".join(
            [
                "En este momento no contamos con sopas debido a que ya se agotaron.",
                "Podemos seguir con tu orden sin sopa o, si prefieres, la cancelamos sin problema.",
                "¿Quieres seguir con tu orden o prefieres cancelarla?",
            ]
        )

    @classmethod
    def generic_soup_inclusion_answer(cls) -> str:
        return (
            "Si, mientras haya sopa disponible el pollo incluye sopa segun la presentacion: "
            "1 pollo entero o 3/4 incluyen 2 sopas sin costo; medio pollo o 1/4 incluyen 1 sopa sin costo."
        )

    @classmethod
    def continue_without_soup_menu(cls) -> str:
        return "\n\n".join(
            [
                "Listo, seguimos con tu orden sin sopa.",
                "¿Deseas ordenar algo mas del menu?",
                cls.product_categories(),
            ]
        )

    @classmethod
    def product_combination_answer(cls) -> str:
        return (
            "Si, puedes ordenar medio asado y medio broaster en la misma orden. "
            "Te los añado como productos separados: 1/2 Asado y 1/2 Broasted.\n\n"
            "¿Deseas ordenarlos ahora o prefieres seguir viendo el menu?"
        )

    @classmethod
    def delivery_price_answer(cls, neighborhood: str, price_cop: int) -> str:
        return f"El domicilio para {neighborhood} cuesta ${price_cop}."

    @classmethod
    def service_available_answer(cls) -> str:
        return "\n\n".join(
            [
                "Muy buenas tardes, si claro, contamos con servicio a domicilio y estamos atendiendo.",
                "Dime como te puedo ayudar. Puedes escribirme tu orden completa o seleccionar menu para ver la imagen.",
            ]
        )

    @classmethod
    def order_status_answer(cls) -> str:
        return (
            "🍗 Estamos haciendo lo posible para despachar tu orden lo mas pronto posible. "
            "El tiempo aproximado es de 40 minutos o menos.\n\n"
            "Gracias por tu paciencia 🙌"
        )

    @classmethod
    def refund_followup_answer(cls) -> str:
        return (
            "Entiendo. Para devoluciones o ajustes de pago, un administrador revisa la orden "
            "y te confirma por este mismo chat. Por favor dejanos tu numero o cuenta si aun no la enviaste."
        )

    @classmethod
    def complaint_answer(cls) -> str:
        return (
            "Entiendo. Un administrador revisa tu caso y te responde por este mismo chat. "
            "Si ya tienes una orden en curso, por favor dejanos nombre, telefono o direccion para ubicarla rapido."
        )

    @classmethod
    def business_unknown_answer(cls) -> str:
        return (
            "Gracias por escribirme. No cuento con informacion sobre eso. "
            "Puedo ayudarte con el menu, precios, domicilios o pedidos del asadero."
        )

    @classmethod
    def schedules(cls) -> str:
        return "\n".join(
            [
                "🕒 Horario de atencion",
                "",
                "Lunes a domingo",
                "10:00 a.m. a 4:00 p.m.",
                "",
                "0. ⬅️ Volver al inicio",
            ]
        )

    @classmethod
    def outside_business_hours(cls) -> str:
        return "\n".join(
            [
                "Gracias por escribirnos.",
                "En este momento estamos fuera del horario de atencion.",
                "",
                "Nuestro horario es de lunes a domingo de 10:00 a.m. a 4:00 p.m.",
                "Para poder atender bien tu orden, por favor escribenos dentro de ese horario.",
            ]
        )

    @classmethod
    def start_delivery_order(cls) -> str:
        return "\n\n".join(
            [
                "Claro, te colaboro con un domicilio.",
                "Puedes escribirme tu orden completa o seleccionar menu para ver la imagen.",
            ]
        )

    @classmethod
    def audio_not_supported(cls) -> str:
        return (
            "Gracias por el audio. Por ahora no puedo procesar notas de voz. "
            "Para atenderte mejor, por favor escribeme tu orden o usa las opciones del menu."
        )
