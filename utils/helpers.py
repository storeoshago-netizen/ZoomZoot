from core.logging import logger


def format_affiliate_link(base_url: str, destination: str | None) -> str:
    logger.info(f"Formatting affiliate link for destination: {destination}")
    return f"{base_url}?destination={destination or 'any'}"
