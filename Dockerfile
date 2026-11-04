FROM node:20-slim

# Устанавливаем Python, pip, venv и supervisor
RUN apt-get update && \
    apt-get install -y python3 python3-pip python3-venv supervisor && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Копируем весь проект
COPY . .

# --- Настройка Node.js-прокси ---
WORKDIR /app/FreeDeepseekAPI
RUN npm install --omit=dev

# --- Настройка Python-зависимостей через venv (решает ошибку externally-managed) ---
WORKDIR /app
RUN python3 -m venv /opt/venv
RUN /opt/venv/bin/pip install --no-cache-dir -r requirements.txt

# Переменные для прокси
ENV NON_INTERACTIVE=1
ENV HOST=0.0.0.0
ENV PORT=3000

# Копируем конфиг supervisor
COPY supervisord.conf /etc/supervisor/conf.d/supervisord.conf

# Запускаем supervisor — он поднимет оба процесса
CMD ["supervisord", "-c", "/etc/supervisor/conf.d/supervisord.conf"]
