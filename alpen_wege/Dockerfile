FROM python:3.12-slim

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends libpq-dev gcc libcairo2 fontconfig \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Inter (bundled) must be the font cairo draws card text with, the one render.py measures
RUN mkdir -p /usr/local/share/fonts/inter && cp app/compendium/cards/fonts/*.ttf /usr/local/share/fonts/inter/ && fc-cache -f

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
