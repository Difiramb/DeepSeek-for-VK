# Базовый образ с Node.js
FROM node:20-slim

# Устанавливаем Python и pip
RUN apt-get update && \
    apt-get install -y python3 python3-pip && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Копируем весь проект
COPY . .

# --- Настройка и сборка Node.js-прокси ---
WORKDIR /app/FreeDeepseekAPI
RUN npm install --omit=dev

# --- Установка Python-зависимостей ---
WORKDIR /app
RUN pip3 install --no-cache-dir -r requirements.txt

# Переменные для прокси: отключаем меню и слушаем все интерфейсы
ENV NON_INTERACTIVE=1
ENV HOST=0.0.0.0
ENV PORT=3000

RUN apt-get update && apt-get install -y supervisor
# Запускаем оба процесса
COPY start.sh /app/start.sh
RUN chmod +x /app/start.sh

CMD ["/app/start.sh"]

COPY supervisord.conf /etc/supervisor/conf.d/supervisord.conf
CMD ["supervisord", "-c", "/etc/supervisor/conf.d/supervisord.conf"]
