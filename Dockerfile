FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
# sentence-transformers pulls in torch; installing the CPU-only build first (before the
# rest of requirements.txt resolves it) avoids pulling the full CUDA/GPU package set,
# which this backend never uses and which roughly doubles image size and build time.
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
