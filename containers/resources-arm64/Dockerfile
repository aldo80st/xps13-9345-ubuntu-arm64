FROM ubuntu:26.10
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates git cargo rustc rustfmt build-essential pkg-config \
    libgtk-4-dev libadwaita-1-dev libsoup-3.0-dev libudev-dev \
    libxml2-utils gettext \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /src
