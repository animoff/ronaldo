"""Общие границы входных значений корзины и бизнес-сервиса."""


def valid_sku_key(value):
    """Ключ JSON-сессии — каноническая строка положительного BigAutoField ID.

    isdigit() без isascii() принимает, например, «²», который int() не читает.
    Ограничение длины проверяем до int(), чтобы исключить чрезмерные числа.
    """
    return (
        isinstance(value, str) and 1 <= len(value) <= 19
        and value.isascii() and value.isdecimal() and not value.startswith("0")
        and int(value) <= 2**63 - 1
    )
