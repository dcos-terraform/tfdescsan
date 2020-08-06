FROM python:3-alpine
WORKDIR /usr/src/tfdescsan
COPY . .
RUN apk add --no-cache wget ca-certificates openjdk8-jre git \
    && pip install --no-cache-dir -r requirements.txt \
    && chmod +x tfdescsan.py \
    && mv tfdescsan.py /usr/bin/tfdescsan
WORKDIR /root
ENTRYPOINT ["/usr/bin/tfdescsan"]
