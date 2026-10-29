FROM debian:bookworm-slim
RUN apt-get update \
 && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
      iproute2 iptables iputils-ping traceroute netcat-openbsd tcpdump conntrack python3 procps \
 && rm -rf /var/lib/apt/lists/*
COPY listener.py bulk.py /opt/np/
CMD ["python3", "/opt/np/listener.py"]
