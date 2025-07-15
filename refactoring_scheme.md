├── bot/
│   ├── __init__.py
│   ├── main.py          # Точка входа
│   ├── config.py        # Конфигурация
│   ├── database/
│   │   ├── __init__.py
│   │   ├── models.py    # Модели SQLAlchemy
│   │   └── crud.py      # Операции с БД
│   ├── handlers/
│   │   ├── __init__.py
│   │   ├── common.py    # Общие хендлеры
│   │   ├── feedback.py  # Обратная связь
│   │   ├── session.py   # Сессии
│   │   └── profile.py   # Профиль
│   ├── keyboards/
│   │   ├── __init__.py
│   │   ├── builder.py   # Построители клавиатур
│   │   └── texts.py     # Тексты кнопок
│   ├── states.py        # Состояния FSM
│   └── texts/
│       ├── __init__.py
│       ├── common.py    # Общие тексты
│       ├── feedback.py  # Тексты обратной связи
│       └── session.py   # Тексты сессий
└── requirements.txt