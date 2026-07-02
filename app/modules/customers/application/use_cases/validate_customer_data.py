"""Customer-data validation use case for checkout-required fields and payment methods."""

from __future__ import annotations

from dataclasses import dataclass

from app.modules.customers.application.customer_data import CustomerData, missing_customer_fields


@dataclass(frozen=True)
class ValidateCustomerDataResult:
    is_valid: bool
    missing_fields: tuple[str, ...]


class ValidateCustomerData:
    def execute(self, data: CustomerData) -> ValidateCustomerDataResult:
        missing = missing_customer_fields(data)
        return ValidateCustomerDataResult(
            is_valid=not missing,
            missing_fields=tuple(missing),
        )

