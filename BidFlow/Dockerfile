FROM python:3.12-slim

WORKDIR /app

# 安装系统依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libmariadb-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# 复制依赖并安装
COPY backend/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

# 复制应用代码
COPY backend/ /app/backend/

# 创建数据目录
RUN mkdir -p /app/backend/uploads /app/backend/data /app/backend/chroma

WORKDIR /app/backend

# 暴露端口
EXPOSE 8000

# 启动
CMD ["gunicorn", "app.main:app", "--worker-class", "uvicorn.workers.UvicornWorker", "--workers", "2", "--bind", "0.0.0.0:8000"]
