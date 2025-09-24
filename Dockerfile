# Используем официальный Python-образ
FROM python:3.12
ENV PYTHONUNBUFFERED 1
# Создаем рабочую директорию
WORKDIR /app

# Скопируем requirements, если он есть (лучше вынести зависимости туда)
COPY requirements.txt .

# Установим зависимости
RUN pip install -r requirements.txt

# Скопируем весь код бота
COPY . /app

# Запускаем бота
CMD ["python", "bot.py"]
