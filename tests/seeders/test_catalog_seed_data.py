"""Automated test module. It documents expected behavior and protects production bot flows from regressions."""

from __future__ import annotations

from app.modules.catalog.domain.enums import ProductRestriction
from app.modules.catalog.domain.product_alias import normalize_alias
from app.modules.catalog.infrastructure.seeders.catalog_data import (
    EXPECTED_PRICE_BY_CODE,
    PRODUCT_ALIAS_SEEDS,
    PRODUCT_SEEDS,
)
from app.modules.delivery.infrastructure.seeders.delivery_zone_data import (
    EXPECTED_DELIVERY_PRICE_BY_CODE,
)


def test_seed_prices_are_exact() -> None:
    assert EXPECTED_PRICE_BY_CODE == {
        "ASADO_ENTERO": 44500,
        "ASADO_34": 34000,
        "ASADO_MEDIO": 22300,
        "ASADO_CUARTO": 11800,
        "BROASTER_ENTERO": 51000,
        "BROASTER_34": 38600,
        "BROASTER_MEDIO": 25500,
        "BROASTER_CUARTO": 13500,
        "LITRO_MEDIO": 8500,
        "COCA_COLA_15": 8500,
        "QUATRO_15": 8500,
        "GASEOSA_25": 8500,
        "PERSONAL_400": 3500,
        "AGUA_BOTELLA": 2600,
        "JUGO_HIT_PERSONAL": 3000,
        "JUGO_HIT_LITRO": 6000,
        "CLUB_COLOMBIA": 4400,
        "PILSEN_BOTELLA": 4000,
        "CERVEZA_LATA": 4400,
        "CERVEZA_MILLER_LATA": 4400,
        "LASAGNA_MIXTA": 20000,
        "MADURO_QUESO": 9500,
        "PAPA_FRANCESA": 8200,
        "PAPA_SALADA": 5000,
        "YUCA_FRITA": 5000,
        "BOTELLA_VIDRIO": 200,
        "ICOPOR": 900,
        "ADICIONAL_SALSAS": 900,
        "SOPA_ADICIONAL": 3500,
        "ICOPOR_SOPA": 350,
        "DOMICILIO_BASE": 1000,
        "ALOHA_VASO": 4500,
        "BOCATO_CONO": 5700,
        "ARTESANAL": 3500,
        "PLATILLO": 3500,
        "PALETA_DRACULA": 5500,
        "CHOCOCONO": 3500,
        "ALOHA_LIMON": 2000,
        "PALETA_JET": 5000,
        "CASERO": 2500,
        "POLET": 7000,
        "MINI_POLET": 6000,
        "PLATILLO_JUMBO": 4000,
    }
    assert all(isinstance(price, int) for price in EXPECTED_PRICE_BY_CODE.values())


def test_delivery_zones_are_exact() -> None:
    assert EXPECTED_DELIVERY_PRICE_BY_CODE == {
        "DOMICILIO_LAGOS_2_SANTA_COLOMA": 2000,
        "DOMICILIO_BUCARICA_BELLAVISTA": 4000,
        "DOMICILIO_EL_MANANTIAL": 4000,
        "DOMICILIO_CANAVERAL_FLORIDA": 6000,
        "DOMICILIO_PROVENZA_DIAMANTE": 7000,
        "DOMICILIO_CACIQUE": 8000,
        "DOMICILIO_SAN_ANDRESITO": 10000,
        "DOMICILIO_CIUDADELA": 11000,
        "DOMICILIO_CABECERA": 12000,
        "HOSPITAL_INTERNACIONAL": 10000,
        "DOMICILIO_ADICIONAL": 500,
    }
    assert all(isinstance(price, int) for price in EXPECTED_DELIVERY_PRICE_BY_CODE.values())


def test_restricted_products() -> None:
    products = {seed.code: seed for seed in PRODUCT_SEEDS}

    assert products["LASAGNA_MIXTA"].restricted_to == ProductRestriction.WEEKEND_OR_HOLIDAY
    assert products["MADURO_QUESO"].restricted_to == ProductRestriction.WEEKEND_OR_HOLIDAY


def test_alcohol_products_require_age_verification() -> None:
    products = {seed.code: seed for seed in PRODUCT_SEEDS}

    for code in ("CLUB_COLOMBIA", "PILSEN_BOTELLA", "CERVEZA_LATA", "CERVEZA_MILLER_LATA"):
        assert products[code].requires_age_verification


def test_aliases_normalized() -> None:
    normalized_aliases = {
        normalize_alias(alias)
        for seed in PRODUCT_ALIAS_SEEDS
        for alias in seed.aliases
    }

    assert "broaster" in normalized_aliases
    assert "broasted" in normalized_aliases
    assert "broster" in normalized_aliases
    assert "pollo broaster" in normalized_aliases
    assert "medio pollo" in normalized_aliases
    assert "media" in normalized_aliases
    assert "coca cola 1.5" in normalized_aliases
    assert "gaseosa 2.5" in normalized_aliases
    assert "jugo hit personal" in normalized_aliases
    assert "quatro 1.5" in normalized_aliases
    assert "lasana" in normalized_aliases
    assert "lasagna" in normalized_aliases
    assert "maduro" in normalized_aliases
    assert "papa" in normalized_aliases
    assert "papa francesa" in normalized_aliases
    assert "yuca frita" in normalized_aliases
    assert normalize_alias("Cañaveral") == "canaveral"
