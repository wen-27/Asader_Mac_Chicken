"""Centralized Telegram message copy for the conversation graph.

User-facing text should live here instead of inside nodes. That keeps the graph
focused on state transitions and makes UX/copy changes safer.
"""

from __future__ import annotations

from app.modules.catalog.domain.product import Product
from app.modules.conversations.graph.state import CartLineState, ConversationGraphState


class BotMessageFactory:
    BUSINESS_NAME = "ASADERO MC CHICKEN EXPRESS"
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
                f"👋 Hola, bienvenido a {cls.BUSINESS_NAME}.",
                "¿Que quieres hacer hoy?",
                "\n".join(
                    [
                        "1. Pedir por menu 📋",
                        "2. Pedir escribiendo ✍️",
                        "3. Ver carrito 🧾",
                        "4. Horarios 🕒",
                    ]
                ),
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
                "6. ✅ Finalizar pedido",
                "0. ⬅️ Volver al inicio",
            ]
        )

    @classmethod
    def product_menu(cls, title: str, products: list[Product]) -> str:
        friendly_title = cls.CATEGORY_TITLES.get(title, title.replace("_", " ").title())
        if not products:
            return f"{friendly_title}\n\nPor ahora no hay productos disponibles en esta categoria."
        lines = [friendly_title, ""]
        for index, product in enumerate(products, start=1):
            lines.append(f"{index}. {product.name.value} - ${product.price.amount}")
        lines.append("")
        lines.append("Responde con el numero del producto que quieres agregar.")
        lines.append("0. ⬅️ Volver a categorias")
        return "\n".join(lines)

    @classmethod
    def ask_quantity(cls, product_name: str, price_cop: int) -> str:
        return "\n\n".join(
            [
                f"🛒 {product_name}",
                f"Precio unitario: ${price_cop}",
                "¿Cuantas unidades deseas agregar?",
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
    def product_unavailable(cls) -> str:
        return (
            "⚠️ Ese producto solo esta disponible fines de semana o festivos. "
            "Puedes elegir otra opcion del menu."
        )

    @classmethod
    def product_not_found(cls) -> str:
        return "No encontre ese producto. Escribe menu para ver las opciones disponibles."

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
                "✅ Agregado al carrito.",
                f"{line.quantity} x {line.product_name} = ${line.subtotal_cop}",
                f"🧾 Total acumulado: ${total_cop}",
                "¿Que quieres hacer ahora?",
                "\n".join(
                    [
                        "1. Agregar mas productos ➕",
                        "2. Ver carrito 🛒",
                        "3. Finalizar pedido ✅",
                        "4. Vaciar carrito 🗑️",
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
                "✅ Agregado al carrito.",
                added_lines,
                f"🧾 Total acumulado: ${total_cop}",
                "¿Que quieres hacer ahora?",
                "\n".join(
                    [
                        "1. Agregar mas productos ➕",
                        "2. Ver carrito 🛒",
                        "3. Finalizar pedido ✅",
                        "4. Vaciar carrito 🗑️",
                        "0. Volver a categorias ⬅️",
                    ]
                ),
            ]
        )

    @classmethod
    def cart(cls, cart: list[CartLineState], total_cop: int) -> str:
        if not cart:
            return "🛒 Tu carrito esta vacio. Escribe menu para ver opciones."
        lines = ["🛒 Tu carrito:", ""]
        for line in cart:
            lines.append(f"- {line.quantity} x {line.product_name}: ${line.subtotal_cop}")
        lines.append("")
        lines.append(f"Total: ${total_cop}")
        lines.append("")
        lines.append("1. Agregar mas productos ➕")
        lines.append("2. Ver carrito 🛒")
        lines.append("3. Finalizar pedido ✅")
        lines.append("4. Vaciar carrito 🗑️")
        lines.append("0. Volver al inicio ⬅️")
        return "\n".join(lines)

    @classmethod
    def clear_cart(cls) -> str:
        return "🗑️ Listo, vacie tu carrito. Puedes seguir comprando cuando quieras."

    @classmethod
    def remove_last_item(cls, removed_name: str | None) -> str:
        if removed_name is None:
            return "🛒 Tu carrito esta vacio. No hay productos para eliminar."
        return f"Listo, quite {removed_name} del carrito."

    @classmethod
    def checkout_summary(cls, state: ConversationGraphState) -> str:
        if not state.cart:
            return "🛒 Tu carrito esta vacio. Primero agrega productos al pedido."
        return "\n\n".join(
            [
                "🧾 Resumen de tu pedido:",
                cls.cart(state.cart, state.subtotal_cop),
                "¿Deseas confirmar el pedido? Responde SI para confirmar o NO para cancelar.",
            ]
        )

    @classmethod
    def ask_customer_data(cls) -> str:
        return "\n\n".join(
            [
                "📦 Para finalizar tu pedido necesito los datos de envio:",
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
                "Puedes enviarlos en un solo mensaje, en lineas separadas o como te quede mas facil.",
                "0. ⬅️ Volver al carrito",
            ]
        )

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
        return "\n\n".join(
            [
                "✅ Datos recibidos. Revisa tu pedido:",
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
                "¿Confirmas tu pedido? Responde SI para confirmar o NO para cancelar.",
            ]
        )

    @classmethod
    def confirmed(cls) -> str:
        return "✅ Pedido confirmado. Gracias por tu compra."

    @classmethod
    def order_confirmation_failed(cls) -> str:
        return (
            "No pude registrar tu pedido en este momento. No perdi tu carrito ni tus datos. "
            "Por favor intenta confirmar de nuevo en unos segundos."
        )

    @classmethod
    def cancelled(cls) -> str:
        return "Listo, cancele el pedido actual. Cuando quieras empezamos de nuevo."

    @classmethod
    def natural_language_fallback(cls) -> str:
        return (
            "Puedes escribirme tu pedido en texto normal. Por ejemplo: "
            "un pollo asado con una Coca-Cola 1.5, medio broaster o dos papas francesas."
        )

    @classmethod
    def unavailable_product_answer(cls) -> str:
        return (
            "Gracias por preguntar. Por ahora no cuento con informacion de ese producto "
            "en el catalogo del asadero. Puedo ayudarte con pollo asado, broaster, bebidas, "
            "adicionales, especiales y domicilios.\n\n"
            "Escribe menu para ver las opciones o dime otro producto del asadero."
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
        lines.append("Si quieres pedir alguno, puedes escribirlo o responder con menu.")
        return "\n".join(lines)

    @classmethod
    def product_price_answer(cls, product: Product) -> str:
        return f"{product.name.value} vale ${product.price.amount}."

    @classmethod
    def delivery_price_answer(cls, neighborhood: str, price_cop: int) -> str:
        return f"El domicilio para {neighborhood} cuesta ${price_cop}."

    @classmethod
    def order_status_answer(cls) -> str:
        return (
            "🍗 Estamos haciendo lo posible para despachar tu pedido lo mas pronto posible. "
            "El tiempo aproximado es de 40 minutos o menos.\n\n"
            "Gracias por tu paciencia 🙌"
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
                "11:00 a.m. a 4:00 p.m.",
                "",
                "0. ⬅️ Volver al inicio",
            ]
        )
