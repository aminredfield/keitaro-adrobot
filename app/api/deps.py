"""Зависимости, которые FastAPI подставляет в обработчики."""

import threading
from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends, Path
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.db import get_session
from app.keitaro import KeitaroClient, get_keitaro
from app.schemas import MAX_ID

SessionDep = Annotated[Session, Depends(get_session)]
KeitaroDep = Annotated[KeitaroClient, Depends(get_keitaro)]
SettingsDep = Annotated[Settings, Depends(get_settings)]

# id в Keitaro — положительные числа, которые помещаются в обычный INTEGER базы
KeitaroId = Annotated[int, Path(gt=0, le=MAX_ID)]

_write_lock = threading.Lock()


def write_lock() -> Iterator[None]:
    """Пускает изменяющие запросы по одному.

    Каждый такой запрос читает поток, пересчитывает доли и пишет обратно. Два
    одновременных запроса посчитали бы доли по устаревшим данным. Приложение
    работает одним процессом, поэтому обычного замка достаточно.
    """
    with _write_lock:
        yield


WriteLock = Depends(write_lock)
