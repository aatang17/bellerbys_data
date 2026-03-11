# Bellerbys Offer Database — used when this repo is deployed from root (single service).
# For a second service (Offer Letter Generator), set Root Directory to Offer_Letter_Generator.
FROM python:3.12-slim

WORKDIR /app
COPY Bellerbys_Offer_Database/ ./Bellerbys_Offer_Database/
WORKDIR /app/Bellerbys_Offer_Database

RUN pip install --no-cache-dir -r requirements.txt

EXPOSE 8000
ENV PORT=8000
CMD uvicorn app:app --host 0.0.0.0 --port ${PORT}
