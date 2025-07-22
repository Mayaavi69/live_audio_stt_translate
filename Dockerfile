FROM python:3.10-slim
WORKDIR /app
COPY backend/ ./backend/
COPY config/ ./config/
WORKDIR /app/backend
RUN apt-get update && apt-get install -y libportaudio2 ffmpeg
RUN pip install --upgrade pip && pip install -r requirements.txt
CMD ["python", "main.py"]