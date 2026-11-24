# Учёт заказов сервисного центра

Курсовой проект по КПО. Веб-приложение на Python (FastAPI, SQLAlchemy 2, SQLite), интерфейс на HTML, CSS и JavaScript.

Автор: Масюк Алексей, ПО-16.

## Запуск

Нужен Python 3.11+ и [uv](https://docs.astral.sh/uv/).

```sh
uv sync
uv run python -m app.cli init-demo
uv run uvicorn app.main:app --port 8000
```

Приложение откроется на http://127.0.0.1:8000.

`init-demo` создаёт тестовые аккаунты и несколько заказов:

| Роль | Логин | Пароль |
| --- | --- | --- |
| Администратор | admin | AdminDemo2026! |
| Оператор | operator | OperatorDemo2026! |

Создать администратора для пустой базы: `uv run python -m app.cli create-admin`.

Без uv:

```sh
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m app.cli init-demo
python -m uvicorn app.main:app --port 8000
```

## Возможности

- вход по логину и паролю, роли администратора и оператора;
- добавление, редактирование, поиск и удаление заказов;
- отметка о выполнении и возврат заказа в работу;
- список невыполненных заказов: сначала просроченные, затем остальные по плановой дате;
- доход за период от даты x до даты y;
- управление сотрудниками (для администратора).

База данных хранится в `data/service.db` и создаётся при первом запуске.

## Тесты

```sh
uv run pytest -q
```
