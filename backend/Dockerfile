FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential gcc curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
# torch's full GPU wheel is large; the CPU-only index keeps the image
# reasonable for a laptop demo. Swap back to plain `pip install torch`
# if you have a CUDA-enabled deployment target.
RUN pip install --no-cache-dir --index-url https://download.pytorch.org/whl/cpu torch \
    && pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
