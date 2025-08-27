# Dockerfile
FROM python:3.10-slim

ENV LANG=C.UTF-8 LC_ALL=C.UTF-8 TZ=Asia/Seoul

RUN apt-get update && apt-get install -y --no-install-recommends \
    chromium \
    chromium-driver \
    fonts-noto-cjk \
    libnss3 libxi6 libxrender1 libxcomposite1 \
    libxrandr2 libatk1.0-0 libatk-bridge2.0-0 libxdamage1 \
    libgbm1 libasound2 libpango-1.0-0 libcairo2 \
    libxshmfence1 libx11-xcb1 libdrm2 libxfixes3 \
  && rm -rf /var/lib/apt/lists/*

ENV PYTHONUNBUFFERED=1 \
    CHROME_BIN=/usr/bin/chromium \
    CHROMEDRIVER_BIN=/usr/bin/chromedriver \
    PORT=8000

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# 권장: wsgi 엔트리 사용
CMD ["sh","-c","gunicorn -k gthread -w 1 -b 0.0.0.0:${PORT} wsgi:app --timeout 300 --log-level info"]

