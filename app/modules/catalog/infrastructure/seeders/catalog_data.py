"""Canonical seed data for products and aliases. Prices here must match spec.md exactly."""

from __future__ import annotations

from dataclasses import dataclass, field

from app.modules.catalog.domain.enums import ProductCategory, ProductRestriction
from app.modules.catalog.domain.product_alias import normalize_alias


@dataclass(frozen=True)
class ProductSeed:
    code: str
    name: str
    category: ProductCategory
    price_cop: int
    restricted_to: ProductRestriction = ProductRestriction.NONE
    requires_age_verification: bool = False
    is_active: bool = True
    is_available: bool = True


@dataclass(frozen=True)
class ProductAliasSeed:
    product_code: str
    aliases: tuple[str, ...] = field(default_factory=tuple)


def expanded_aliases(aliases: tuple[str, ...]) -> tuple[str, ...]:
    expanded: list[str] = []
    seen: set[str] = set()
    for alias in aliases:
        for candidate in (alias, _pluralize_alias(alias)):
            normalized = normalize_alias(candidate)
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            expanded.append(candidate)
    return tuple(expanded)


def _pluralize_alias(alias: str) -> str:
    words = alias.split()
    if not words:
        return alias
    return " ".join(_pluralize_word(word) for word in words)


def _pluralize_word(word: str) -> str:
    clean = word.strip()
    if not clean or any(char.isdigit() for char in clean) or "/" in clean or "." in clean:
        return word
    if normalize_alias(clean) in {"de", "del", "con", "y", "o", "para", "en"}:
        return word
    if clean.endswith("s"):
        return word
    if clean.endswith("z"):
        return clean[:-1] + "ces"
    return clean + "s"


