"""Generate reviewable urban delivery-zone data for the Bucaramanga metro area.

The bot already calculates distance-based delivery when a neighborhood is not
found in the manual table. This script only prepares urban neighborhood rows for
manual pricing; rural veredas and corregimientos are intentionally excluded.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from urllib.error import URLError
from urllib.request import Request, urlopen


OUTPUT_DIR = Path(__file__).resolve().parents[2] / "private" / "delivery_zones"
CSV_PATH = OUTPUT_DIR / "amb_urban_delivery_zones.csv"
SQL_PATH = OUTPUT_DIR / "amb_urban_delivery_zones.sql"
README_PATH = OUTPUT_DIR / "README.md"

BUCARAMANGA_BARRIOS_URL = (
    "https://vmarcgis01.bucaramanga.gov.co/waserver/rest/services/"
    "LIMITES_POLITICOS/Barrios/FeatureServer/0/query"
    "?where=1%3D1&outFields=*&returnGeometry=false&f=json"
)


@dataclass(frozen=True)
class ZoneCandidate:
    municipality: str
    neighborhood: str
    source: str
    source_quality: str


@dataclass(frozen=True)
class PricedZone:
    code: str
    municipality: str
    neighborhood: str
    normalized_neighborhood: str
    delivery_price_cop: int
    is_active: bool
    pricing_source: str
    review_required: bool
    data_source: str
    source_quality: str


MANUAL_PRICES: tuple[tuple[str, str, int], ...] = (
    ("DOMICILIO_LAGOS_2_SANTA_COLOMA", "Lagos 2 / Santa Coloma", 2000),
    ("DOMICILIO_BUCARICA_BELLAVISTA", "Bucarica / Bellavista", 4000),
    ("DOMICILIO_EL_MANANTIAL", "El Manantial", 4000),
    ("DOMICILIO_CANAVERAL_FLORIDA", "Cañaveral / Florida", 6000),
    ("DOMICILIO_PROVENZA_DIAMANTE", "Provenza / Diamante", 7000),
    ("DOMICILIO_CACIQUE", "Cacique", 8000),
    ("DOMICILIO_SAN_ANDRESITO", "San Andresito", 10000),
    ("DOMICILIO_CIUDADELA", "Ciudadela", 11000),
    ("DOMICILIO_CABECERA", "Cabecera", 12000),
    ("HOSPITAL_INTERNACIONAL", "Hospital Internacional", 10000),
)

MANUAL_PRICE_BY_ALIAS = {
    alias: price
    for _, neighborhood, price in MANUAL_PRICES
    for alias in [*neighborhood.split("/"), neighborhood]
}

BUCARAMANGA_FALLBACK = (
    "El Rosal",
    "Colorados",
    "Café Madrid",
    "Las Hamacas",
    "Altos del Kennedy",
    "Kennedy",
    "Balcones del Kennedy",
    "Las Olas",
    "Villa Rosa",
    "Omagá",
    "Minuto de Dios",
    "Tejar Norte",
    "Miramar",
    "Miradores del Kennedy",
    "El Pablón",
    "Los Angeles",
    "Villa Helena",
    "José María Córdoba",
    "Esperanza",
    "Lizcano",
    "Regadero Norte",
    "San Cristóbal",
    "La Juventud",
    "Transición",
    "La Independencia",
    "Villa Mercedes",
    "Bosque Norte",
    "Norte Bajo",
    "San Rafael",
    "El Cinal",
    "Chapinero",
    "Comuneros",
    "La Universidad",
    "Mutualidad",
    "Modelo",
    "San Francisco",
    "Alarcón",
    "Gaitán",
    "Granadas",
    "Nariño",
    "Girardot",
    "La Feria",
    "Nápoles",
    "Pío XII",
    "23 de Junio",
    "Santander",
    "Don Bosco",
    "12 de Octubre",
    "La Gloria",
    "Quinta Estrella",
    "Alfonso López",
    "La Joya",
    "Chorreras de Don Juan",
    "Campohermoso",
    "La Estrella",
    "Primero de Mayo",
    "La Concordia",
    "San Miguel",
    "Candiles",
    "Aeropuerto Gómez Niño",
    "Ricaurte",
    "La Ceiba",
    "La Salle",
    "La Victoria",
    "Ciudadela Real de Minas",
    "San Gerardo",
    "Antiguo Colombia",
    "Los Canelos",
    "Bucaramanga",
    "Cordoncillo",
    "Pablo VI",
    "20 de Julio",
    "África",
    "Juan XXIII",
    "Los Laureles",
    "Quebrada la Iglesia",
    "Antonia Santos Sur",
    "San Pedro Claver",
    "San Martín",
    "Nueva Granada",
    "La Pedregosa",
    "La Libertad",
    "Diamante I",
    "Villa Inés",
    "Asturias",
    "Las Casitas",
    "Diamante II",
    "San Luis",
    "Provenza",
    "El Cristal",
    "Fontana",
    "Granjas de Provenza",
    "Ciudad Venecia",
    "Villa Alicia",
    "El Rocío",
    "Toledo Plata",
    "Dangond",
    "Manuela Beltrán",
    "Igzabelar",
    "Santa María",
    "Los Robles",
    "Granjas de Julio Rincón",
    "Jardines de Coaviconsa",
    "El Candado",
    "Malpaso",
    "El Porvenir",
    "Las Delicias",
    "Cabecera del Llano",
    "Sotomayor",
    "Antiguo Campestre",
    "Bolarquí",
    "Mercedes",
    "Puerta del Sol",
    "Conucos",
    "El Jardín",
    "Pan de Azúcar",
    "Los Cedros",
    "Terrazas",
    "La Floresta",
    "Los Pinos",
    "San Alonso",
    "Galán",
    "La Aurora",
    "Las Américas",
    "El Prado",
    "Mejoras Públicas",
    "Antonia Santos",
    "Bolívar",
    "Álvarez",
    "Vegas de Morrorico",
    "El Diviso",
    "Morrorico",
    "Albania",
    "Miraflores",
    "Buenos Aires",
    "Limoncito",
    "Los Sauces",
    "Centro",
    "García Rovira",
    "Lagos del Cacique",
    "El Tejar",
    "San Expedito",
    "Mutis",
    "Balconcitos",
    "Monterredondo",
    "Héroes",
    "Estoraques",
    "Prados del Mutis",
)

FLORIDABLANCA_URBAN_SEED = (
    "Casco Antiguo",
    "Villabel",
    "Santa Ana",
    "Caldas",
    "El Reposo",
    "La Cumbre",
    "Primavera I",
    "Primavera II",
    "Bucarica",
    "Lagos I",
    "Lagos II",
    "Lagos III",
    "Lagos IV",
    "Lagos V",
    "Zapamanga I",
    "Zapamanga II",
    "Zapamanga III",
    "Zapamanga IV",
    "Zapamanga V",
    "Zapamanga VI",
    "Zapamanga VII",
    "Zapamanga VIII",
    "Los Alares",
    "La Trinidad",
    "Las Villas",
    "El Carmen",
    "Cañaveral",
    "Cañaveral Occidental",
    "Cañaveral Oriental",
    "El Bosque",
    "El Porvenir",
    "Palomitas",
    "Ciudad Valencia",
    "San Bernardo",
    "Altamira",
    "Los Andes",
    "Limoncito",
    "Jardín del Limoncito",
    "Las Rondas",
    "La Castellana",
    "Versalles",
    "La Paz",
    "Villas de San Francisco",
    "El Verde",
    "El Recreo",
    "Abadías",
    "Florida",
    "La Ronda",
    "Aranzoque",
    "Campestre",
    "Buenos Aires",
    "Caracolí",
    "Altos del Caracolí",
    "Andalucía",
    "Guayacanes",
    "Molinos",
    "Molinos Altos",
    "Molinos Bajos",
)

GIRON_URBAN_SEED = (
    "Altos de la Campiña",
    "Altos del Poblado",
    "Arenales Campestre",
    "Bellavista",
    "Campiña",
    "Carrizal Campestre",
    "Corivandi 1",
    "Corivandi 3",
    "El Consuelo",
    "El Gallineral",
    "Hacienda San Antonio",
    "Jardín de Arenales",
    "La Playa",
    "Las Marías",
    "Los Bambúes",
    "Meseta 3",
    "Meseta de Alcalá",
    "Mirador de Arenales",
    "Mirador de la Aldea",
    "Quintas del Llanito",
    "Rincón de Girón",
    "Rincón de Oro II",
    "Río Prado",
    "San Antonio Carrizal",
    "Santa Cruz",
    "Sector Frente a Cotragas",
    "Villa Campestre",
    "Villanpis",
    "Villas de Don Juan 2",
    "El Consuelo 3",
    "El Rincón Parte Alta",
)

PIEDECUESTA_URBAN_SEED = (
    "San Rafael",
    "San Cristóbal",
    "Cabecera",
    "Quinta Granada",
    "Pinares de Granada",
    "Paseo del Puente",
    "La Rioja",
    "San Telmo",
    "La Argentina",
    "San Francisco",
    "San Carlos",
    "La Castellana",
    "San Luis",
    "La Macarena",
    "Hoyo Grande",
    "Bariloche",
    "Chacarita",
    "Campo Verde",
    "La Colina",
    "La Candelaria",
    "El Refugio",
    "Paysandú",
    "Puerto Madero",
    "El Molino",
    "Divino Niño",
    "El Trapiche",
    "La Tachuela",
    "Hospital Internacional",
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="Print summary without writing files.")
    args = parser.parse_args()

    zones = build_zones()
    if args.dry_run:
        print(f"Generated {len(zones)} urban delivery-zone candidates.")
        print(f"Review-required rows: {sum(zone.review_required for zone in zones)}")
        print(f"Output CSV: {CSV_PATH}")
        print(f"Output SQL: {SQL_PATH}")
        return

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    write_csv(zones, CSV_PATH)
    write_sql(zones, SQL_PATH)
    write_readme(zones, README_PATH)
    print(f"Wrote {len(zones)} rows to {CSV_PATH}")
    print(f"Wrote SQL to {SQL_PATH}")
    print(f"Wrote notes to {README_PATH}")


def build_zones() -> list[PricedZone]:
    candidates = [
        *bucaramanga_candidates(),
        *static_candidates("Floridablanca", FLORIDABLANCA_URBAN_SEED, "AMB/Alcaldía Floridablanca"),
        *static_candidates("Girón", GIRON_URBAN_SEED, "Alcaldía de Girón"),
        *static_candidates("Piedecuesta", PIEDECUESTA_URBAN_SEED, "Alcaldía de Piedecuesta"),
    ]
    deduped: dict[str, ZoneCandidate] = {}
    for candidate in candidates:
        normalized = normalize_neighborhood(candidate.neighborhood)
        if not normalized or is_invalid_neighborhood(candidate.neighborhood):
            continue
        key = f"{normalize_neighborhood(candidate.municipality)}::{normalized}"
        deduped.setdefault(key, candidate)

    priced = [price_zone(candidate) for candidate in deduped.values()]
    return sorted(priced, key=lambda item: (item.municipality, item.normalized_neighborhood))


def bucaramanga_candidates() -> list[ZoneCandidate]:
    neighborhoods = fetch_bucaramanga_neighborhoods() or list(BUCARAMANGA_FALLBACK)
    source_quality = "official_arcgis" if neighborhoods and neighborhoods != list(BUCARAMANGA_FALLBACK) else "official_fallback"
    return [
        ZoneCandidate(
            municipality="Bucaramanga",
            neighborhood=neighborhood,
            source="Alcaldía de Bucaramanga",
            source_quality=source_quality,
        )
        for neighborhood in neighborhoods
    ]


def fetch_bucaramanga_neighborhoods() -> list[str]:
    request = Request(BUCARAMANGA_BARRIOS_URL, headers={"User-Agent": "asadero-delivery-zone-generator/1.0"})
    try:
        with urlopen(request, timeout=20) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (OSError, URLError, json.JSONDecodeError):
        return []

    neighborhoods = []
    for feature in payload.get("features", []):
        attrs = feature.get("attributes", {})
        name = attrs.get("NOMBRE_BAR") or attrs.get("NOMBRE")
        if isinstance(name, str):
            neighborhoods.append(clean_name(name))
    return sorted(set(filter(None, neighborhoods)), key=normalize_neighborhood)


def static_candidates(municipality: str, names: tuple[str, ...], source: str) -> list[ZoneCandidate]:
    return [
        ZoneCandidate(
            municipality=municipality,
            neighborhood=name,
            source=source,
            source_quality="official_seed_partial",
        )
        for name in names
    ]


def price_zone(candidate: ZoneCandidate) -> PricedZone:
    manual_price = manual_price_for(candidate.neighborhood)
    if manual_price is not None:
        price = manual_price
        pricing_source = "manual_existing"
        review_required = False
    else:
        price = suggested_price(candidate.municipality, candidate.neighborhood)
        pricing_source = "rule_suggested"
        review_required = True

    normalized = f"{normalize_neighborhood(candidate.neighborhood)} {normalize_neighborhood(candidate.municipality)}"
    return PricedZone(
        code=make_code(candidate.municipality, candidate.neighborhood),
        municipality=candidate.municipality,
        neighborhood=candidate.neighborhood,
        normalized_neighborhood=normalized,
        delivery_price_cop=price,
        is_active=True,
        pricing_source=pricing_source,
        review_required=review_required,
        data_source=candidate.source,
        source_quality=candidate.source_quality,
    )


def manual_price_for(neighborhood: str) -> int | None:
    normalized = normalize_neighborhood(neighborhood)
    for alias, price in MANUAL_PRICE_BY_ALIAS.items():
        alias_normalized = normalize_neighborhood(alias)
        if normalized == alias_normalized or alias_normalized in normalized or normalized in alias_normalized:
            return price
    return None


def suggested_price(municipality: str, neighborhood: str) -> int:
    normalized = normalize_neighborhood(neighborhood)
    rules: tuple[tuple[tuple[str, ...], int], ...] = (
        (("lagos", "santa coloma"), 2000),
        (("bucarica", "bellavista", "manantial"), 4000),
        (("canaveral", "canaveral", "florida", "zapamanga", "cumbre", "reposo"), 6000),
        (("villabel", "bosque", "altamira", "limoncito", "andes", "versalles"), 6000),
        (("provenza", "diamante"), 7000),
        (("cacique", "mutis", "ciudadela", "real de minas"), 10000),
        (("cabecera", "sotomayor", "bolarqui", "terrazas", "conucos"), 12000),
        (("pan de azucar", "floresta", "centro"), 12000),
        (("hospital internacional",), 10000),
    )
    for aliases, price in rules:
        if any(alias in normalized for alias in aliases):
            return price

    municipality_defaults = {
        "bucaramanga": 10000,
        "floridablanca": 6000,
        "giron": 12000,
        "piedecuesta": 14000,
    }
    return municipality_defaults.get(normalize_neighborhood(municipality), 10000)


def write_csv(zones: list[PricedZone], path: Path) -> None:
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(
            file,
            fieldnames=[
                "code",
                "municipality",
                "neighborhood",
                "normalized_neighborhood",
                "delivery_price_cop",
                "is_active",
                "pricing_source",
                "review_required",
                "data_source",
                "source_quality",
            ],
        )
        writer.writeheader()
        for zone in zones:
            writer.writerow(zone.__dict__)


def write_sql(zones: list[PricedZone], path: Path) -> None:
    values = ",\n".join(
        "    "
        + "("
        + ", ".join(
            [
                sql_quote(zone.code),
                sql_quote(f"{zone.neighborhood}, {zone.municipality}"),
                sql_quote(zone.normalized_neighborhood),
                str(zone.delivery_price_cop),
                "TRUE" if zone.is_active else "FALSE",
            ]
        )
        + ")"
        for zone in zones
    )
    path.write_text(
        "\n".join(
            [
                "-- Review bot/private/delivery_zones/amb_urban_delivery_zones.csv before applying.",
                "-- Urban zones only. Rural veredas/corregimientos stay out so the bot can price by distance.",
                "BEGIN;",
                "INSERT INTO bot.delivery_zones (",
                "    code,",
                "    neighborhood,",
                "    normalized_neighborhood,",
                "    delivery_price_cop,",
                "    is_active",
                ")",
                "VALUES",
                values,
                "ON CONFLICT (normalized_neighborhood)",
                "DO UPDATE SET",
                "    neighborhood = EXCLUDED.neighborhood,",
                "    delivery_price_cop = EXCLUDED.delivery_price_cop,",
                "    is_active = EXCLUDED.is_active;",
                "COMMIT;",
                "",
            ]
        ),
        encoding="utf-8",
    )


def write_readme(zones: list[PricedZone], path: Path) -> None:
    review_count = sum(zone.review_required for zone in zones)
    path.write_text(
        f"""# AMB urban delivery zones

Generated rows: {len(zones)}
Rows that require price review: {review_count}

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
""",
        encoding="utf-8",
    )


def clean_name(name: str) -> str:
    return re.sub(r"\s+", " ", name.strip(" \t\r\n.,;:-"))


def is_invalid_neighborhood(name: str) -> bool:
    cleaned = clean_name(name)
    if not cleaned:
        return True
    if cleaned.isdigit():
        return True
    return len(cleaned) < 3


def normalize_neighborhood(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value.lower())
    normalized = "".join(char for char in normalized if not unicodedata.combining(char))
    normalized = normalized.replace("ñ", "n")
    normalized = re.sub(r"[^a-z0-9]+", " ", normalized)
    return re.sub(r"\s+", " ", normalized).strip()


def make_code(municipality: str, neighborhood: str) -> str:
    base = f"DOMICILIO_{municipality}_{neighborhood}"
    slug = normalize_neighborhood(base).upper().replace(" ", "_")
    if len(slug) <= 100:
        return slug
    digest = hashlib.sha1(slug.encode("utf-8")).hexdigest()[:8].upper()
    return f"{slug[:91]}_{digest}"


def sql_quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


if __name__ == "__main__":
    main()
