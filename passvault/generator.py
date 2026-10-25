import secrets
import string

SYMBOLS = "!@#$%^&*()-_=+[]{};:,.?"


def generate_password(length: int = 20, symbols: bool = True) -> str:
    """Random password with at least one lowercase, uppercase, digit (and symbol)."""
    pools = [string.ascii_lowercase, string.ascii_uppercase, string.digits]
    if symbols:
        pools.append(SYMBOLS)
    if length < len(pools):
        raise ValueError(f"Độ dài tối thiểu là {len(pools)}")

    alphabet = "".join(pools)
    chars = [secrets.choice(pool) for pool in pools]
    chars += [secrets.choice(alphabet) for _ in range(length - len(chars))]
    secrets.SystemRandom().shuffle(chars)
    return "".join(chars)
