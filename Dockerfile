FROM python:3.12-slim

WORKDIR /app

# 系统依赖（Playwright Chromium 需要）
RUN apt-get update && apt-get install -y --no-install-recommends \
    wget gnupg ca-certificates fonts-wqy-zenhei fonts-noto-cjk \
    libnss3 libatk1.0-0 libatk-bridge2.0-0 libcups2 libdrm2 \
    libxkbcommon0 libxcomposite1 libxdamage1 libxfixes3 libxrandr2 \
    libgbm1 libpango-1.0-0 libcairo2 libasound2t64 \
    && rm -rf /var/lib/apt/lists/*

# Python 依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && python -m playwright install --with-deps chromium

# 应用代码
COPY app/ app/
COPY static/ static/
COPY run.py .

# 数据目录（挂载持久卷）
RUN mkdir -p /data
ENV KANGZHAN_DATA=/data
ENV PYTHONUNBUFFERED=1

EXPOSE 8000

CMD ["python", "run.py", "--port", "8000", "--no-browser"]
