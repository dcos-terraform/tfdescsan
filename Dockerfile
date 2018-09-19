FROM python:3-alpine
WORKDIR /usr/src/tfdescsan

COPY . .
RUN pip install --no-cache-dir -r requirements.txt

ENTRYPOINT [ "python", "tfdescsan.py" ]