PRODUCT_SEEDS: tuple[ProductSeed, ...] = (
    ProductSeed("ASADO_ENTERO", "1 Asado Entero", ProductCategory.POLLO_ASADO, 44500),
    ProductSeed("ASADO_34", "3/4 Asado", ProductCategory.POLLO_ASADO, 34000),
    ProductSeed("ASADO_MEDIO", "1/2 Asado", ProductCategory.POLLO_ASADO, 22300),
    ProductSeed("ASADO_CUARTO", "1/4 Asado", ProductCategory.POLLO_ASADO, 11800),
    ProductSeed("BROASTER_ENTERO", "Broasted Entero", ProductCategory.POLLO_BROASTER, 51000),
    ProductSeed("BROASTER_34", "3/4 Broasted", ProductCategory.POLLO_BROASTER, 38600),
    ProductSeed("BROASTER_MEDIO", "1/2 Broasted", ProductCategory.POLLO_BROASTER, 25500),
    ProductSeed("BROASTER_CUARTO", "1/4 Broasted", ProductCategory.POLLO_BROASTER, 13500),
    ProductSeed("LITRO_MEDIO", "Litro y Medio", ProductCategory.BEBIDAS, 8500, is_active=False),
    ProductSeed("COCA_COLA_15", "Coca-Cola 1.5 L", ProductCategory.BEBIDAS, 8500),
    ProductSeed("QUATRO_15", "Quatro 1.5 L", ProductCategory.BEBIDAS, 8500),
    ProductSeed("GASEOSA_25", "Gaseosa 2.5 L", ProductCategory.BEBIDAS, 8500),
    ProductSeed("PERSONAL_400", "Coca-Cola personal 400 ml", ProductCategory.BEBIDAS, 3500),
    ProductSeed("AGUA_BOTELLA", "Agua botella", ProductCategory.BEBIDAS, 2600),
    ProductSeed("JUGO_HIT_PERSONAL", "Jugos Hit personal", ProductCategory.BEBIDAS, 3000),
    ProductSeed("JUGO_HIT_LITRO", "Jugo Hit Litro", ProductCategory.BEBIDAS, 6000),
    ProductSeed(
        "CLUB_COLOMBIA",
        "Club Colombia",
        ProductCategory.BEBIDAS_ALCOHOLICAS,
        4400,
        requires_age_verification=True,
    ),
    ProductSeed(
        "PILSEN_BOTELLA",
        "Pilsen Botella",
        ProductCategory.BEBIDAS_ALCOHOLICAS,
        4000,
        requires_age_verification=True,
    ),
    ProductSeed(
        "CERVEZA_LATA",
        "Cerveza Lata",
        ProductCategory.BEBIDAS_ALCOHOLICAS,
        4400,
        requires_age_verification=True,
    ),
    ProductSeed(
        "CERVEZA_MILLER_LATA",
        "Cerveza Miller Lata",
        ProductCategory.BEBIDAS_ALCOHOLICAS,
        4400,
        requires_age_verification=True,
    ),
    ProductSeed(
        "LASAGNA_MIXTA",
        "Lasagna Mixta",
        ProductCategory.ESPECIALES,
        20000,
        restricted_to=ProductRestriction.WEEKEND_OR_HOLIDAY,
    ),
    ProductSeed(
        "MADURO_QUESO",
        "Maduro con Queso",
        ProductCategory.ESPECIALES,
        9500,
        restricted_to=ProductRestriction.WEEKEND_OR_HOLIDAY,
    ),
    ProductSeed("PAPA_FRANCESA", "Papa Francesa", ProductCategory.ADICIONALES, 8200),
    ProductSeed("PAPA_SALADA", "Papa o yuca salada", ProductCategory.ADICIONALES, 5000),
    ProductSeed("YUCA_FRITA", "Yuca frita", ProductCategory.ADICIONALES, 5000),
    ProductSeed("ADICIONAL_SALSAS", "Adicional de Salsas", ProductCategory.ADICIONALES, 900),
    ProductSeed("SOPA_ADICIONAL", "Sopa Adicional", ProductCategory.ADICIONALES, 3500),
    ProductSeed("ICOPOR_SOPA", "Icopor Sopa", ProductCategory.ADICIONALES, 350),
    ProductSeed("DOMICILIO_BASE", "Domicilio", ProductCategory.DOMICILIOS, 1000),
    ProductSeed("ALOHA_VASO", "Aloha Vaso", ProductCategory.HELADOS, 4500),
    ProductSeed("BOCATO_CONO", "Bocato Cono", ProductCategory.HELADOS, 5700),
    ProductSeed("ARTESANAL", "Artesanal", ProductCategory.HELADOS, 3500),
    ProductSeed("PLATILLO", "Platillo", ProductCategory.HELADOS, 3500),
    ProductSeed("PALETA_DRACULA", "Paleta Dracula", ProductCategory.HELADOS, 5500),
    ProductSeed("CHOCOCONO", "Chococono", ProductCategory.HELADOS, 3500),
    ProductSeed("ALOHA_LIMON", "Aloha Limon", ProductCategory.HELADOS, 2000),
    ProductSeed("PALETA_JET", "Paleta Jet", ProductCategory.HELADOS, 5000),
    ProductSeed("CASERO", "Casero", ProductCategory.HELADOS, 2500),
    ProductSeed("POLET", "Polet", ProductCategory.HELADOS, 7000),
    ProductSeed("MINI_POLET", "Mini Polet", ProductCategory.HELADOS, 6000),
    ProductSeed("PLATILLO_JUMBO", "Platillo Jumbo", ProductCategory.HELADOS, 4000),
)


