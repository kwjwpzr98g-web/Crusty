FROM python:3.11-slim
ENV PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY app.py maker.py index.html ./
RUN mkdir -p /data
EXPOSE 8080
CMD ["python","app.py"]
