#!/usr/bin/with-contenv bashio
set -e

bashio::log.info "Starting EcoFlow Decoder add-on..."
exec python3 /decoder.py