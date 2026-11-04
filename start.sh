#!/bin/sh
set -e

echo ">>> Запуск FreeDeepseekAPI..."
node /app/FreeDeepseekAPI/server.js &
NODE_PID=$!

# Даём прокси время подняться
sleep 3

echo ">>> Запуск Python-бота..."
python3 /app/Script.py &
PYTHON_PID=$!

# Ждём завершения любого из процессов
wait -n $NODE_PID $PYTHON_PID
