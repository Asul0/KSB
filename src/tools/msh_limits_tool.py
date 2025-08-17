# src/tools/msh_limits_tool.py
import asyncio
from parser.msx_limit import get_subsidy_limits

# Здесь можно реализовать кэширование, чтобы не парсить PDF каждый раз
_cached_limits = None

async def get_msh_limits_data() -> dict | None:
    """
    Получает (возможно, из кэша) полные данные о лимитах МСХ.
    """
    global _cached_limits
    if _cached_limits:
        return _cached_limits
    
    limits = await asyncio.to_thread(get_subsidy_limits)
    if limits:
        _cached_limits = limits
    return limits