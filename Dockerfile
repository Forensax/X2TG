FROM python:3.9-slim

WORKDIR /app

# 设置时区为上海
ENV TZ=Asia/Shanghai
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# 创建数据目录
RUN mkdir -p /app/data

# 默认命令
CMD ["python", "main.py"]
