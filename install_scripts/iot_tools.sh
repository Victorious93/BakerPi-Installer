#!/bin/bash
# IoT protocols, GPIO, and sensor tools
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive
TOOL_ID="${1:-}"
UPDATE_MODE="${2:-}"

install_rpi_gpio() {
  echo "[iot] Installing RPi.GPIO + gpiozero..."
  apt-get install -y --no-install-recommends python3-rpi.gpio python3-gpiozero python3-colorzero
  echo "[iot] GPIO libraries installed."
}

install_pigpio() {
  echo "[iot] Installing pigpio..."
  apt-get install -y --no-install-recommends pigpio python3-pigpio
  systemctl enable pigpiod
  systemctl start pigpiod 2>/dev/null || true
  echo "[iot] pigpio installed and daemon started."
}

install_i2c_tools() {
  echo "[iot] Installing i2c-tools + python3-smbus2..."
  apt-get install -y --no-install-recommends i2c-tools python3-smbus2
  # Enable I2C in /boot/config.txt
  if ! grep -q "^dtparam=i2c_arm=on" /boot/config.txt 2>/dev/null; then
    echo "dtparam=i2c_arm=on" >> /boot/config.txt
    echo "[iot] I2C enabled in /boot/config.txt — reboot required."
  fi
  echo "[iot] i2c-tools installed. After reboot: i2cdetect -y 1"
}

install_spi_dev() {
  echo "[iot] Installing python3-spidev..."
  apt-get install -y --no-install-recommends python3-spidev
  if ! grep -q "^dtparam=spi=on" /boot/config.txt 2>/dev/null; then
    echo "dtparam=spi=on" >> /boot/config.txt
    echo "[iot] SPI enabled in /boot/config.txt — reboot required."
  fi
  echo "[iot] spidev installed."
}

install_sensor_libraries() {
  echo "[iot] Installing Adafruit sensor libraries..."
  pip3 install --quiet \
    adafruit-circuitpython-dht \
    adafruit-circuitpython-bmp280 \
    adafruit-circuitpython-mpu6050 \
    adafruit-circuitpython-neopixel \
    board \
    RPi.GPIO
  echo "[iot] Adafruit/CircuitPython sensor libraries installed."
}

install_gpio_zero_extras() {
  echo "[iot] Installing gpiozero extras..."
  apt-get install -y --no-install-recommends python3-gpiozero python3-colorzero
  pip3 install --quiet gpiozero
  echo "[iot] gpiozero with motion/distance/servo support installed."
}

install_mosquitto() {
  echo "[iot] Installing Mosquitto MQTT broker + clients..."
  apt-get install -y --no-install-recommends mosquitto mosquitto-clients python3-paho-mqtt
  systemctl enable mosquitto
  systemctl start mosquitto 2>/dev/null || true
  echo "[iot] Mosquitto started on port 1883. Test: mosquitto_sub -t '#' -v"
}

install_node_red() {
  if [ "$UPDATE_MODE" = "update" ]; then
    echo "[iot] Updating Node-RED..."
    npm update -g node-red 2>/dev/null || true
    echo "[iot] Node-RED updated."
    return
  fi
  echo "[iot] Installing Node-RED..."
  apt-get install -y --no-install-recommends nodejs npm
  npm install -g --unsafe-perm node-red 2>/dev/null || true
  # Create systemd service
  cat > /etc/systemd/system/nodered.service << 'EOF'
[Unit]
Description=Node-RED
After=network.target

[Service]
Type=simple
User=root
ExecStart=/usr/local/bin/node-red --max-old-space-size=64
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF
  systemctl daemon-reload
  systemctl enable nodered
  echo "[iot] Node-RED installed. Start: systemctl start nodered | Access: http://172.16.0.1:1880"
}

install_zigbee2mqtt() {
  if [ "$UPDATE_MODE" = "update" ] && [ -d /opt/zigbee2mqtt ]; then
    echo "[iot] Updating zigbee2mqtt..."
    git -C /opt/zigbee2mqtt pull 2>/dev/null || true
    cd /opt/zigbee2mqtt && npm ci --production 2>/dev/null || true
    echo "[iot] zigbee2mqtt updated."
    return
  fi
  echo "[iot] Installing zigbee2mqtt..."
  apt-get install -y --no-install-recommends nodejs npm git
  mkdir -p /opt/zigbee2mqtt
  git clone --depth=1 https://github.com/Koenkk/zigbee2mqtt.git /opt/zigbee2mqtt 2>/dev/null || true
  cd /opt/zigbee2mqtt && npm ci --production 2>/dev/null || true
  cp /opt/zigbee2mqtt/data/configuration.example.yaml /opt/zigbee2mqtt/data/configuration.yaml 2>/dev/null || true
  echo "[iot] zigbee2mqtt installed. Edit /opt/zigbee2mqtt/data/configuration.yaml and set your coordinator port."
}

install_coap_tools() {
  echo "[iot] Installing python-aiocoap..."
  pip3 install --quiet aiocoap
  echo "[iot] aiocoap installed. Usage: python3 -m aiocoap.cli.client coap://target/resource"
}

install_lorawan() {
  echo "[iot] Installing ChirpStack gateway bridge..."
  apt-get install -y --no-install-recommends apt-transport-https dirmngr
  apt-key adv --keyserver keyserver.ubuntu.com --recv-keys 1CE2AFD36DBCCA00 2>/dev/null || true
  echo "deb https://artifacts.chirpstack.io/packages/4.x/deb stable main" \
    > /etc/apt/sources.list.d/chirpstack.list
  apt-get update -qq 2>/dev/null || true
  apt-get install -y --no-install-recommends chirpstack-gateway-bridge 2>/dev/null || \
    echo "[iot] ChirpStack package not available for this architecture — use Docker instead."
}

install_modbus_tools() {
  echo "[iot] Installing pymodbus..."
  pip3 install --quiet pymodbus
  echo "[iot] pymodbus installed. Usage: python3 -m pymodbus.console tcp --host 192.168.1.1 --port 502"
}

case "$TOOL_ID" in
  "rpi_gpio")           install_rpi_gpio ;;
  "pigpio")             install_pigpio ;;
  "i2c_tools")          install_i2c_tools ;;
  "spi_dev")            install_spi_dev ;;
  "sensor_libraries")   install_sensor_libraries ;;
  "gpio_zero_extras")   install_gpio_zero_extras ;;
  "mosquitto")          install_mosquitto ;;
  "node_red")           install_node_red ;;
  "zigbee2mqtt")        install_zigbee2mqtt ;;
  "coap_tools")         install_coap_tools ;;
  "lorawan")            install_lorawan ;;
  "modbus_tools")       install_modbus_tools ;;
  "matter_thread")
    echo "[iot] Installing OpenThread Border Router agent..."
    pip3 install --quiet chip-repl 2>/dev/null || echo "[iot] chip-repl install needs CHIP SDK — see https://github.com/project-chip/connectedhomeip"
    ;;
  *)
    echo "[iot] Unknown tool: $TOOL_ID"
    exit 1
    ;;
esac
