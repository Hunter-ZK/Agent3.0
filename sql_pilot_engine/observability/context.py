from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from collections.abc import Iterable


_current_run_id: ContextVar[str] = ContextVar(
    "agent3_run_id",
    default="-",
)


def get_run_id() -> str:

    return _current_run_id.get()


@contextmanager
def bind_run_id(
    run_id: str,
) -> Iterable[None]:
    """在当前执行上下文中绑定 run_id。

    离开 with 作用域后自动恢复之前的值。
    """
    token = _current_run_id.set(run_id)

    try:
        yield
    finally:
        _current_run_id.reset(token)

        
    