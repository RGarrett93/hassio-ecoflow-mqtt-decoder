ARG BUILD_FROM=ghcr.io/hassio-addons/base:14.0.0
FROM $BUILD_FROM

# Install Python & pip
RUN apk add --no-cache python3 py3-pip

# Copy requirements first (for caching)
COPY ecoflow.proto ecoflow_pb2.py requirements.txt /
# Allow pip to bypass PEP 668 restrictions
RUN pip3 install --no-cache-dir --break-system-packages -r /requirements.txt

# Copy decoder script and run script
COPY decoder.py /decoder.py
COPY run.sh /run.sh
RUN chmod a+x /run.sh

CMD [ "/run.sh" ]