PRODUCT_ALIAS_SEEDS: tuple[ProductAliasSeed, ...] = (
    ProductAliasSeed(
        "ASADO_ENTERO",
        ("asado entero", "pollo asado entero", "entero asado", "1 asado entero"),
    ),
    ProductAliasSeed("ASADO_MEDIO", ("medio pollo", "media", "medio asado", "1/2 asado")),
    ProductAliasSeed("ASADO_CUARTO", ("cuarto asado", "1/4 asado", "cuarto pollo")),
    ProductAliasSeed(
        "BROASTER_ENTERO",
        ("broaster", "broasted", "broster", "pollo broaster", "broasted entero"),
    ),
    ProductAliasSeed("BROASTER_MEDIO", ("medio broaster", "medio brosted", "medio broster")),
    ProductAliasSeed("BROASTER_CUARTO", ("cuarto broaster", "cuarto broster")),
    ProductAliasSeed("COCA_COLA_15", ("coca cola 1.5", "coca-cola 1.5", "cocacola 1.5", "coca 1.5", "coca litro y medio")),
    ProductAliasSeed("QUATRO_15", ("quatro 1.5", "quatro litro y medio", "cuatro 1.5", "cuatro litro y medio")),
    ProductAliasSeed(
        "GASEOSA_25",
        (
            "gaseosa 2.5",
            "gaseosa dos litros y medio",
            "gaseosa kola",
            "gaseosa de kola",
            "kola 2.5",
            "gaseosa pepsi",
            "pepsi 2.5",
            "gaseosa pina",
            "gaseosa piña",
            "pina 2.5",
            "piña 2.5",
            "gaseosa colombiana",
            "colombiana 2.5",
        ),
    ),
    ProductAliasSeed(
        "LASAGNA_MIXTA",
        (
            "lasana",
            "lasagna",
            "lasaña",
            "lasagna mixta",
            "lasagna mista",
            "lasaña mixta",
            "lasaña mista",
            "lasana mixta",
            "lasana mista",
        ),
    ),
    ProductAliasSeed("MADURO_QUESO", ("maduro", "maduro con queso", "platano maduro")),
    ProductAliasSeed(
        "PAPA_FRANCESA",
        (
            "papa",
            "papa francesa",
            "papas francesas",
            "papa frita",
            "papas fritas",
            "fritas",
            "porcion de francesa",
            "porcion de francesas",
            "adicional de papas",
            "adicional de papas fritas",
        ),
    ),
    ProductAliasSeed(
        "PAPA_SALADA",
        ("papa salada", "papas saladas", "papa cocida", "yuca salada", "papa o yuca salada"),
    ),
    ProductAliasSeed("YUCA_FRITA", ("yuca frita", "yucas fritas", "adicional de yuca frita")),
    ProductAliasSeed(
        "ADICIONAL_SALSAS",
        ("adicional de salsas", "adicional de salsa", "extra salsas", "extra salsa", "salsa adicional"),
    ),
    ProductAliasSeed("SOPA_ADICIONAL", ("sopa", "sopita", "sopa adicional")),
    ProductAliasSeed(
        "ICOPOR_SOPA",
        (
            "icopor sopa",
            "icopor para sopa",
            "vaso sopa",
            "sopa con icopor",
            "sopa en icopor",
            "sopita con icopor",
            "sopita en icopor",
        ),
    ),
    ProductAliasSeed(
        "AGUA_BOTELLA",
        ("agua", "agua botella", "botella de agua", "agua con gas", "agua sin gas", "agua saborizada"),
    ),
    ProductAliasSeed(
        "JUGO_HIT_PERSONAL",
        (
            "jugo hit personal",
            "hit personal",
            "jugo tropical",
            "hit tropical",
            "hit de tropical",
            "jugo mango",
            "hit mango",
            "hit de mango",
        ),
    ),
    ProductAliasSeed(
        "JUGO_HIT_LITRO",
        ("jugo hit litro", "hit litro", "jugo hit litro tetra", "hit litro tetra"),
    ),
    ProductAliasSeed("CLUB_COLOMBIA", ("club colombia", "club")),
    ProductAliasSeed("PILSEN_BOTELLA", ("pilsen", "pilsen botella")),
    ProductAliasSeed("CERVEZA_LATA", ("cerveza lata", "cerveza en lata", "lata de cerveza")),
    ProductAliasSeed("CERVEZA_MILLER_LATA", ("miller", "miller lata", "cerveza miller")),
    ProductAliasSeed("ALOHA_VASO", ("aloha vaso", "vaso aloha")),
    ProductAliasSeed("BOCATO_CONO", ("bocato", "bocato cono", "cono bocato")),
    ProductAliasSeed("ARTESANAL", ("artesanal", "helado artesanal")),
    ProductAliasSeed("PLATILLO", ("platillo",)),
    ProductAliasSeed("PLATILLO_JUMBO", ("platillo jumbo",)),
    ProductAliasSeed("PALETA_DRACULA", ("paleta dracula", "dracula")),
    ProductAliasSeed("CHOCOCONO", ("chococono", "choco cono")),
    ProductAliasSeed("ALOHA_LIMON", ("aloha limon", "aloha limón")),
    ProductAliasSeed("PALETA_JET", ("paleta jet", "jet")),
    ProductAliasSeed("CASERO", ("casero", "helado casero")),
    ProductAliasSeed("POLET", ("polet",)),
    ProductAliasSeed("MINI_POLET", ("mini polet",)),
)


EXPECTED_PRICE_BY_CODE: dict[str, int] = {
    seed.code: seed.price_cop for seed in PRODUCT_SEEDS
}
