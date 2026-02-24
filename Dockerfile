FROM python:3.12-slim

WORKDIR /app
COPY pyproject.toml README.md LICENSE ./
COPY src/ src/

RUN pip install --no-cache-dir ".[server]"

EXPOSE 9000

ENTRYPOINT ["swarm-router"]
CMD ["serve", "--port", "9000"]
