FROM docker.linkos.org/library/python:3.13-slim

WORKDIR /app

# 设置时区为上海
ENV TZ=Asia/Shanghai
# 确保 Python 输出不被缓存，这样日志可以在 Docker 中实时显示
ENV PYTHONUNBUFFERED=1
ENV PIP_INDEX_URL=https://mirrors.tuna.tsinghua.edu.cn/pypi/web/simple
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# 创建数据目录
RUN mkdir -p /app/data

EXPOSE 8000

# 默认命令
CMD ["uvicorn", "app.web:app", "--host", "0.0.0.0", "--port", "8000"]
